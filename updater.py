"""
updater.py — Version tracking and GitHub Releases update checker.
"""

import logging
import threading
from typing import Optional, Tuple
import requests

logger = logging.getLogger("autorpc.updater")

__version__ = "0.1.0-beta"
GITHUB_REPO = "yashkthakor/Discord-AutoRPC"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_for_updates() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check GitHub Releases for a newer version.
    Returns: (update_available, latest_version_tag, download_url)
    """
    try:
        resp = requests.get(API_URL, headers={"User-Agent": f"DiscordAutoRPC/{__version__}"}, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            tag = data.get("tag_name", "").lstrip("v")
            html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
            
            # Simple version comparison
            if tag and tag != __version__.lstrip("v"):
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
