"""
main.py — Discord AutoRPC entry point.

Runs a system-tray icon (PyQt6) with a background thread that
polls the foreground window and updates Discord Rich Presence.

`--engine-stdio` is a second, headless entry point: the Tauri shell in `desktop/` spawns this
file with that flag and drives the same detection pipeline over JSON lines on stdin/stdout
(see `engine_stdio.py`). That branch runs before the Qt imports below, so it never loads
PyQt6 and never takes the tray app's single-instance mutex — the two can coexist.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import io
import webbrowser

# Headless engine mode (`T-022`). Handled *here*, above the Qt imports, so the sidecar the
# desktop shell spawns never loads PyQt6 — and above the single-instance mutex, which belongs
# to the tray app this process deliberately is not.
if "--engine-stdio" in sys.argv:
    from engine_stdio import run

    sys.exit(run())

import psutil
import win32api
import win32event
import winerror
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config import load_config, is_configured, CONFIG_PATH, get_data_dir
from detector import Detector, AppInfo, is_discord_running, load_ignore_list, save_ignore_list
from gui import (
    run_onboarding_wizard,
    open_settings_gui,
    open_quick_rename_gui,
    _ensure_qapp,
    DISCORD_DARK_QSS,
    ICON_PATH,
)
from icons import get_icon_url
from presence import PresenceManager
from updater import __version__, check_updates_async

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = get_data_dir() / "config.json"
LOG_PATH = get_data_dir() / "autorpc.log"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler: 2 MB × 3 backups
    fh = RotatingFileHandler(
        LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler (only when running with a visible console)
    if sys.stdout and hasattr(sys.stdout, "write"):
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        root.addHandler(ch)


logger = logging.getLogger("autorpc.main")




# ---------------------------------------------------------------------------
# Tray icon image (generated in-memory)
# ---------------------------------------------------------------------------
def _make_tray_icon(paused: bool = False) -> Image.Image:
    """Generate a simple 64×64 tray icon."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer circle — Discord blurple when active, grey when paused
    fill = (88, 101, 242) if not paused else (120, 120, 120)
    draw.ellipse([4, 4, size - 4, size - 4], fill=fill)

    # Inner "play" triangle or "pause" bars
    if not paused:
        # Play triangle
        draw.polygon([(24, 18), (24, 46), (48, 32)], fill=(255, 255, 255))
    else:
        # Pause bars
        draw.rectangle([22, 18, 28, 46], fill=(255, 255, 255))
        draw.rectangle([36, 18, 42, 46], fill=(255, 255, 255))

    return img


def _make_qt_tray_icon(paused: bool = False) -> QIcon:
    """Return a native QIcon for the system tray."""
    if not paused and ICON_PATH.exists():
        return QIcon(str(ICON_PATH))
    img = _make_tray_icon(paused=paused)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    pix = QPixmap()
    pix.loadFromData(buf.getvalue(), "PNG")
    return QIcon(pix)


# ---------------------------------------------------------------------------
# Main loop (runs in a daemon thread)
# ---------------------------------------------------------------------------
class JsonReloader:
    """Reload config.json periodically so changes take effect without restart."""
    def __init__(self, interval: float = 30.0):
        self.interval = interval
        self._last_load: float = 0
        self._config: dict = {}

    def get(self) -> dict:
        now = time.time()
        if now - self._last_load > self.interval:
            self._config = load_config()
            self._last_load = now
        return self._config


class TrayBridge(QObject):
    set_visible_signal = pyqtSignal(bool)
    show_settings_signal = pyqtSignal()
    set_tooltip_signal = pyqtSignal(str)

    def __init__(self, tray: QSystemTrayIcon):
        super().__init__()
        self.tray = tray
        self.set_visible_signal.connect(self._on_set_visible)
        self.show_settings_signal.connect(self._on_show_settings)
        self.set_tooltip_signal.connect(self._on_set_tooltip)

    def _on_set_visible(self, visible: bool):
        if visible:
            self.tray.show()
        else:
            self.tray.hide()

    def _on_set_tooltip(self, tip: str):
        self.tray.setToolTip(tip)

    def _on_show_settings(self):
        open_settings_gui()


