"""
detector.py — Foreground window detection with debounce and ignore logic.

Polls the foreground window every N seconds, resolves the owning process,
and applies ignore / whitelist / debounce rules before reporting.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil
import win32api
import win32con
import win32gui
import win32process

from context import extract_dynamic_tagline

logger = logging.getLogger("autorpc.detector")

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class AppInfo:
    """Snapshot of a detected foreground application."""
    exe_name: str          # e.g. "gta5.exe"
    exe_path: str          # full path to the executable
    window_title: str      # current window title text
    pid: int               # OS process id
    display_name: str = "" # resolved friendly name (filled later)
    tagline: str = ""      # contextual detail line (filled later)

    def __eq__(self, other):
        if not isinstance(other, AppInfo):
            return NotImplemented
        return self.exe_path.lower() == other.exe_path.lower()

    def __hash__(self):
        return hash(self.exe_path.lower())


# ---------------------------------------------------------------------------
# Display-name resolution
# ---------------------------------------------------------------------------

_CATEGORY_SUFFIX_REGEX = re.compile(
    r"\s*[-—–]?\s*("
    r"image editor|photo editor|"
    r"text editor|code editor|"
    r"media player|video player|audio player|music player|"
    r"spreadsheet software|word processor|"
    r"web browser|"
    r"client bootstrapper|client|"
    r"desktop app(?:lication)?|"
    r"for windows|"
    r"64-bit|x64|32-bit|x86"
    r")\s*$",
    re.IGNORECASE,
)


def _clean_display_name(text: str) -> str:
    """Strip marketing categories, platform tags, and architecture suffixes."""
    if not text:
        return ""
    t = text.strip()
    t = _CATEGORY_SUFFIX_REGEX.sub("", t).strip()
    return t


def _extract_pe_version_strings(exe_path: str) -> tuple[str | None, str | None]:
    """Pull (ProductName, FileDescription) from the exe's version-info resource."""
    try:
        lang_info = win32api.GetFileVersionInfo(exe_path, "\\VarFileInfo\\Translation")
        if not lang_info:
            return None, None
        lang, codepage = lang_info[0]

        query_desc = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
        query_prod = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\ProductName"

        desc = None
        prod = None

        try:
            d = win32api.GetFileVersionInfo(exe_path, query_desc)
            if d and d.strip():
                desc = d.strip()
        except Exception:
            pass

        try:
            p = win32api.GetFileVersionInfo(exe_path, query_prod)
            if p and p.strip():
                prod = p.strip()
        except Exception:
            pass

        return prod, desc
    except Exception:
        return None, None


def resolve_display_name(app: AppInfo, overrides: dict) -> str:
    """
    Determine the human-friendly name for an application.

    Priority:
      1. config.json overrides  (exact exe_name match, case-insensitive)
      2. Smart PE metadata (ProductName / cleaned FileDescription)
      3. exe filename without extension, Title Cased
    """
    key = app.exe_name.lower()
    if key in {k.lower(): k for k in overrides}:
        real_key = next(k for k in overrides if k.lower() == key)
        override = overrides[real_key]
        if isinstance(override, dict) and "name" in override:
            return override["name"]
        if isinstance(override, str):
            return override

    prod, desc = _extract_pe_version_strings(app.exe_path)

    # If FileDescription starts with ProductName (e.g. 'PhotoCraft image editor' starts with 'PhotoCraft'),
    # ProductName is the concise brand name!
    if prod and desc and desc.lower().startswith(prod.lower()) and len(prod) >= 3:
        clean_prod = _clean_display_name(prod)
        if clean_prod:
            return clean_prod

    # Otherwise, clean the FileDescription (strips suffixes like ' image editor', ' media player')
    if desc:
        clean_desc = _clean_display_name(desc)
        if clean_desc:
            return clean_desc

    # Fall back to cleaned ProductName if valid
    if prod:
        clean_prod = _clean_display_name(prod)
        if clean_prod and not clean_prod.endswith(".exe"):
            return clean_prod

    stem = Path(app.exe_name).stem
    return stem.replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------------------
# Tagline resolution
# ---------------------------------------------------------------------------

