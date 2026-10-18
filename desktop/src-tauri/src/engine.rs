//! Engine lifecycle: choose a driver, hand it the app handle, stay out of the way.
//!
//! Two drivers exist.
//!
//! * **The real engine** (`sidecar.rs`) — spawns `main.py --engine-stdio` and talks JSON lines to
//!   it (`T-022`). This is the default: detection, icons, taglines and the Discord connection all
//!   come from the Python pipeline the tray build uses.
//! * **The mock** (`AUTORPC_ENGINE=mock`) — cycling demo apps that exercise every affordance the
//!   UI has (app switches, taglines, logs) without touching Discord or GDI. Use it to review the
//!   interface, and as the fallback when no engine can be started.
//!
//! `AUTORPC_ENGINE=python` insists on the real engine and reports the failure instead of falling
//! back, so a broken install is visible rather than quietly mocked.
//!
//! Two things the mock never fakes:
//!
//! * **nothing is sent to Discord** — it says so in the log at startup;
//! * **the Discord status is probed for real** (`discord::probe`), so the Status pane shows
//!   "Discord is not running" when that is the truth rather than a green pill.

use std::thread;
use std::time::Duration;

use tauri::AppHandle;

use crate::config_file;
use crate::discord;
use crate::paths;
use crate::service;
use crate::sidecar;
use crate::state::{AppInfo, DISCORD_CONNECTED, DISCORD_OFFLINE, ENGINE_OFFLINE, ENGINE_WAITING};

/// Rotating demo apps. Paths are plausible-but-fake: nothing here reads a real process.
const DEMO: &[(&str, &str, &str, &str)] = &[
    (
        "code.exe",
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        "Visual Studio Code",
        "Writing code",
    ),
    (
        "chrome.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "Google Chrome",
        "Surfing the internet",
    ),
    (
        "notion.exe",
        r"C:\Users\you\AppData\Local\Programs\Notion\Notion.exe",
        "Notion",
        "Working on a document",
    ),
    (
        "spotify.exe",
        r"C:\Users\you\AppData\Roaming\Spotify\Spotify.exe",
        "Spotify",
        "Listening to music",
    ),
];

const IDLE_LINES: &[&str] = &[
    "poll: no change (foreground still the same app)",
    "presence: within the 15 s rate limit, nothing sent",
    "presence: deduped — identical presence to the last update",
    "idle: waiting for a window switch",
];

pub fn start(app: AppHandle) {
    let mode = std::env::var("AUTORPC_ENGINE")
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase();

    // `mock` is for reviewing the UI without touching Discord; `python` insists on the real
    // engine; anything else — the default — tries the real engine and falls back to the mock.
    if mode == "mock" {
        start_mock(app);
        return;
    }

    if sidecar::start(app.clone()) {
        return;
    }

    if mode == "python" {
        service::set_engine(&app, ENGINE_OFFLINE);
        service::ui_log(
            &app,
            "WARNING",
            "autorpc.engine",
            "AUTORPC_ENGINE=python was requested but the engine could not be started. Running \
             without one — nothing is sent to Discord.",
        );
        return;
    }

    service::ui_log(
        &app,
        "WARNING",
        "autorpc.engine",
        "Falling back to the mock engine.",
    );
    start_mock(app);
}

fn start_mock(app: AppHandle) {
    service::refresh_flags(&app);
    service::set_engine(&app, ENGINE_WAITING);
    service::set_discord(&app, DISCORD_OFFLINE);

    service::ui_log(
        &app,
        "INFO",
        "autorpc.engine",
        "Started the mock engine (AUTORPC_ENGINE=mock). Demo apps are cycled for reviewing the UI; \
         nothing is sent to Discord.",
    );

    thread::spawn(move || {
        thread::sleep(Duration::from_millis(700));

        // The probe can block for up to 2.5 s, so it lives here rather than in `setup`.
        report_discord(&app);

        let mut tick: usize = 0;

        loop {
            thread::sleep(Duration::from_secs(3));

            if service::is_paused(&app) {
                continue;
            }

            if tick % 3 == 0 {
                let (exe, path, name, tagline) = DEMO[(tick / 3) % DEMO.len()];

                let mut info = AppInfo::new(exe, path, name);
                info.tagline = Some(tagline.to_string());
                info.started_at_ms = Some(paths::now_ms());
                info.pid = 4_000 + tick as u32;

                service::set_current_app(&app, info);
                service::emit_log(
                    &app,
                    "DEBUG",
                    "autorpc.detector",
                    &format!("poll: foreground changed -> {exe} ({name})"),
                );
            } else {
                let message = IDLE_LINES[tick % IDLE_LINES.len()];
                service::emit_log(&app, "DEBUG", "autorpc.detector", message);
            }

            tick += 1;
        }
    });
}

/// Ask Discord whether it is actually there. The mock reports the answer verbatim.
fn report_discord(app: &AppHandle) {
    let config = config_file::load();
    let app_id = config_file::string_field(&config, "application_id");

    if app_id.is_empty() {
        service::emit_log(
            app,
            "INFO",
            "autorpc.engine",
            "No Application ID is configured, so Discord was not contacted.",
        );
        return;
    }

    if discord::probe(&app_id).ok {
        service::set_discord(app, DISCORD_CONNECTED);
        service::emit_log(
            app,
            "INFO",
            "autorpc.engine",
            "Discord answered the handshake. (The mock engine still sends no presence.)",
        );
    } else {
        service::set_discord_not_running(app);
        service::emit_log(
            app,
            "INFO",
            "autorpc.engine",
            "Discord did not answer on its IPC pipe — start Discord to connect.",
        );
    }
}