def _poll_loop(
    state: dict,          # shared mutable state
    presence: PresenceManager,
    bridge: TrayBridge,
    wakeup_event=None,
) -> None:
    """Background polling loop with auto Discord lifecycle sync."""
    reloader = JsonReloader()
    was_discord_active = None

    while not state["quit"]:
        if state["paused"]:
            time.sleep(1)
            continue

        config = reloader.get()
        poll_interval = config.get("poll_interval", 5)
        auto_close = config.get("auto_close_with_discord", True)

        discord_running = is_discord_running()

        if not discord_running:
            if auto_close:
                # If Discord was previously active and just closed, or if started dormant on system startup
                if was_discord_active is True or (was_discord_active is None and state.get("is_startup", False)):
                    logger.info("Discord is closed. AutoRPC entering dormant standby mode (hidden tray)...")
                    presence.close()
                    bridge.set_visible_signal.emit(False)
                    state["dormant"] = True
                    was_discord_active = False

                elif was_discord_active is None and not state.get("is_startup", False):
                    bridge.set_tooltip_signal.emit("Discord AutoRPC — Waiting for Discord...")
                    was_discord_active = False

                # Dormant sleep loop: wait quietly until Discord launches or app quits
                while not state["quit"]:
                    time.sleep(2)
                    if wakeup_event and win32event.WaitForSingleObject(wakeup_event, 0) == win32event.WAIT_OBJECT_0:
                        bridge.set_visible_signal.emit(True)
                        bridge.show_settings_signal.emit()

                    if is_discord_running():
                        logger.info("Discord detected! Restoring system tray icon and reconnecting Rich Presence...")
                        bridge.set_tooltip_signal.emit("Discord AutoRPC")
                        bridge.set_visible_signal.emit(True)
                        state["dormant"] = False
                        was_discord_active = True
                        presence.connect(force=True)
                        break
                continue
            else:
                presence.clear()
                bridge.set_tooltip_signal.emit("Discord AutoRPC — Discord not running")
                time.sleep(poll_interval)
                continue

        # If discord is running and we just saw it start
        if was_discord_active is not True:
            was_discord_active = True
            bridge.set_tooltip_signal.emit("Discord AutoRPC")
            bridge.set_visible_signal.emit(True)
            state["dormant"] = False
            presence.connect(force=True)

        # Check for wakeup event from second instance
        if wakeup_event and win32event.WaitForSingleObject(wakeup_event, 0) == win32event.WAIT_OBJECT_0:
            bridge.set_visible_signal.emit(True)
            bridge.show_settings_signal.emit()

        # Lazy-create or re-create detector when config changes
        if state.get("_detector") is None:
            state["_detector"] = Detector(config)
        detector: Detector = state["_detector"]
        detector.config = config
        detector.overrides = config.get("overrides", {})

        app = detector.poll()
        state["current_app"] = app

        if app is not None:
            icon_url = get_icon_url(app.exe_path, app.display_name, config)
            presence.update(
                display_name=app.display_name,
                icon_url=icon_url,
                exe_path=app.exe_path,
                pid=app.pid,
                tagline=app.tagline,
            )
        else:
            presence.clear()

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Native Qt System Tray & Menu
# ---------------------------------------------------------------------------