# Built-in taglines for known apps (exe name → tagline)
_BUILTIN_TAGLINES: dict[str, str] = {
    # Productivity / documents
    "notion.exe":           "Working on a document",
    "obsidian.exe":         "Taking notes",
    "onenote.exe":          "Taking notes",
    "winword.exe":          "Working on a document",
    "excel.exe":            "Crunching numbers",
    "powerpnt.exe":         "Making a presentation",
    "wordpad.exe":          "Editing a document",
    "notepad.exe":          "Editing a file",
    "notepad++.exe":        "Editing a file",
    # IDEs / code editors
    "code.exe":             "Working on a project",
    "devenv.exe":           "Working on a project",
    "idea64.exe":           "Working on a project",
    "pycharm64.exe":        "Working on a project",
    "webstorm64.exe":       "Working on a project",
    "rider64.exe":          "Working on a project",
    "clion64.exe":          "Working on a project",
    "goland64.exe":         "Working on a project",
    "sublime_text.exe":     "Working on a project",
    "atom.exe":             "Working on a project",
    "cursor.exe":           "Working on a project",
    "windsurf.exe":         "Working on a project",
    "antigravity ide.exe":  "Working on a project",
    "antigravity.exe":      "Working on a project",
    # Browsers
    "chrome.exe":           "Surfing the internet",
    "firefox.exe":          "Surfing the internet",
    "msedge.exe":           "Surfing the internet",
    "opera.exe":            "Surfing the internet",
    "brave.exe":            "Surfing the internet",
    "vivaldi.exe":          "Surfing the internet",
    "zen.exe":              "Surfing the internet",
    "arc.exe":              "Surfing the internet",
    # Media
    "vlc.exe":              "Watching something",
    "mpv.exe":              "Watching something",
    "mpc-hc64.exe":         "Watching something",
    "mpc-hc.exe":           "Watching something",
    "spotify.exe":          "Listening to music",
    "itunes.exe":           "Listening to music",
    "wmplayer.exe":         "Playing media",
    # Creative / design
    "photoshop.exe":        "Designing something",
    "illustrator.exe":      "Designing something",
    "figma.exe":            "Designing something",
    "blender.exe":          "Creating in 3D",
    "afterfx.exe":          "Editing a video",
    "premiere pro.exe":     "Editing a video",
    "davinci resolve.exe":  "Editing a video",
    # Communication
    "slack.exe":            "Chatting",
    "teams.exe":            "In a meeting",
    "telegram.exe":         "Chatting",
    "whatsapp.exe":         "Chatting",
    # Gaming platforms
    "steam.exe":            "Browsing games",
    "epicgameslauncher.exe":"Browsing games",
    # Terminals
    "windowsterminal.exe":  "In the terminal",
    "wt.exe":               "In the terminal",
    "powershell.exe":       "In the terminal",
    "cmd.exe":              "In the terminal",
    # File managers
    "totalcmd64.exe":       "Managing files",
    "totalcmd.exe":         "Managing files",
    "doublecmd.exe":        "Managing files",
}

# Keyword-based fallback categories (checked against exe name & display name)
_KEYWORD_TAGLINES: list[tuple[list[str], str]] = [
    (["studio", "ide", "code", "edit"],  "Working on a project"),
    (["browser", "web"],                 "Surfing the internet"),
    (["player", "media", "video"],       "Watching something"),
    (["game", "play"],                   "Playing a game"),
    (["chat", "messenger", "message"],   "Chatting"),
    (["terminal", "console", "shell"],   "In the terminal"),
    (["design", "draw", "paint"],        "Designing something"),
]


def built_in_taglines() -> dict[str, str]:
    """A copy of the shipped table, so a caller cannot edit it in place.

    The Tauri shell mirrors this read-only (`T-022`) rather than keeping a second copy of the
    same 58 strings, which would silently drift away from this one.
    """
    return dict(_BUILTIN_TAGLINES)


