//! The native tray icon and its menu (TR-1…TR-14).
//!
//! Tauri's tray menu is a real Win32 popup menu, so it is **plain text only** — no emoji, no
//! glyphs, no styling, and no per-item icons beyond what the OS draws (TR-3). Labels that
//! depend on state (`Pause`/`Resume`, `Rename Active App (… )`) are updated from
//! `service::push`, so the menu can never disagree with the Status pane.
//!
//! Left-click opens Settings (TR-14); the menu itself is on right-click only.

use std::sync::Mutex;

use tauri::menu::{MenuBuilder, MenuItem, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Wry};

use crate::state::{EngineState, ENGINE_PAUSED};
use crate::{ignore_store, service, windows};

pub struct TrayHandles {
    tray: TrayIcon<Wry>,
    rename_item: MenuItem<Wry>,
    pause_item: MenuItem<Wry>,
    ignore_item: MenuItem<Wry>,
    normal_icon: tauri::image::Image<'static>,
    paused_icon: tauri::image::Image<'static>,
    last_paused: Mutex<Option<bool>>,
}

pub fn create(app: &AppHandle) -> tauri::Result<()> {
    let version = MenuItemBuilder::with_id(
        "version",
        format!("Discord AutoRPC {}", env!("CARGO_PKG_VERSION")),
    )
    .enabled(false)
    .build(app)?;

    let settings = MenuItemBuilder::with_id("settings", "Settings").build(app)?;
    let rename_item = MenuItemBuilder::with_id("rename", "Rename Active App")
        .enabled(false)
        .build(app)?;
    let pause_item = MenuItemBuilder::with_id("pause", "Pause").build(app)?;
    let ignore_item = MenuItemBuilder::with_id("ignore", "Ignore current app")
        .enabled(false)
        .build(app)?;
    let open_log = MenuItemBuilder::with_id("log", "Open log file").build(app)?;
    let quit = MenuItemBuilder::with_id("quit", "Quit").build(app)?;

    let menu = MenuBuilder::new(app)
        .item(&version)
        .separator()
        .item(&settings)
        .separator()
        .item(&rename_item)
        .item(&pause_item)
        .item(&ignore_item)
        .separator()
        .item(&open_log)
        .item(&quit)
        .build()?;

    let base = tray_icon(app);
    let paused_icon = desaturate(&base);

    let tray = TrayIconBuilder::with_id("main")
        .icon(base.clone())
        .icon_as_template(false)
        .tooltip("Discord AutoRPC")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "settings" => windows::open_settings(app),
            "rename" => windows::open_rename(app),
            "pause" => {
                if service::is_paused(app) {
                    service::resume(app);
                } else {
                    service::pause(app);
                }
            }
            "ignore" => ignore_current(app),
            "log" => crate::commands::open_log_impl(app),
            "quit" => {
                // Recorded on the way out: otherwise a quit leaves no trace, and a vanishing
                // tray icon is indistinguishable from a crash.
                service::ui_log(app, "INFO", "autorpc.tray", "Quit requested from the tray menu");
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // Left click opens Settings; right click opens the menu (handled natively).
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                windows::open_settings(tray.app_handle());
            }
        })
        .build(app)?;

    app.manage(TrayHandles {
        tray,
        rename_item,
        pause_item,
        ignore_item,
        normal_icon: base,
        paused_icon,
        last_paused: Mutex::new(None),
    });

    Ok(())
}

/// Mirror engine state into the menu and the tooltip.
pub fn sync(app: &AppHandle, state: &EngineState) {
    let Some(handles) = app.try_state::<TrayHandles>() else {
        return;
    };

    let paused = state.engine == ENGINE_PAUSED;
    let _ = handles
        .pause_item
        .set_text(if paused { "Resume" } else { "Pause" });

    match state.app.as_ref() {
        Some(info) => {
            let _ = handles
                .rename_item
                .set_text(format!("Rename Active App ({})", info.display_name));
            let _ = handles.rename_item.set_enabled(true);
            let _ = handles.ignore_item.set_text(format!("Ignore {}", info.exe));
            let _ = handles.ignore_item.set_enabled(!info.ignored);
            let _ = handles
                .tray
                .set_tooltip(Some(format!("Discord AutoRPC — {}", info.display_name)));
        }
        None => {
            let _ = handles.rename_item.set_text("Rename Active App");
            let _ = handles.rename_item.set_enabled(false);
            let _ = handles.ignore_item.set_text("Ignore current app");
            let _ = handles.ignore_item.set_enabled(false);
            let _ = handles
                .tray
                .set_tooltip(Some("Discord AutoRPC — watching for apps"));
        }
    }

    // Icon swap only on change: the tray is a native resource, not a per-second repaint.
    let mut last = match handles.last_paused.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    };

    if *last != Some(paused) {
        let icon = if paused {
            handles.paused_icon.clone()
        } else {
            handles.normal_icon.clone()
        };
        let _ = handles.tray.set_icon(Some(icon));
        *last = Some(paused);
    }
}

fn ignore_current(app: &AppHandle) {
    let Some(info) = service::snapshot(app).app else {
        return;
    };

    // TR-12 / D-047: the tray writes the same list the Ignored Apps pane edits.
    if let Err(error) = ignore_store::add(&info.exe) {
        service::ui_log(app, "ERROR", "autorpc.tray", &error);
        return;
    }

    service::refresh_ignored(app);
    service::ui_log(
        app,
        "INFO",
        "autorpc.tray",
        &format!("{} added to the ignore list from the tray menu", info.exe),
    );
}

/// The tray icon, with a fallback chain so the tray can never end up invisible (D-004).
fn tray_icon(app: &AppHandle) -> tauri::image::Image<'static> {
    if let Some(icon) = app.default_window_icon() {
        return tauri::image::Image::new_owned(icon.rgba().to_vec(), icon.width(), icon.height());
    }

    if let Ok(icon) = tauri::image::Image::from_bytes(include_bytes!("../icons/icon.png")) {
        return icon;
    }

    // A visible grey square beats an invisible tray: the user can still reach Quit.
    let mut rgba = Vec::with_capacity(32 * 32 * 4);
    for _ in 0..(32 * 32) {
        rgba.extend_from_slice(&[90, 90, 96, 255]);
    }

    tauri::image::Image::new_owned(rgba, 32, 32)
}

/// A grey, slightly transparent copy of the tray icon for the paused state (TR-2).
///
/// Built at runtime so there is no second binary asset to keep in step with the first.
fn desaturate(icon: &tauri::image::Image<'_>) -> tauri::image::Image<'static> {
    let width = icon.width();
    let height = icon.height();
    let mut rgba = icon.rgba().to_vec();

    for pixel in rgba.chunks_exact_mut(4) {
        let luma = (0.2126 * f32::from(pixel[0]) + 0.7152 * f32::from(pixel[1]) + 0.0722 * f32::from(pixel[2])) as u8;
        pixel[0] = luma;
        pixel[1] = luma;
        pixel[2] = luma;
        pixel[3] = (f32::from(pixel[3]) * 0.7) as u8;
    }

    tauri::image::Image::new_owned(rgba, width, height)
}
