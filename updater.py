"""
updater.py — Version tracking and GitHub Releases update checker.
"""

import logging
import re
import threading
from typing import Optional, Tuple
import requests

logger = logging.getLogger("autorpc.updater")

__version__ = "0.1.0-beta"
GITHUB_REPO = "yashkthakor/Discord-AutoRPC"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=5"

# `/releases`, **not** `/releases/latest`: GitHub answers `404` on the `latest` endpoint while
# every published release is a prerelease — which is exactly this project's situation — so the
# check silently reported "up to date" forever (B-14).

# `1`, `1.2`, `1.2.3`, optionally followed by a pre-release suffix (`-beta`, `-rc.1`).
_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?([0-9A-Za-z][0-9A-Za-z.\-]*))?$")


def _version_key(tag: str) -> tuple:
    """Turn a release tag into something that can be *ordered*.

    `v1.2.3` → ((1, 2, 3), 1, "") — a final release.
    `v1.2.3-beta` → ((1, 2, 3), 0, "beta") — a pre-release of the same numbers, which is older
    than the release itself, so `0.1.0-beta` never "upgrades" to `0.1.0`.
    Anything unparseable sorts below every real version instead of winning.
    """
    text = (tag or "").strip().lstrip("vV").strip()
    match = _VERSION_RE.match(text)
    if not match:
        return ((0, 0, 0), 0, text)

    major, minor, patch, pre = match.groups()
    numbers = (int(major), int(minor or 0), int(patch or 0))
    return (numbers, 0 if pre else 1, pre or "")


def is_newer(remote_tag: str, local_version: str) -> bool:
    """True only when `remote_tag` is strictly newer than `local_version`."""
    return _version_key(remote_tag) > _version_key(local_version)


def check_for_updates() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check GitHub Releases for a newer version.
    Returns: (update_available, latest_version_tag, download_url)
    """
    try:
        resp = requests.get(API_URL, headers={"User-Agent": f"DiscordAutoRPC/{__version__}"}, timeout=6)
        if resp.status_code == 200:
            releases = resp.json()
            latest = releases[0] if isinstance(releases, list) and releases else None
            if latest:
                tag = str(latest.get("tag_name", "")).lstrip("v")
                html_url = latest.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")

                # Ordered comparison, not `!=`: the old test offered the running version back as
                # an update whenever the tag was written differently (B-11).
                if tag and is_newer(tag, __version__):
                    return True, tag, html_url
    except Exception as exc:
        logger.debug(f"Failed to check for updates: {exc}")
    
    return False, None, None


def check_updates_async(callback):
    """Run update check in background thread."""
    def _worker():
        avail, tag, url = check_for_updates()
        if avail and callback:
            callback(tag, url)
    threading.Thread(target=_worker, daemon=True).start()
