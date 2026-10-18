//! Everything that mutates engine state, plus the log pipeline.
//!
//! Commands and tray handlers both go through here so there is exactly one place that
//! emits `state` events and one place that writes log lines.

use std::sync::atomic::{AtomicU64, Ordering};

use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_autostart::ManagerExt as AutostartExt;

use crate::clock;
use crate::config_file;
use crate::ignore_store;
use crate::paths;
use crate::sidecar;
use crate::state::{
    AppInfo, EngineState, LogLine, Shared, DISCORD_CONNECTED, DISCORD_NOT_RUNNING, DISCORD_OFFLINE,
    ENGINE_ACTIVE, ENGINE_PAUSED, ENGINE_WAITING,
};

static NEXT_LOG_ID: AtomicU64 = AtomicU64::new(1);

pub fn snapshot(app: &AppHandle) -> EngineState {
    app.state::<Shared>().snapshot()
}

/// Mutate the snapshot and push it to every window.
pub fn mutate(app: &AppHandle, change: impl FnOnce(&mut EngineState)) {
    app.state::<Shared>().mutate(change);
    push(app);
}

pub fn push(app: &AppHandle) {
    let state = snapshot(app);
    let _ = app.emit("state", &state);
    crate::tray::sync(app, &state);
}

/* ------------------------------------------------------------ engine bits --- */

pub fn is_paused(app: &AppHandle) -> bool {
    snapshot(app).engine == ENGINE_PAUSED
}

pub fn pause(app: &AppHandle) {
    mutate(app, |state| {
        state.engine = ENGINE_PAUSED.to_string();
        state.discord = DISCORD_OFFLINE.to_string();
    });
    emit_log(app, "INFO", "autorpc.presence", "Presence cleared (paused from the menu)");

    // The engine owns the Discord connection, so pausing has to reach it: it clears the presence
    // and stops polling until `resume` arrives (`T-022`). This lives here rather than in the
    // command so the tray's Pause and the pane's cannot drift out of step.
    sidecar::set_paused(true);
}

pub fn resume(app: &AppHandle) {
    let waiting = snapshot(app).app.is_none();
    mutate(app, |state| {
        state.engine = if waiting { ENGINE_WAITING } else { ENGINE_ACTIVE }.to_string();
        state.discord = DISCORD_CONNECTED.to_string();
    });
    emit_log(app, "INFO", "autorpc.presence", "Broadcasting resumed");
    sidecar::set_paused(false);
}

pub fn set_engine(app: &AppHandle, status: &str) {
    mutate(app, |state| state.engine = status.to_string());
}

pub fn set_discord(app: &AppHandle, status: &str) {
    mutate(app, |state| state.discord = status.to_string());
}

pub fn set_current_app(app: &AppHandle, info: AppInfo) {
    let exe = info.exe.clone();
    mutate(app, |state| {
        state.engine = if state.engine == ENGINE_PAUSED {
            ENGINE_PAUSED.to_string()
        } else {
            ENGINE_ACTIVE.to_string()
        };

        let mut recent = vec![exe.clone()];
        recent.extend(state.recent_apps.iter().filter(|item| **item != exe).cloned());
        recent.truncate(8);
        state.recent_apps = recent;

        state.app = Some(info);
    });
}

/// Used by the engine port (`T-022`) when the foreground app disappears or is ignored.
#[allow(dead_code)]
pub fn clear_current_app(app: &AppHandle) {
    mutate(app, |state| {
        state.app = None;
        if state.engine != ENGINE_PAUSED {
            state.engine = ENGINE_WAITING.to_string();
        }
    });
}

/// Apply a rename to the app on screen right now, without waiting for a poll (R-7).
pub fn relabel_current(app: &AppHandle, exe: &str, name: &str, tagline: Option<&str>) {
    mutate(app, |state| {
        if let Some(info) = state.app.as_mut() {
            if info.exe.eq_ignore_ascii_case(exe) {
                info.display_name = name.to_string();
                if let Some(value) = tagline {
                    info.tagline = Some(value.to_string());
                }
            }
        }
    });
}