def resolve_tagline(app: AppInfo, config: dict) -> str:
    """
    Determine a contextual tagline for the details line.

    Priority:
      1. config.json overrides  ({"overrides": {"exe.exe": {"tagline": "..."}}})
      2. Dynamic Win32 semantic extraction (sheet names, web platforms, active files)
      3. config.json taglines   ({"taglines": {"exe.exe": "..."}})
      4. Built-in known-app table
      5. Keyword matching against exe name / display name
      6. Empty string (no details line shown)
    """
    key = app.exe_name.lower()

    # 1. Per-app override in overrides section
    overrides = config.get("overrides", {})
    for k, val in overrides.items():
        if k.lower() == key and isinstance(val, dict):
            tagline = val.get("tagline")
            if tagline:
                return tagline

    # 2. Dynamic Win32 semantic extraction
    dynamic = extract_dynamic_tagline(
        exe_name=app.exe_name,
        window_title=app.window_title,
        display_name=app.display_name,
        config=config,
    )
    if dynamic:
        return dynamic

    # 3. Dedicated taglines section
    taglines = config.get("taglines", {})
    for k, val in taglines.items():
        if k.lower() == key:
            return val

    # 4. Built-in table
    if key in _BUILTIN_TAGLINES:
        return _BUILTIN_TAGLINES[key]

    # 5. Keyword matching
    search_text = f"{key} {app.display_name}".lower()
    for keywords, tagline in _KEYWORD_TAGLINES:
        if any(kw in search_text for kw in keywords):
            return tagline

    # 6. No tagline
    return ""


# ---------------------------------------------------------------------------
# Ignore / whitelist helpers
# ---------------------------------------------------------------------------

from config import get_data_dir
_BASE_DIR = get_data_dir()


def _load_json_list(path: Path) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [s.lower() for s in data] if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def load_ignore_list() -> list[str]:
    return _load_json_list(_BASE_DIR / "ignore_list.json")


