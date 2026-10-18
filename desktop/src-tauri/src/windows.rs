//! Window creation and the no-flash theme handshake.
//!
//! Three windows, three HTML entry points (SH-1):
//!
//! | label        | entry             | size          |
//! |--------------|-------------------|---------------|
//! | `settings`   | `index.html`      | 980×700, min 820×560 |
//! | `onboarding` | `onboarding.html` | 620×760, fixed |
//! | `rename`     | `rename.html`     | 520×600, fixed |
//!
//! The two auxiliary windows are 40 px taller than their content was designed for: the title
//! strip eats into the client area now that there is no native caption, and their layouts are
//! fixed, so the strip is paid for out of the window size rather than out of the content.
//!
//! **The caption has to be stripped by hand.** `decorations(false)` is not enough on Windows:
//! tao's backend keeps `WS_CAPTION` in the style it applies (the decorations flag only feeds
//! the `AdjustWindowRectEx` math), so a native title bar is drawn on top of the chrome the
//! frontend provides. `strip_caption` below removes the bits, and it is re-applied everywhere
//! tao might restore them.
//!
//! Every window is built **hidden** and only shown when the webview calls `ready` — that is
//! the first moment the theme is painted, so there is no white flash in either theme
//! (THEME-3 / D-046). A background thread is the safety net: if the frontend never calls
//! `ready`, the window still appears rather than looking like a crash.
//!
//! **All three windows are frameless** (`decorations(false)`, D-055): the native caption is
//! replaced by chrome the frontend draws — a drag region, the app/pane identity, and
//! minimize / maximize / close. Only the settings window is a "real window" in that sense;
//! onboarding and rename are fixed-size and get a close button alone.

use std::time::Duration;

use tauri::window::Color;
use tauri::{AppHandle, Manager, Theme, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::prefs;

pub const SETTINGS: &str = "settings";
pub const ONBOARDING: &str = "onboarding";
pub const RENAME: &str = "rename";

/// Matches `--bg` in `tokens.css` for each theme.
const LIGHT_BG: Color = Color(245, 245, 247, 255);
const DARK_BG: Color = Color(30, 30, 30, 255);

pub fn open_settings(app: &AppHandle) {
    focus_or_build(
        app,
        SETTINGS,
        "Discord AutoRPC",
        "index.html",
        980.0,
        700.0,
        Some((820.0, 560.0)),
        true,
    );
}

pub fn open_onboarding(app: &AppHandle) {
    focus_or_build(
        app,
        ONBOARDING,
        "Set up Discord AutoRPC",
        "onboarding.html",
        620.0,
        760.0,
        None,
        false,
    );
}

pub fn open_rename(app: &AppHandle) {
    focus_or_build(
        app,
        RENAME,
        "Rename Active App",
        "rename.html",
        520.0,
        600.0,
        None,
        false,
    );
}

fn focus_or_build(
    app: &AppHandle,
    label: &str,
    title: &str,
    entry: &str,
    width: f64,
    height: f64,
    min_size: Option<(f64, f64)>,
    resizable: bool,
) {
    if let Some(window) = app.get_webview_window(label) {
        let _ = window.unminimize();
        let _ = window.show();
        // `unminimize` and `show` are flag changes, so tao has just rebuilt the style and put
        // the caption back; without this, reopening Settings from the tray would look different
        // from opening it for the first time.
        strip_caption_of(&window);
        let _ = window.set_focus();
        return;
    }

    let mut builder = WebviewWindowBuilder::new(app, label, WebviewUrl::App(entry.into()))
        .title(title)
        .inner_size(width, height)
        .resizable(resizable)
        // D-055: no native caption. The taskbar still shows `title`, and the OS still owns
        // edge-resizing and Aero Snap — only the title bar is ours.
        .decorations(false)
        // Aux windows are fixed-size dialogs, so they refuse minimize/maximize as well;
        // otherwise double-clicking their drag region would maximize a 520 px dialog.
        .maximizable(resizable)
        .minimizable(resizable)
        .visible(false)
        .center();

    if let Some((min_width, min_height)) = min_size {
        builder = builder.min_inner_size(min_width, min_height);
    }

    let Ok(window) = builder.build() else {
        return;
    };

    // The window is built hidden, so this is invisible; it just means the first frame that
    // appears is already frameless.
    strip_caption_of(&window);

    // Paint the frame and the pre-paint background in the saved theme, but stay hidden.
    apply_theme(&window, &prefs::load().appearance);

    let fallback = window.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(4));
        let _ = fallback.show();
        strip_caption_of(&fallback);
    });
}

