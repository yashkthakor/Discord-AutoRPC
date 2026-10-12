"""
context.py — Smart Win32 Window Title Semantic Extractor for Discord AutoRPC.

Extracts dynamic, human-friendly contextual taglines from raw OS window titles:
  • Excel / Word / Office: "Editing Receipt List", "Editing Q4 Proposal"
  • Notion / Obsidian: "Document: Roadmap", "Note: Daily Tasks"
  • Web Browsers (Zen, Chrome, Firefox, Edge): "Watching YouTube", "Reviewing code on GitHub"
  • Code Editors / IDEs: "detector.py (Discord AutoRPC)"
  • Media Players (Spotify, VLC): "🎵 Daft Punk - One More Time", "Watching Interstellar"

Features built-in noise stripping, privacy safeguards, and 128-char bound protection.
"""

import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Noise Stripping Helpers
# ---------------------------------------------------------------------------

# Leading unread notification counts: e.g. "(4) ", "(99+) "
_RE_NOTIFICATION_BADGE = re.compile(r"^\(\d+[\+]?\)\s*")

# Dirty buffer / unsaved file marks: e.g. "● ", "* ", "• "
_RE_DIRTY_MARK = re.compile(r"^[●\*•]\s*")

# Standard browser suffixes
_BROWSER_SUFFIXES = [
    re.compile(r"\s*[-—–]\s*Zen Browser$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Google Chrome$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Mozilla Firefox$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Microsoft\s*Edge$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Brave$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Opera( GX)?$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Vivaldi$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Arc$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Chromium$", re.IGNORECASE),
]

# Standard IDE / Editor suffixes
_IDE_SUFFIXES = [
    re.compile(r"\s*[-—–]\s*Visual Studio Code$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Antigravity IDE$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Antigravity$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Cursor$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Windsurf$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*Sublime Text$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*PyCharm.*$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*IntelliJ IDEA.*$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*WebStorm.*$", re.IGNORECASE),
    re.compile(r"\s*[-—–]\s*CLion.*$", re.IGNORECASE),
]


def _clean_title(title: str) -> str:
    """Strip notification numbers and unsaved file markers."""
    t = title.strip()
    t = _RE_NOTIFICATION_BADGE.sub("", t)
    t = _RE_DIRTY_MARK.sub("", t)
    return t.strip()


def _truncate(text: str, max_len: int = 120) -> str:
    """Ensure tagline fits safely within Discord RPC 128-char limits."""
    text = text.strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# Curated Browser Platform Recognizers
# ---------------------------------------------------------------------------

_BROWSER_PLATFORMS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bYouTube\b", re.I), "Watching YouTube"),
    (re.compile(r"\bTwitch\b", re.I), "Watching Twitch"),
    (re.compile(r"\bNetflix\b", re.I), "Watching Netflix"),
    (re.compile(r"\bDisney\+?\b", re.I), "Watching Disney+"),
    (re.compile(r"\bPrime Video\b", re.I), "Watching Prime Video"),
    (re.compile(r"\bCrunchyroll\b", re.I), "Watching Crunchyroll"),
    (re.compile(r"\bSpotify\b", re.I), "Listening on Spotify"),
    (re.compile(r"\bSoundCloud\b", re.I), "Listening on SoundCloud"),
    (re.compile(r"\bGitHub\b", re.I), "Reviewing code on GitHub"),
    (re.compile(r"\bGitLab\b", re.I), "Reviewing code on GitLab"),
    (re.compile(r"\bReddit\b", re.I), "Browsing Reddit"),
    (re.compile(r"\b(Twitter|X(?:\.com)?)\b", re.I), "Browsing X / Twitter"),
    (re.compile(r"\bChatGPT\b", re.I), "Prompting ChatGPT"),
    (re.compile(r"\bClaude\b", re.I), "Prompting Claude"),
    (re.compile(r"\bGemini\b", re.I), "Prompting Gemini"),
    (re.compile(r"\bStack Overflow\b", re.I), "Browsing Stack Overflow"),
    (re.compile(r"\bWikipedia\b", re.I), "Reading Wikipedia"),
    (re.compile(r"\bGoogle Docs\b", re.I), "Editing Google Doc"),
    (re.compile(r"\bGoogle Sheets\b", re.I), "Editing Google Sheet"),
    (re.compile(r"\bGoogle Slides\b", re.I), "Editing Google Slides"),
    (re.compile(r"\bGoogle Search\b", re.I), "Searching the web"),
    (re.compile(r"\b(Gmail|Google Mail)\b", re.I), "Checking emails"),
    (re.compile(r"\bOutlook\b", re.I), "Checking emails"),
    (re.compile(r"\bLinkedIn\b", re.I), "Browsing LinkedIn"),
    (re.compile(r"\bPinterest\b", re.I), "Browsing Pinterest"),
    (re.compile(r"\bMedium\b", re.I), "Reading on Medium"),
    (re.compile(r"\bSubstack\b", re.I), "Reading on Substack"),
]