def _create_qt_tray(state: dict, presence: PresenceManager, app: QApplication) -> tuple[QSystemTrayIcon, TrayBridge]:
    tray = QSystemTrayIcon(_make_qt_tray_icon(), app)
    tray.setToolTip("Discord AutoRPC")
    bridge = TrayBridge(tray)

    menu = QMenu()
    menu.setStyleSheet(DISCORD_DARK_QSS)

    # 1. Update / Version Action
    update_action = QAction(f"Discord AutoRPC v{__version__}", menu)
    update_action.setEnabled(False)
    def _open_update():
        if state.get("update_url"):
            webbrowser.open(state["update_url"])
    update_action.triggered.connect(_open_update)
    menu.addAction(update_action)

    menu.addSeparator()

    # 2. Settings Action
    settings_action = QAction("⚙️ Settings", menu)
    def _open_settings():
        open_settings_gui(on_saved=lambda cfg: state.update({"_detector": None}))
    settings_action.triggered.connect(_open_settings)
    menu.addAction(settings_action)

    menu.addSeparator()

    # 3. Rename Active App Action
    rename_action = QAction("🏷️ Rename Active App...", menu)
    def _rename_cur():
        cur = state.get("current_app")
        if cur:
            def _on_rename_saved(cfg, new_name, new_tagline):
                state["_detector"] = None
                cur.display_name = new_name
                if new_tagline:
                    cur.tagline = new_tagline
                icon_url = get_icon_url(cur.exe_path, new_name, cfg)
                presence.update(
                    display_name=new_name,
                    icon_url=icon_url,
                    exe_path=cur.exe_path,
                    pid=cur.pid,
                    tagline=cur.tagline,
                )
            open_quick_rename_gui(
                exe_name=cur.exe_name,
                current_name=cur.display_name,
                current_tagline=cur.tagline,
                on_saved=_on_rename_saved,
            )
    rename_action.triggered.connect(_rename_cur)
    menu.addAction(rename_action)

    # 4. Pause / Resume Action
    pause_action = QAction("⏸ Pause", menu)
    def _toggle_pause():
        state["paused"] = not state["paused"]
        if state["paused"]:
            presence.clear()
            pause_action.setText("▶ Resume")
        else:
            pause_action.setText("⏸ Pause")
        tray.setIcon(_make_qt_tray_icon(paused=state["paused"]))
        logger.info("Paused" if state["paused"] else "Resumed")
    pause_action.triggered.connect(_toggle_pause)
    menu.addAction(pause_action)

    # 5. Ignore Current App Action
    ignore_action = QAction("🚫 Ignore current app", menu)
    def _ignore_cur():
        cur = state.get("current_app")
        if cur:
            ignored = load_ignore_list()
            exe_lower = cur.exe_name.lower()
            if exe_lower not in ignored:
                ignored.append(exe_lower)
                save_ignore_list(ignored)
                logger.info(f"Added {cur.exe_name} to ignore list")
                state["_detector"] = None
    ignore_action.triggered.connect(_ignore_cur)
    menu.addAction(ignore_action)

    menu.addSeparator()

    # 6. Open Log Action
    log_action = QAction("📋 Open log", menu)
    def _open_log():
        try:
            os.startfile(str(LOG_PATH))
        except Exception:
            subprocess.Popen(["notepad.exe", str(LOG_PATH)])
    log_action.triggered.connect(_open_log)
    menu.addAction(log_action)

    # 7. Quit Action
    quit_action = QAction("❌ Quit", menu)
    def _quit_app():
        state["quit"] = True
        presence.close()
        tray.hide()
        logger.info("AutoRPC quit")
        app.quit()
    quit_action.triggered.connect(_quit_app)
    menu.addAction(quit_action)

    # Dynamic menu update before showing
    def _update_menu_state():
        cur = state.get("current_app")
        if cur:
            rename_action.setText(f"🏷️ Rename Active App ({cur.display_name})...")
            rename_action.setEnabled(True)
            ignore_action.setText(f"🚫 Ignore {cur.exe_name}")
            ignore_action.setEnabled(True)
        else:
            rename_action.setText("🏷️ Rename Active App...")
            rename_action.setEnabled(False)
            ignore_action.setText("🚫 Ignore current app")
            ignore_action.setEnabled(False)

        if state.get("update_url"):
            update_action.setText(f"⭐ Update to v{state['latest_tag']}")
            update_action.setEnabled(True)

    menu.aboutToShow.connect(_update_menu_state)

    # Click / Double-click on tray opens Settings
    def _on_activated(reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            open_settings_gui(on_saved=lambda cfg: state.update({"_detector": None}))

    tray.activated.connect(_on_activated)
    tray.setContextMenu(menu)
    if not state.get("dormant", False):
        tray.show()
    return tray, bridge


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _setup_logging()
    logger.info("=" * 50)
    logger.info("Discord AutoRPC starting")

    # Single-instance mutex check
    MUTEX_NAME = "DiscordAutoRPC_SingleInstance_Mutex"
    EVENT_NAME = "DiscordAutoRPC_Wakeup_Event"

    h_mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        logger.info("Another instance of Discord AutoRPC is already running. Signaling wake up...")
        try:
            h_event = win32event.OpenEvent(win32event.EVENT_MODIFY_STATE, False, EVENT_NAME)
            if h_event:
                win32event.SetEvent(h_event)
                win32api.CloseHandle(h_event)
        except Exception:
            pass
        sys.exit(0)

    wakeup_event = win32event.CreateEvent(None, False, False, EVENT_NAME)

    # Initialize Qt on the main thread FIRST
    app = _ensure_qapp()
    app.setQuitOnLastWindowClosed(False)

    config = load_config()

    # First-Run Experience: Launch guided setup wizard if unconfigured
    if not is_configured(config):
        logger.info("No valid Application ID found. Launching Setup Wizard...")
        config = run_onboarding_wizard()
        if not config or not is_configured(config):
            logger.info("Setup wizard canceled or closed. Exiting.")
            sys.exit(0)

    app_id = config.get("application_id", "")
    presence = PresenceManager(app_id)

    is_startup = "--startup" in sys.argv
    discord_running = is_discord_running()
    auto_close = config.get("auto_close_with_discord", True)
    start_dormant = is_startup and not discord_running and auto_close

    # Shared state between tray and background thread
    state: dict = {
        "quit": False,
        "paused": False,
        "current_app": None,
        "_detector": None,
        "latest_tag": None,
        "update_url": None,
        "app_qt": app,
        "dormant": start_dormant,
        "is_startup": is_startup,
    }

    # Asynchronously check for GitHub updates
    def _on_update_found(tag, url):
        state["latest_tag"] = tag
        state["update_url"] = url
        logger.info(f"New release available: v{tag}")

    check_updates_async(_on_update_found)

    # Native Qt System Tray Icon & Bridge
    tray, bridge = _create_qt_tray(state, presence, app)
    state["tray"] = tray
    state["bridge"] = bridge

    # Start the polling thread
    poll_thread = threading.Thread(
        target=_poll_loop, args=(state, presence, bridge, wakeup_event), daemon=True
    )
    poll_thread.start()

    # Run Qt Event Loop on the Main Thread
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