def save_ignore_list(items: list[str]) -> None:
    with open(_BASE_DIR / "ignore_list.json", "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def is_ignored(app: AppInfo, config: dict) -> bool:
    """Return True if the app should be silently skipped."""
    name_lower = app.exe_name.lower()
    path_lower = app.exe_path.lower()

    # System process — lives under C:\Windows
    win_dir = os.environ.get("SystemRoot", r"C:\Windows").lower()
    if path_lower.startswith(win_dir):
        return True

    # Static ignore list from config
    cfg_ignored = [x.lower() for x in config.get("ignored_exes", [])]
    if name_lower in cfg_ignored:
        return True

    # Dynamic ignore list (user-added via tray)
    user_ignored = load_ignore_list()
    if name_lower in user_ignored:
        return True

    # Whitelist mode — if enabled, only listed exes pass
    if config.get("whitelist_only", False):
        whitelist = [x.lower() for x in config.get("whitelist", [])]
        if name_lower not in whitelist:
            return True

    # Privacy protection: ignore Incognito / Private browsing windows
    if config.get("mask_private_browsing", True) and is_incognito(app):
        return True

    return False


_BROWSER_EXES = {
    "chrome.exe", "msedge.exe", "brave.exe", "firefox.exe",
    "opera.exe", "vivaldi.exe", "zen.exe", "arc.exe"
}


def is_incognito(app: AppInfo) -> bool:
    """Detect if a browser is in Private / Incognito mode from its window title."""
    if app.exe_name.lower() not in _BROWSER_EXES:
        return False
    t = app.window_title.lower()
    return (
        "incognito" in t
        or "inprivate" in t
        or "private browsing" in t
        or "(private)" in t
        or "private window" in t
    )


_DISCORD_EXES = {"discord.exe", "discordcanary.exe", "discordptb.exe", "discorddevelopment.exe"}


def _is_discord(app: AppInfo) -> bool:
    return app.exe_name.lower() in _DISCORD_EXES


def is_discord_running() -> bool:
    """True while a Discord desktop client is on the process list.

    Lives here rather than in an entry point because both entry points need it — the tray
    build's poll loop and the headless engine (`engine_stdio.py`) — and this module already
    knows Discord's exe names. `main._is_discord_running` used to be a copy of this.
    """
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name")
            if name and name.lower() in _DISCORD_EXES:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _is_process_alive(app: AppInfo) -> bool:
    try:
        p = psutil.Process(app.pid)
        return p.is_running() and p.name().lower() == app.exe_name.lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


# ---------------------------------------------------------------------------
# Core detector
# ---------------------------------------------------------------------------

class Detector:
    """
    Periodically checks the foreground window and returns a stable AppInfo
    after debounce, or None when nothing trackable is in focus.
    """

    def __init__(self, config: dict):
        self.config = config
        self.overrides = config.get("overrides", {})
        self.debounce_seconds: float = config.get("debounce_seconds", 10)
        self.idle_timeout: float = config.get("idle_timeout_seconds", 60)

        self._current_candidate: AppInfo | None = None
        self._candidate_since: float = 0.0
        self._confirmed_app: AppInfo | None = None
        self._last_real_app_time: float = 0.0   # when a real app was last confirmed

    # -- public interface --

    @property
    def confirmed(self) -> AppInfo | None:
        return self._confirmed_app

    def poll(self) -> AppInfo | None:
        """
        Sample the foreground window and run debounce logic.
        Returns the currently confirmed app (or None).
        """
        raw = self._get_foreground_app()

        # Special handling: When Discord itself is focused, keep showing the
        # last confirmed app as long as it's still running, and refresh the idle timer
        # so chatting or doing anything in Discord never clears your presence.
        if raw is not None and _is_discord(raw):
            if self._confirmed_app is not None:
                if _is_process_alive(self._confirmed_app):
                    self._last_real_app_time = time.time()
                    return self._confirmed_app
                else:
                    logger.info(
                        f"Previous app {self._confirmed_app.display_name} closed while in Discord — clearing presence"
                    )
                    self._confirmed_app = None
                    self._current_candidate = None
                    return None
            return None

        if raw is None or is_ignored(raw, self.config):
            # Foreground is ignored (desktop, taskbar, etc.) — keep last real app for idle_timeout
            if self._confirmed_app is not None:
                if time.time() - self._last_real_app_time > self.idle_timeout:
                    logger.info("Idle timeout reached — clearing presence")
                    self._confirmed_app = None
                    self._current_candidate = None
            return self._confirmed_app

        # We have a real (non-ignored) app in focus
        self._last_real_app_time = time.time()

        # Is it the same as the already-confirmed app?
        if raw == self._confirmed_app:
            # Update window title and re-evaluate dynamic tagline if window title changed
            if self._confirmed_app is not None:
                if self._confirmed_app.window_title != raw.window_title:
                    self._confirmed_app.window_title = raw.window_title
                    new_tagline = resolve_tagline(self._confirmed_app, self.config)
                    if new_tagline != self._confirmed_app.tagline:
                        self._confirmed_app.tagline = new_tagline
                        logger.info(
                            f"Context updated for {self._confirmed_app.display_name}: '{new_tagline}'"
                        )
            return self._confirmed_app

        # New candidate — check debounce
        if raw != self._current_candidate:
            self._current_candidate = raw
            self._candidate_since = time.time()
            return self._confirmed_app  # keep old one while debouncing

        elapsed = time.time() - self._candidate_since
        if elapsed >= self.debounce_seconds:
            # Candidate confirmed
            raw.display_name = resolve_display_name(raw, self.overrides)
            raw.tagline = resolve_tagline(raw, self.config)
            self._confirmed_app = raw
            self._current_candidate = None
            logger.info(f"App confirmed: {raw.display_name} ({raw.exe_name}) | tagline: '{raw.tagline}'")

        return self._confirmed_app

    # -- internals --

    def _get_foreground_app(self) -> AppInfo | None:
        """Return an AppInfo for the current foreground window, or None."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid <= 0:
                return None

            proc = psutil.Process(pid)
            exe_path = proc.exe()
            exe_name = proc.name()
            title = win32gui.GetWindowText(hwnd)

            if not exe_path or not exe_name:
                return None

            return AppInfo(
                exe_name=exe_name,
                exe_path=exe_path,
                window_title=title,
                pid=pid,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, Exception) as exc:
            logger.debug(f"Foreground detection failed: {exc}")
            return None