_BROWSER_EXES = {
    "zen.exe",
    "chrome.exe",
    "firefox.exe",
    "msedge.exe",
    "brave.exe",
    "opera.exe",
    "operagx.exe",
    "vivaldi.exe",
    "arc.exe",
    "chromium.exe",
    "waterfox.exe",
}


def _parse_browser(title: str) -> str:
    cleaned = _clean_title(title)
    if not cleaned:
        return "Surfing the internet"

    # 1. Match curated platform
    for pattern, tagline in _BROWSER_PLATFORMS:
        if pattern.search(cleaned):
            return tagline

    # 2. Strip browser brand name from end
    t = cleaned
    for suff in _BROWSER_SUFFIXES:
        t = suff.sub("", t).strip()

    # If something clean remains (e.g. "Hacker News" or "Product Hunt")
    parts = re.split(r"\s*[-—–]\s*", t)
    candidate = parts[-1].strip() if parts else t
    # Sanitize: avoid displaying email addresses or huge URLs
    if candidate and len(candidate) <= 35 and "@" not in candidate and "/" not in candidate:
        if not candidate.lower().startswith("http"):
            return _truncate(f"Browsing {candidate}")

    return "Surfing the internet"


# ---------------------------------------------------------------------------
# Office / Spreadsheet / Document Parsers
# ---------------------------------------------------------------------------

def _parse_excel(title: str) -> str:
    cleaned = _clean_title(title)
    t = re.sub(r"\s*[-—–]\s*Excel$", "", cleaned, flags=re.IGNORECASE).strip()
    t = re.sub(r"\.(xlsx|xls|xlsm|xlsb|csv)$", "", t, flags=re.IGNORECASE).strip()
    if t and t.lower() not in {"excel", "microsoft excel"}:
        return _truncate(f"Editing {t}")
    return "Crunching numbers"


def _parse_word(title: str) -> str:
    cleaned = _clean_title(title)
    t = re.sub(r"\s*[-—–]\s*Word$", "", cleaned, flags=re.IGNORECASE).strip()
    t = re.sub(r"\.(docx|doc|rtf|dotx)$", "", t, flags=re.IGNORECASE).strip()
    if t and t.lower() not in {"word", "microsoft word"}:
        return _truncate(f"Editing {t}")
    return "Working on a document"


def _parse_powerpoint(title: str) -> str:
    cleaned = _clean_title(title)
    t = re.sub(r"\s*[-—–]\s*PowerPoint$", "", cleaned, flags=re.IGNORECASE).strip()
    t = re.sub(r"\.(pptx|ppt|ppsx)$", "", t, flags=re.IGNORECASE).strip()
    if t and t.lower() not in {"powerpoint", "microsoft powerpoint"}:
        return _truncate(f"Presenting {t}")
    return "Making a presentation"


def _parse_notion(title: str) -> str:
    cleaned = _clean_title(title)
    t = re.sub(r"\s*[-—–]\s*Notion$", "", cleaned, flags=re.IGNORECASE).strip()
    if t and t.lower() != "notion":
        # Notion often formats titles like "Page Title - Workspace / Section"
        page = re.split(r"\s*[-—–]\s*", t)[0].strip()
        if page:
            return _truncate(f"Document: {page}")
    return "Working on a document"