/// Re-read the two flags that come from outside the engine: configured, autostart.
pub fn refresh_flags(app: &AppHandle) {
    let configured = config_file::is_configured(&config_file::load());
    let autostart_enabled = app.autolaunch().is_enabled().unwrap_or(false);

    mutate(app, |state| {
        state.configured = configured;
        state.autostart_enabled = autostart_enabled;
    });
}

pub fn set_autostart(app: &AppHandle, enabled: bool) {
    mutate(app, |state| state.autostart_enabled = enabled);
}

/// Recompute whether the app on screen is ignored.
pub fn refresh_ignored(app: &AppHandle) {
    let listing = ignore_store::load();
    mutate(app, |state| {
        if let Some(info) = state.app.as_mut() {
            info.ignored = listing
                .managed
                .iter()
                .chain(listing.legacy.iter())
                .any(|known| known.eq_ignore_ascii_case(&info.exe));
        }
    });

    // The engine does the actual filtering, so it needs the new list now instead of on its next
    // mtime check (`T-022`). Both writers of the list — the pane and the tray menu — end up here.
    sidecar::reload_config();
}

pub fn set_discord_not_running(app: &AppHandle) {
    set_discord(app, DISCORD_NOT_RUNNING);
}

/* --------------------------------------------------------------- logging --- */

pub fn emit_log(app: &AppHandle, level: &str, logger: &str, message: &str) {
    let line = LogLine {
        id: NEXT_LOG_ID.fetch_add(1, Ordering::Relaxed),
        ts: paths::now_ms(),
        level: level.to_uppercase(),
        logger: logger.to_string(),
        message: message.to_string(),
        display_time: None,
    };
    let _ = app.emit("log", &line);
}

/// A line that came from the UI. Shown live **and** appended to `autorpc.log`, because a
/// crash report that vanishes when the window closes is not a crash report.
pub fn ui_log(app: &AppHandle, level: &str, logger: &str, message: &str) {
    emit_log(app, level, logger, message);
    append_log_file(level, logger, message);
}

/// Byte-for-byte the Python handler's shape: `[2026-10-18 14:07:33] INFO    autorpc.ui - message`.
///
/// Both builds append to the same file, so the date is not optional — a shell line and an
/// engine line have to be indistinguishable in a text editor.
pub fn append_log_file(level: &str, logger: &str, message: &str) {
    use std::io::Write;

    let path = paths::log_path();
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        let line = format!(
            "[{}] {:<7} {} - {}\n",
            clock::timestamp_string(),
            level.to_uppercase(),
            logger,
            message
        );
        let _ = file.write_all(line.as_bytes());
    }
}

/// L-7: the view opens seeded with the last `limit` lines of the log file.
pub fn seed_from_file(limit: usize) -> Vec<LogLine> {
    let Some(raw) = paths::read_to_string(&paths::log_path()) else {
        return Vec::new();
    };

    let lines: Vec<&str> = raw.lines().collect();
    let start = lines.len().saturating_sub(limit);

    lines[start..]
        .iter()
        .filter_map(|line| parse_log_line(line))
        .collect()
}

/// Parse `[2026-10-18 14:07:33] INFO    autorpc.detector - message`.
///
/// A seeded line keeps its own clock string for display (`displayTime`), stripped of the date
/// so the Logs pane reads the same as live lines. `ts` is best-effort (now) and is never used
/// for ordering: seeded lines keep their file order, which is already chronological.
fn parse_log_line(raw: &str) -> Option<LogLine> {
    let rest = raw.strip_prefix('[')?;
    let (stamp, rest) = rest.split_once(']')?;
    let time = stamp.rsplit_once(' ').map_or(stamp, |(_, clock)| clock);
    let rest = rest.trim_start();

    let (level, rest) = match rest.split_once(char::is_whitespace) {
        Some((level, rest)) => (level, rest.trim_start()),
        None => (rest, ""),
    };

    let (logger, message) = rest.split_once(" - ").unwrap_or(("autorpc", rest));

    Some(LogLine {
        id: NEXT_LOG_ID.fetch_add(1, Ordering::Relaxed),
        ts: paths::now_ms(),
        level: level.to_uppercase(),
        logger: logger.to_string(),
        message: message.to_string(),
        display_time: Some(time.to_string()),
    })
}