/// Called from the frontend once its first paint is done, with the saved preference.
pub fn show_with_theme(window: &WebviewWindow, appearance: &str) {
    apply_theme(window, appearance);
    let _ = window.show();
    // `show()` is a window-flag change, and tao rebuilds the whole style when flags change,
    // which puts the caption back. Strip it again after every show.
    strip_caption_of(window);
    let _ = window.set_focus();
}

/// Set both the OS window theme (titlebar, native menus, scrollbars) and the webview's
/// background colour, so the frame and the page agree before anything is painted.
///
/// `system` passes `None`: the OS keeps deciding, which is what makes a live theme switch
/// while the window is open work without the app polling (THEME-4).
pub fn apply_theme(window: &WebviewWindow, appearance: &str) {
    let (theme, background) = match appearance {
        prefs::LIGHT => (Some(Theme::Light), Some(LIGHT_BG)),
        prefs::DARK => (Some(Theme::Dark), Some(DARK_BG)),
        _ => (None, None),
    };

    let _ = window.set_theme(theme);
    let _ = window.set_background_color(background);
}

/* --------------------------------------------------- frameless window --- */

// `decorations(false)` does not remove the caption on Windows. tao's backend always starts the
// applied style from `WS_CAPTION | WS_CLIPSIBLINGS | WS_SYSMENU` and only consults the
// decorations flag for the `AdjustWindowRectEx` math and for child windows — see
// `tao/platform_impl/windows/window_state.rs::to_window_styles`. The observed result was a
// native title bar, in the system's dark theme, sitting directly above the toolbar the
// frontend draws (D-055).
//
// Worse, this is not a one-time fix: `WindowState::apply_diff` rebuilds the entire style from
// `to_window_styles()` on *any* flag change, so showing, maximizing, minimizing and restoring
// all put the caption back. Every entry point is therefore covered — creation, each `show()`,
// our own maximize command, and every `Resized` event (which catches Tauri's injected
// double-click maximize and anything the OS does).

const GWL_STYLE: i32 = -16;
/// `WS_BORDER | WS_DLGFRAME`: together they are what a caption is made of.
const WS_CAPTION: isize = 0x00C0_0000;

const SWP_NOSIZE: u32 = 0x0001;
const SWP_NOMOVE: u32 = 0x0002;
const SWP_NOZORDER: u32 = 0x0004;
const SWP_NOACTIVATE: u32 = 0x0010;
const SWP_FRAMECHANGED: u32 = 0x0020;

extern "system" {
    fn GetWindowLongPtrW(hwnd: isize, index: i32) -> isize;
    fn SetWindowLongPtrW(hwnd: isize, index: i32, value: isize) -> isize;
    fn SetWindowPos(
        hwnd: isize,
        insert_after: isize,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
        flags: u32,
    ) -> i32;
}

/// Clear `WS_CAPTION` on `hwnd`, leaving every other style bit — including `WS_SIZEBOX` for
/// resizable windows — exactly as it was.
///
/// Takes a raw handle rather than a window type because the resize event hands out a
/// `tauri::Window` while creation has a `WebviewWindow`, and the two are not interchangeable.
pub fn strip_caption(hwnd: isize) {
    // SAFETY: both calls only read or write one window-style value for a handle this process
    // owns, and the `SetWindowPos` flags ask for no move, no resize and no z-order change.
    unsafe {
        let style = GetWindowLongPtrW(hwnd, GWL_STYLE);

        // Nothing to do in the common case: a resize fires this dozens of times per drag, and
        // a `SetWindowPos` inside a `WM_SIZE` handler would be a re-entrant resize each time.
        if style & WS_CAPTION == 0 {
            return;
        }

        SetWindowLongPtrW(hwnd, GWL_STYLE, style & !WS_CAPTION);
        SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        );
    }
}

/// `strip_caption` for the windows this module creates. `HWND` is a newtype over a pointer and
/// is only reachable through `hwnd()`, so the conversion lives here once.
pub fn strip_caption_of(window: &WebviewWindow) {
    if let Ok(handle) = window.hwnd() {
        strip_caption(handle.0 as isize);
    }
}