def _parse_obsidian(title: str) -> str:
    cleaned = _clean_title(title)
    # E.g. "Note Title - Vault Name - Obsidian v1.6.5"
    t = re.sub(r"\s*[-—–]\s*Obsidian.*$", "", cleaned, flags=re.IGNORECASE).strip()
    if t:
        note = re.split(r"\s*[-—–]\s*", t)[0].strip()
        if note:
            return _truncate(f"Note: {note}")
    return "Taking notes"


def _parse_text_editor(title: str) -> str:
    cleaned = _clean_title(title)
    t = re.sub(r"\s*[-—–]\s*Notepad(\+\+)?$", "", cleaned, flags=re.IGNORECASE).strip()
    if t and t.lower() not in {"notepad", "notepad++", "untitled"}:
        return _truncate(f"Editing {Path(t).name}")
    return "Editing a file"


# ---------------------------------------------------------------------------
# Code Editors & IDE Parsers
# ---------------------------------------------------------------------------

_IDE_EXES = {
    "code.exe",
    "cursor.exe",
    "windsurf.exe",
    "antigravity ide.exe",
    "antigravity.exe",
    "sublime_text.exe",
    "devenv.exe",
    "pycharm64.exe",
    "idea64.exe",
    "webstorm64.exe",
    "rider64.exe",
    "clion64.exe",
    "goland64.exe",
}


def _parse_ide(title: str) -> str:
    cleaned = _clean_title(title)
    t = cleaned
    for suff in _IDE_SUFFIXES:
        t = suff.sub("", t).strip()

    if not t:
        return "Working on a project"

    parts = re.split(r"\s*[-—–]\s*", t)
    if len(parts) >= 2:
        file_part = parts[0].strip()
        proj_part = parts[1].strip()
        # In VS Code, format is "file.py - project"
        return _truncate(f"{file_part} ({proj_part})")
    elif len(parts) == 1 and parts[0]:
        return _truncate(f"Editing {parts[0]}")

    return "Working on a project"


# ---------------------------------------------------------------------------
# Media Players
# ---------------------------------------------------------------------------

def _parse_spotify(title: str) -> str:
    cleaned = _clean_title(title)
    # Spotify shows "Spotify" or "Spotify Free" when idle/paused
    if cleaned and cleaned.lower() not in {"spotify", "spotify free", "spotify premium"}:
        return _truncate(f"Listening to {cleaned}")
    return "Listening to music"


def _parse_vlc(title: str) -> str:
    cleaned = _clean_title(title)
    t = re.sub(r"\s*[-—–]\s*VLC media player$", "", cleaned, flags=re.IGNORECASE).strip()
    if t:
        return _truncate(f"Watching {t}")
    return "Watching something"


# ---------------------------------------------------------------------------
# Public Dispatcher
# ---------------------------------------------------------------------------

def extract_dynamic_tagline(
    exe_name: str,
    window_title: str,
    display_name: str = "",
    config: Optional[dict] = None,
) -> Optional[str]:
    """
    Extract a dynamic, semantic tagline from the active window title.
    Returns None if no dynamic pattern applies, signalling fallback to static tagline.
    """
    if config is not None and not config.get("enable_dynamic_taglines", True):
        return None

    if not window_title or not window_title.strip():
        return None

    exe = exe_name.lower()

    # 1. Office / Spreadsheets / Documents
    if exe == "excel.exe":
        return _parse_excel(window_title)
    if exe == "winword.exe":
        return _parse_word(window_title)
    if exe == "powerpnt.exe":
        return _parse_powerpoint(window_title)
    if exe == "notion.exe":
        return _parse_notion(window_title)
    if exe == "obsidian.exe":
        return _parse_obsidian(window_title)
    if exe in {"notepad.exe", "notepad++.exe"}:
        return _parse_text_editor(window_title)

    # 2. Web Browsers
    if exe in _BROWSER_EXES or "browser" in exe:
        return _parse_browser(window_title)

    # 3. Code Editors & IDEs
    if exe in _IDE_EXES:
        return _parse_ide(window_title)

    # 4. Media Players
    if exe == "spotify.exe":
        return _parse_spotify(window_title)
    if exe in {"vlc.exe", "mpc-hc64.exe", "mpc-hc.exe", "mpv.exe"}:
        return _parse_vlc(window_title)

    return None
