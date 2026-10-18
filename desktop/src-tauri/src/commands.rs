//! Every `#[tauri::command]` the frontend can call, and nothing else.
//!
//! Names here are the other half of `cmd` in `src/ipc/types.ts` — if one is renamed, the
//! other must be too, or the call fails at runtime (there is no compile-time link between
//! a string and a Rust function).
//!
//! Conventions:
//! * a mutation returns the value that is now on disk, never a bare `()`; the frontend
//!   replaces its store with it rather than guessing (SEM-6);
//! * errors are `Result<_, String>` with a sentence that can go straight into a toast —
//!   the frontend never invents copy for a backend failure (ERR-2);
//! * no command blocks the UI thread for longer than a stream read (`test_connection` runs
//!   its blocking read on a helper thread with a 2.5 s cap).

use serde::Serialize;
use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};
use tauri_plugin_autostart::ManagerExt as AutostartExt;
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_opener::OpenerExt;

use crate::config_file;
use crate::discord::{self, ConnectionTest};
use crate::ignore_store::{self, IgnoredListing};
use crate::paths;
use crate::prefs::{self, Prefs};
use crate::service;
use crate::sidecar;
use crate::state::{EngineState, LogLine};
use crate::windows;

#[derive(Clone, Debug, Serialize)]
pub struct BuiltIns {
    pub taglines: std::collections::BTreeMap<String, String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInfo {
    pub current: String,
    pub latest: Option<String>,
    pub url: Option<String>,
}

/* ------------------------------------------------------- boot handshake --- */

/// Called by each window after its first paint. This is the only place a window is shown,
/// which is what makes the no-white-flash guarantee hold (THEME-3 / D-046).
#[tauri::command]
pub fn ready(window: WebviewWindow) -> Result<(), String> {
    let appearance = prefs::load().appearance;
    windows::show_with_theme(&window, &appearance);
    Ok(())
}

#[tauri::command]
pub fn get_state(app: AppHandle) -> EngineState {
    service::refresh_flags(&app);
    service::snapshot(&app)
}

/* ------------------------------------------------------------- config --- */

#[tauri::command]
pub fn get_config() -> Value {
    config_file::load()
}

#[tauri::command]
pub fn set_config(app: AppHandle, patch: Value) -> Result<Value, String> {
    let next = config_file::update(patch)?;
    let _ = app.emit("config-changed", &next);
    service::refresh_flags(&app);
    // config.json is the shared truth between the two halves of the app, so the engine is told
    // to re-read it now rather than waiting for its own file check (`T-022`).
    sidecar::reload_config();
    Ok(next)
}

#[tauri::command]
pub fn reset_config(app: AppHandle) -> Result<Value, String> {
    let next = config_file::reset()?;
    let _ = app.emit("config-changed", &next);
    service::refresh_flags(&app);
    sidecar::reload_config();
    Ok(next)
}

#[tauri::command]
pub fn export_config() -> Result<String, String> {
    let value = config_file::load();
    let mut text = serde_json::to_string_pretty(&value).map_err(|e| format!("Couldn't encode config: {e}"))?;
    text.push('\n');

    let target = paths::exports_dir().join(format!("config-{}.json", paths::stamp()));
    paths::write_atomic(&target, text.as_bytes()).map_err(|e| format!("Couldn't write the export: {e}"))?;

    Ok(target.display().to_string())
}

/* -------------------------------------------------------------- prefs --- */

#[tauri::command]
pub fn get_prefs() -> Prefs {
    prefs::load()
}

#[tauri::command]
pub fn set_prefs(app: AppHandle, appearance: String) -> Result<Prefs, String> {
    let saved = prefs::save(&appearance)?;

    // Every window follows, including ones opened later, which read the file on creation.
    let _ = app.emit("ui-prefs-changed", &saved);
    for (_, window) in app.webview_windows() {
        windows::apply_theme(&window, &saved.appearance);
    }

    Ok(saved)
}

#[tauri::command]
pub fn set_window_theme(window: WebviewWindow, appearance: String) {
    windows::apply_theme(&window, &appearance);
}

/* ---------------------------------------------------------- autostart --- */

#[tauri::command]
pub fn get_autostart(app: AppHandle) -> bool {
    app.autolaunch().is_enabled().unwrap_or(false)
}

#[tauri::command]
pub fn set_autostart(app: AppHandle, enabled: bool) -> Result<bool, String> {
    let manager = app.autolaunch();

    if enabled {
        manager
            .enable()
            .map_err(|e| format!("Windows refused the startup entry: {e}"))?;
    } else {
        manager
            .disable()
            .map_err(|e| format!("Windows refused to remove the startup entry: {e}"))?;
    }

    // Read back rather than trusting the call: a policy can block the write silently.
    let actual = manager.is_enabled().unwrap_or(false);
    service::set_autostart(&app, actual);
    Ok(actual)
}

/* --------------------------------------------------------- connection --- */

#[tauri::command]
pub fn test_connection(app_id: String) -> ConnectionTest {
    discord::probe(&app_id)
}

/* -------------------------------------------------------------- engine --- */

#[tauri::command]
pub fn pause(app: AppHandle) {
    service::pause(&app);
}

#[tauri::command]
pub fn resume(app: AppHandle) {
    service::resume(&app);
}

#[tauri::command]
pub fn rename_app(app: AppHandle, exe: String, name: String, tagline: String) -> Result<Value, String> {
    let key = config_file::normalize_exe(&exe);
    if key.is_empty() {
        return Err("That doesn't look like an executable name.".to_string());
    }

    let display = name.trim();
    if display.is_empty() {
        return Err("A display name is required.".to_string());
    }

    let mut entry = serde_json::Map::new();
    entry.insert("name".to_string(), Value::String(display.to_string()));

    let tagline = tagline.trim();
    if !tagline.is_empty() {
        entry.insert("tagline".to_string(), Value::String(tagline.to_string()));
    }

    let next = config_file::set_map_entry("overrides", &key, Some(Value::Object(entry)))?;
    let _ = app.emit("config-changed", &next);
    // The engine resolves display names, so it has to see the override before the next presence
    // goes out (`T-022`).
    sidecar::reload_config();

    // R-7: the app on screen updates immediately, without waiting for the next poll.
    service::relabel_current(&app, &key, display, if tagline.is_empty() { None } else { Some(tagline) });

    Ok(next)
}

#[tauri::command]
pub fn remove_override(app: AppHandle, exe: String) -> Result<Value, String> {
    let key = config_file::normalize_exe(&exe);
    if key.is_empty() {
        return Err("That doesn't look like an executable name.".to_string());
    }

    let next = config_file::set_map_entry("overrides", &key, None)?;
    let _ = app.emit("config-changed", &next);
    sidecar::reload_config();

    Ok(next)
}

/* -------------------------------------------------------------- ignore --- */

#[tauri::command]
pub fn get_ignored() -> IgnoredListing {
    ignore_store::load()
}

#[tauri::command]
pub fn ignore_app(app: AppHandle, exe: String) -> Result<(), String> {
    ignore_store::add(&exe)?;
    service::refresh_ignored(&app);
    Ok(())
}

#[tauri::command]
pub fn unignore_app(app: AppHandle, exe: String) -> Result<(), String> {
    ignore_store::remove(&exe)?;
    service::refresh_ignored(&app);
    Ok(())
}

/* ----------------------------------------------------------- built-ins --- */

/// The engine's own built-in tagline table, cached from the `builtins` line it sends on startup.
///
/// Empty until the engine answers. Duplicating the table into Rust would create a second source
/// of truth that silently drifts from `detector.py::_BUILTIN_TAGLINES` (`T-022`), so an empty
/// list means "the engine has not started", not "there are none".
#[tauri::command]
pub fn get_built_ins() -> BuiltIns {
    BuiltIns {
        taglines: sidecar::built_ins().into_iter().collect(),
    }
}

/* --------------------------------------------------------------- logs --- */

#[tauri::command]
pub fn seed_logs() -> Vec<LogLine> {
    service::seed_from_file(200)
}

#[tauri::command]
pub fn export_logs() -> Result<Option<String>, String> {
    let source = paths::log_path();
    if !source.is_file() {
        return Ok(None);
    }

    let target = paths::exports_dir().join(format!("autorpc-log-{}.txt", paths::stamp()));
    std::fs::copy(&source, &target).map_err(|e| format!("Couldn't copy the log: {e}"))?;

    Ok(Some(target.display().to_string()))
}

#[tauri::command]
pub fn clear_icon_cache() -> Result<usize, String> {
    let path = paths::icon_cache_path();
    let Some(raw) = paths::read_to_string(&path) else {
        return Ok(0);
    };

    let count = serde_json::from_str::<Value>(&raw)
        .ok()
        .map(|value| match value {
            Value::Object(map) => map.len(),
            Value::Array(items) => items.len(),
            _ => 0,
        })
        .unwrap_or(0);

    std::fs::remove_file(&path).map_err(|e| format!("Couldn't delete icon_cache.json: {e}"))?;

    Ok(count)
}

/// Report a UI-side failure into the log. Not in `cmd` — `src/ipc/client.ts` calls it by
/// name from the error boundary and the write-failure path.
#[tauri::command]
pub fn ui_log(app: AppHandle, level: String, message: String) {
    service::ui_log(&app, &level, "autorpc.ui", &message);
}

/* --------------------------------------------------------------- misc --- */

#[tauri::command]
pub fn copy_text(app: AppHandle, text: String) -> Result<(), String> {
    app.clipboard()
        .write_text(text)
        .map_err(|e| format!("Couldn't copy to the clipboard: {e}"))
}

#[tauri::command]
pub fn app_icon_url(exe: String) -> Option<String> {
    let key = config_file::normalize_exe(&exe);
    if key.is_empty() {
        return None;
    }

    let config = config_file::load();

    if let Some(url) = config
        .get("overrides")
        .and_then(|value| value.get(&key))
        .and_then(|value| value.get("icon_url"))
        .and_then(Value::as_str)
    {
        return Some(url.to_string());
    }

    paths::read_to_string(&paths::icon_cache_path())
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .and_then(|value| match value {
            Value::Object(map) => map.get(&key).and_then(Value::as_str).map(str::to_string),
            _ => None,
        })
}

/// The updater is Phase 2. It is a real command today so the Status pane has something
/// truthful to say: no update is pending, and nothing is silently checked.
#[tauri::command]
pub fn check_updates() -> UpdateInfo {
    UpdateInfo {
        current: env!("CARGO_PKG_VERSION").to_string(),
        latest: None,
        url: None,
    }
}

/* ------------------------------------------------------------ opening --- */

#[tauri::command]
pub fn open_url(app: AppHandle, url: String) -> Result<(), String> {
    if !url.starts_with("https://") {
        return Err("Only https:// links can be opened from here.".to_string());
    }

    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| format!("Couldn't open the link: {e}"))
}

