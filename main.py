"""
main.py — Discord AutoRPC entry point.

Runs a system-tray icon (pystray) with a background thread that
polls the foreground window and updates Discord Rich Presence.
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

import webbrowser

import psutil
import pystray
from PIL import Image, ImageDraw

from config import load_config, is_configured, CONFIG_PATH
from detector import Detector, AppInfo, load_ignore_list, save_ignore_list
from gui import run_onboarding_wizard, open_settings_gui
from icons import get_icon_url
from presence import PresenceManager
from updater import __version__, check_updates_async

# `---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
LOG_PATH = BASE_DIR / "autorpc.log"


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




def _is_discord_running() -> bool:
    """Check if any Discord desktop client is currently running."""
    discord_names = {"discord.exe", "discordcanary.exe", "discordptb.exe", "discorddevelopment.exe"}
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name")
            if name and name.lower() in discord_names:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _poll_loop(
    state: dict,          # shared mutable state
    presence: PresenceManager,
) -> None:
    """Background polling loop."""
    reloader = JsonReloader()

    while not state["quit"]:
        if state["paused"]:
            time.sleep(1)
            continue

        config = reloader.get()
        poll_interval = config.get("poll_interval", 5)

        # Discord process lifecycle check
        discord_running = _is_discord_running()
        if not discord_running:
            if config.get("auto_close_with_discord", False):
                logger.info("Discord is closed and auto_close_with_discord is enabled. Exiting AutoRPC...")
                state["quit"] = True
                presence.close()
                tray = state.get("tray")
                if tray:
                    try:
                        tray.stop()
                    except Exception:
                        pass
                break
            else:
                presence.clear()
                time.sleep(poll_interval)
                continue

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
# Tray menu actions
# ---------------------------------------------------------------------------

def _make_menu(state, tray, presence):
    def toggle_pause(icon, item):
        state["paused"] = not state["paused"]
        if state["paused"]:
            presence.clear()
        icon.icon = _make_tray_icon(paused=state["paused"])
        logger.info("Paused" if state["paused"] else "Resumed")

    def ignore_current(icon, item):
        app: AppInfo | None = state.get("current_app")
        if app is None:
            logger.info("No current app to ignore")
            return
        ignored = load_ignore_list()
        exe_lower = app.exe_name.lower()
        if exe_lower not in ignored:
            ignored.append(exe_lower)
            save_ignore_list(ignored)
            logger.info(f"Added {app.exe_name} to ignore list")
            # Force detector to re-evaluate
            state["_detector"] = None

    def open_config(icon, item):
        try:
            os.startfile(str(CONFIG_PATH))
        except Exception:
            subprocess.Popen(["notepad.exe", str(CONFIG_PATH)])

    def open_settings(icon, item):
        def _launch():
            try:
                def _on_save(new_cfg):
                    state["_detector"] = None
                open_settings_gui(on_saved=_on_save)
            except Exception as exc:
                logger.error(f"Failed to open settings window: {exc}")
        threading.Thread(target=_launch, daemon=True).start()

    def open_log(icon, item):
        try:
            os.startfile(str(LOG_PATH))
        except Exception:
            subprocess.Popen(["notepad.exe", str(LOG_PATH)])

    def quit_app(icon, item):
        state["quit"] = True
        presence.close()
        icon.stop()
        logger.info("AutoRPC quit")

    return pystray.Menu(
        pystray.MenuItem(
            lambda item: f"⭐ Update to v{state['latest_tag']}" if state.get("update_url") else f"Discord AutoRPC v{__version__}",
            lambda icon, item: webbrowser.open(state.get("update_url", "https://github.com/yashkthakor/Discord-AutoRPC/releases")) if state.get("update_url") else None,
            enabled=lambda item: bool(state.get("update_url")),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("⚙️ Settings", open_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda item: "▶ Resume" if state["paused"] else "⏸ Pause",
            toggle_pause,
        ),
        pystray.MenuItem("🚫 Ignore current app", ignore_current),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("📋 Open log", open_log),
        pystray.MenuItem("❌ Quit", quit_app),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _setup_logging()
    logger.info("=" * 50)
    logger.info("Discord AutoRPC starting")

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

    # Shared state between tray and background thread
    state: dict = {
        "quit": False,
        "paused": False,
        "current_app": None,
        "_detector": None,
        "latest_tag": None,
        "update_url": None,
    }

    # Asynchronously check for GitHub updates
    def _on_update_found(tag, url):
        state["latest_tag"] = tag
        state["update_url"] = url
        logger.info(f"New release available: v{tag}")

    check_updates_async(_on_update_found)

    # Start the polling thread
    poll_thread = threading.Thread(
        target=_poll_loop, args=(state, presence), daemon=True
    )
    poll_thread.start()

    # System tray icon (blocks on the main thread)
    tray = pystray.Icon("AutoRPC")
    tray.icon = _make_tray_icon()
    tray.title = "Discord AutoRPC"
    tray.menu = _make_menu(state, tray, presence)
    state["tray"] = tray
    tray.run()


if __name__ == "__main__":
    main()
