"""
config.py — Configuration loading, saving, validation, and defaults.
"""

import json
import logging
import os
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("autorpc.config")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
SHORTCUT_NAME = "DiscordAutoRPC.lnk"

DEFAULT_CONFIG: dict = {
    "application_id": "",
    "poll_interval": 5,
    "debounce_seconds": 10,
    "idle_timeout_seconds": 60,
    "default_icon_url": "https://cdn.discordapp.com/embed/avatars/0.png",
    "auto_close_with_discord": True,
    "mask_private_browsing": True,
    "whitelist_only": False,
    "whitelist": [],
    "ignored_exes": [
        "explorer.exe",
        "Discord.exe",
        "SearchHost.exe",
        "StartMenuExperienceHost.exe",
        "ShellExperienceHost.exe",
        "SystemSettings.exe",
        "ApplicationFrameHost.exe",
        "TextInputHost.exe",
        "LockApp.exe",
        "ScreenClippingHost.exe",
        "WidgetService.exe",
        "Widgets.exe",
    ],
    "taglines": {
        "notion.exe": "Working on a document",
        "antigravity ide.exe": "Working on a project",
        "chrome.exe": "Surfing the internet",
        "firefox.exe": "Surfing the internet",
        "msedge.exe": "Surfing the internet",
        "brave.exe": "Surfing the internet",
        "zen.exe": "Surfing the internet",
    },
    "overrides": {},
    "steamgriddb_api_key": "",
    "upload_host": "freeimage",
    "enable_dynamic_taglines": True,
}


def validate_app_id(app_id: str) -> Tuple[bool, str]:
    """Check if an Application ID is a valid Discord snowflake."""
    cleaned = str(app_id).strip()
    if not cleaned:
        return False, "Application ID cannot be empty."
    if cleaned in ("YOUR_DISCORD_APPLICATION_ID_HERE", "0"):
        return False, "Please enter your actual Discord Application ID."
    if not cleaned.isdigit():
        return False, "Application ID must contain numbers only."
    if not (17 <= len(cleaned) <= 21):
        return False, f"Discord Application IDs are 17–20 digits long (got {len(cleaned)} digits)."
    return True, ""


def is_configured(config: dict) -> bool:
    """Return True if config has a valid Application ID."""
    app_id = config.get("application_id", "")
    valid, _ = validate_app_id(app_id)
    return valid


def load_config() -> dict:
    """Load config.json, merging with default values to prevent missing keys."""
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Merge missing default keys
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except Exception as exc:
        logger.error(f"Error loading {CONFIG_PATH}: {exc}")
        return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> bool:
    """Save config dictionary to config.json."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as exc:
        logger.error(f"Failed to save {CONFIG_PATH}: {exc}")
        return False


def is_autostart_enabled() -> bool:
    """Check if shortcut exists in Windows Startup folder."""
    if not STARTUP_DIR.exists():
        return False
    return (STARTUP_DIR / SHORTCUT_NAME).exists() or (STARTUP_DIR / "DiscordAutoRPCWatcher.lnk").exists()


def set_autostart_enabled(enabled: bool) -> bool:
    """Enable or disable AutoRPC at Windows Startup."""
    try:
        shortcut_path = STARTUP_DIR / SHORTCUT_NAME
        legacy_path = STARTUP_DIR / "DiscordAutoRPCWatcher.lnk"

        if not enabled:
            if shortcut_path.exists():
                shortcut_path.unlink()
            if legacy_path.exists():
                legacy_path.unlink()
            return True

        # Create shortcut using Windows WScript.Shell
        import subprocess
        main_py = BASE_DIR / "main.py"
        powershell_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{shortcut_path}'); "
            f"$s.TargetPath = 'pythonw.exe'; "
            f"$s.Arguments = '\"{main_py}\"'; "
            f"$s.WorkingDirectory = '{BASE_DIR}'; "
            f"$s.WindowStyle = 7; "
            f"$s.Save()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", powershell_cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=True,
        )
        return True
    except Exception as exc:
        logger.error(f"Failed to toggle startup shortcut: {exc}")
        return False