#[tauri::command]
pub fn open_log(app: AppHandle) {
    open_log_impl(&app);
}

/// Shared with the tray menu item.
pub fn open_log_impl(app: &AppHandle) {
    let path = paths::log_path();

    if path.is_file() {
        if app
            .opener()
            .open_path(path.display().to_string(), None::<&str>)
            .is_ok()
        {
            return;
        }
    }

    let _ = app
        .opener()
        .open_path(paths::data_dir().display().to_string(), None::<&str>);
}

#[tauri::command]
pub fn open_log_folder(app: AppHandle) -> Result<(), String> {
    app.opener()
        .open_path(paths::data_dir().display().to_string(), None::<&str>)
        .map_err(|e| format!("Couldn't open the folder: {e}"))
}

#[tauri::command]
pub fn open_settings(app: AppHandle) {
    windows::open_settings(&app);
}

#[tauri::command]
pub fn open_onboarding(app: AppHandle) {
    windows::open_onboarding(&app);
}

#[tauri::command]
pub fn open_rename(app: AppHandle) {
    windows::open_rename(&app);
}

#[tauri::command]
pub fn close_window(window: WebviewWindow) {
    let _ = window.close();
}

/* --------------------------------------------------------- window chrome --- */

/// Minimize, maximize/restore and close for the frameless chrome (D-055).
///
/// These are commands rather than JS plugin calls on purpose: they keep the frontend free of
/// Tauri imports and the capability set at `core:default` plus the two permissions the drag
/// region itself needs.
#[tauri::command]
pub fn minimize_window(window: WebviewWindow) -> Result<(), String> {
    window
        .minimize()
        .map_err(|error| format!("Couldn't minimize the window: {error}"))?;

    // tao rebuilds the window style for the minimized flag, which restores the caption; the
    // window is not visible right now, but it must still be frameless when it comes back.
    crate::windows::strip_caption_of(&window);
    Ok(())
}

#[tauri::command]
pub fn toggle_maximize(window: WebviewWindow) -> Result<(), String> {
    let maximized = window.is_maximized().unwrap_or(false);

    let result = if maximized {
        window.unmaximize()
    } else {
        window.maximize()
    };

    result.map_err(|error| format!("Couldn't resize the window: {error}"))?;

    // Same reason as `minimize_window`, and this one is visible: maximizing re-applies the
    // caption in the same frame, so it is cleared before the OS finishes animating.
    crate::windows::strip_caption_of(&window);
    Ok(())
}

/* ---------------------------------------------------------------- test --- */

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn built_ins_start_empty() {
        assert!(get_built_ins().taglines.is_empty());
    }

    #[test]
    fn update_info_reports_the_shipped_version() {
        let info = check_updates();
        assert_eq!(info.current, env!("CARGO_PKG_VERSION"));
        assert!(info.latest.is_none());
    }
}
