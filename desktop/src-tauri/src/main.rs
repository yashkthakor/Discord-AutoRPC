//! Discord AutoRPC — desktop shell.
//!
//! The entry point is deliberately thin: plugins, managed state, tray, first window, and the
//! engine. Everything else lives in a module with a single job (AGENTS.md §3 style).
//!
//! Startup order matters and is commented where it is not obvious:
//!
//! 1. single-instance first, so a second launch never gets as far as creating a tray icon;
//! 2. ignore-list migration before any window can read either ignore file (D-047);
//! 3. tray before the window, so the app is reachable even if the webview fails to paint;
//! 4. the Settings window is created **hidden** and shown by the frontend's `ready` call,
//!    which is what removes the white flash (THEME-3 / D-046).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod clock;
mod commands;
mod config_file;
mod discord;
mod engine;
mod ignore_store;
mod paths;
mod prefs;
mod service;
mod sidecar;
mod state;
mod tray;
mod windows;

use tauri::Emitter;

fn main() {
    tauri::Builder::default()
        // A second launch signals this instance instead of starting a duplicate (D-005).
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            windows::open_settings(app);
        }))
        .plugin(
            tauri_plugin_window_state::Builder::default()
                // Restore the geometry and nothing else. The plugin can also store and restore
                // `decorated`, `visible` and `fullscreen`; all three are the app's to decide
                // (frameless by construction, hidden until the first paint, never fullscreen),
                // and a stale `decorated: true` from a build older than D-055 resurrects the
                // native caption on the next launch. `visible: false` would fight the no-flash
                // handshake in `windows.rs` as well.
                .with_state_flags(
                    tauri_plugin_window_state::StateFlags::SIZE
                        | tauri_plugin_window_state::StateFlags::POSITION
                        | tauri_plugin_window_state::StateFlags::MAXIMIZED,
                )
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(
            tauri_plugin_autostart::Builder::new()
                .app_name("Discord AutoRPC")
                .build(),
        )
        .manage(state::Shared::default())
        // Closing the Settings window must not end the process: this is a tray app, and the
        // tray is the only way to reach Quit (`TR-13`). Closing therefore *hides* the window,
        // and reopening it from the tray is instant because the webview is still warm.
        //
        // Resizes are also forwarded to the chrome so the maximize glyph can become a restore
        // glyph — the frontend has no other way to know (`D-055`).
        .on_window_event(|window, event| {
            match event {
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    if window.label() == windows::SETTINGS {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                }
                tauri::WindowEvent::Resized(_) => {
                    // Catches every path that changes the frame without going through our own
                    // commands: Tauri's injected double-click maximize, restoring from the
                    // taskbar, and anything the window manager does. Cheap and idempotent when
                    // the caption is already gone.
                    if let Ok(handle) = window.hwnd() {
                        windows::strip_caption(handle.0 as isize);
                    }

                    if window.label() == windows::SETTINGS {
                        let _ = window.emit(
                            "window-state",
                            state::WindowChrome {
                                maximized: window.is_maximized().unwrap_or(false),
                            },
                        );
                    }
                }
                _ => {}
            }
        })
        .setup(|app| {
            let handle = app.handle().clone();

            // D-047: fold any Python-era `ignore_list.json` entries into `config.ignored_exes`
            // before the UI can read the listing, so nothing is ever shown twice or hidden.
            match ignore_store::migrate() {
                Ok(0) => {}
                Ok(moved) => service::append_log_file(
                    "INFO",
                    "autorpc.ignore",
                    &format!(
                        "Moved {moved} entr{} from ignore_list.json into config.ignored_exes",
                        if moved == 1 { "y" } else { "ies" }
                    ),
                ),
                Err(error) => service::append_log_file(
                    "WARNING",
                    "autorpc.ignore",
                    &format!("Could not migrate ignore_list.json: {error}"),
                ),
            }

            tray::create(&handle)?;

            windows::open_settings(&handle);
            service::refresh_flags(&handle);
            engine::start(handle);

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::ready,
            commands::get_state,
            commands::get_config,
            commands::set_config,
            commands::reset_config,
            commands::export_config,
            commands::get_prefs,
            commands::set_prefs,
            commands::set_window_theme,
            commands::get_autostart,
            commands::set_autostart,
            commands::test_connection,
            commands::pause,
            commands::resume,
            commands::rename_app,
            commands::remove_override,
            commands::get_ignored,
            commands::ignore_app,
            commands::unignore_app,
            commands::get_built_ins,
            commands::seed_logs,
            commands::export_logs,
            commands::clear_icon_cache,
            commands::ui_log,
            commands::copy_text,
            commands::app_icon_url,
            commands::check_updates,
            commands::open_url,
            commands::open_log,
            commands::open_log_folder,
            commands::open_settings,
            commands::open_onboarding,
            commands::open_rename,
            commands::close_window,
            commands::minimize_window,
            commands::toggle_maximize,
        ])
        .build(tauri::generate_context!())
        .expect("error while running Discord AutoRPC")
        .run(|app, event| {
            // Tauri quits as soon as the last window closes. For a tray app that is wrong: the
            // tray is the *only* way to reach Quit (`TR-13`), so closing a window must leave the
            // process alive. An intentional exit carries a code (`app.exit(0)` from the tray) and
            // is allowed straight through; anything else is cancelled.
            if let tauri::RunEvent::ExitRequested { api, code, .. } = event {
                if code.is_none() {
                    api.prevent_exit();
                    return;
                }

                // A real quit: give the Python engine its chance to clear the presence and close
                // the RPC socket before its parent disappears (`T-022`).
                sidecar::shutdown(app);
            }
        });
}
