"""
presence.py — Discord Rich Presence connection and update management.

Uses pypresence to maintain a single RPC connection.
Handles Discord not running, pipe errors, rate limiting, and reconnection.
"""

import logging
import time
from typing import Optional

from pypresence import Presence, exceptions as pp_exceptions

logger = logging.getLogger("autorpc.presence")

# pypresence ≥ 4.3.0 exposes these; import defensively
try:
    from pypresence.types import StatusDisplayType
    HAS_STATUS_DISPLAY_TYPE = True
except ImportError:
    HAS_STATUS_DISPLAY_TYPE = False
    logger.warning(
        "pypresence version lacks StatusDisplayType — "
        "app name will be shown in 'details' instead of the 'Playing ...' header."
    )


class PresenceManager:
    """
    Wraps pypresence.Presence with resilient connect/update/clear logic.

    Key behaviours
    ─────────────
    • One persistent connection (reconnects automatically on errors).
    • Rate-limited: at most one update() call per 15 seconds.
    • Tracks per-app start times so switching back doesn't reset the timer
      unless the process has restarted.
    """

    RATE_LIMIT_SECONDS = 15
    RECONNECT_INTERVAL = 15

    def __init__(self, application_id: str):
        self._app_id = application_id
        self._rpc: Optional[Presence] = None
        self._connected = False
        self._last_update_time: float = 0.0
        self._last_reconnect_attempt: float = 0.0

        # exe_path (lower) → {pid, start_epoch}
        self._start_times: dict[str, dict] = {}

        # Track what we last sent so we can skip no-op updates
        self._last_sent_key: Optional[str] = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Try to connect to Discord. Returns True on success."""
        now = time.time()
        if now - self._last_reconnect_attempt < self.RECONNECT_INTERVAL:
            return False
        self._last_reconnect_attempt = now

        try:
            self._rpc = Presence(self._app_id)
            self._rpc.connect()
            self._connected = True
            logger.info("Connected to Discord RPC")
            return True
        except Exception as exc:
            self._connected = False
            logger.debug(f"Discord RPC connect failed (is Discord running?): {exc}")
            return False

    def _ensure_connected(self) -> bool:
        if self._connected:
            return True
        return self.connect()

    # ------------------------------------------------------------------
    # Start-time tracking
    # ------------------------------------------------------------------

    def _get_start_time(self, exe_path: str, pid: int) -> int:
        """
        Return the epoch when the app first came to foreground.
        If the PID changed (process restarted), reset the timer.
        """
        key = exe_path.lower()
        entry = self._start_times.get(key)
        if entry and entry["pid"] == pid:
            return entry["start_epoch"]

        epoch = int(time.time())
        self._start_times[key] = {"pid": pid, "start_epoch": epoch}
        return epoch

    # ------------------------------------------------------------------
    # Update / Clear
    # ------------------------------------------------------------------

    def update(
        self,
        display_name: str,
        icon_url: str,
        exe_path: str,
        pid: int,
        tagline: str = "",
    ) -> bool:
        """
        Set the Rich Presence for the given app.
        Respects the 15-second rate limit; returns True if an update was sent.
        """
        if not self._ensure_connected():
            return False

        # Build a de-duplication key
        update_key = f"{exe_path.lower()}|{pid}|{icon_url}|{display_name}|{tagline}"
        now = time.time()

        # Skip if identical presence was already sent.
        # This is CRITICAL: re-sending every 15 seconds interrupts Discord's
        # client-side timer, making it jump every 15s instead of ticking smoothly every second!
        if update_key == self._last_sent_key:
            return False

        # Rate limit between different app updates
        if now - self._last_update_time < self.RATE_LIMIT_SECONDS:
            return False

        start_epoch = self._get_start_time(exe_path, pid)

        try:
            kwargs: dict = {
                "large_image": icon_url,
                "large_text": display_name,
                "start": start_epoch,
            }

            # Use the `name` field + StatusDisplayType.NAME if available
            # (pypresence ≥ 4.3.0). This makes Discord show
            #     Playing <display_name>
            # rather than the static application name from the developer portal.
            if HAS_STATUS_DISPLAY_TYPE:
                kwargs["name"] = display_name
                kwargs["status_display_type"] = StatusDisplayType.NAME
                if tagline:
                    kwargs["details"] = tagline
            else:
                # Older pypresence fallback
                kwargs["details"] = display_name
                if tagline:
                    kwargs["state"] = tagline

            self._rpc.update(**kwargs)
            self._last_update_time = time.time()
            self._last_sent_key = update_key
            logger.info(f"Presence updated → {display_name}" + (f" ({tagline})" if tagline else ""))
            return True

        except (pp_exceptions.InvalidID, BrokenPipeError, Exception) as exc:
            logger.warning(f"Presence update failed, will reconnect: {exc}")
            self._connected = False
            self._last_sent_key = None
            return False

    def clear(self) -> None:
        """Clear the presence (nothing being tracked)."""
        if not self._connected:
            return
        try:
            self._rpc.clear()
            self._last_sent_key = None
            logger.info("Presence cleared")
        except Exception as exc:
            logger.debug(f"Presence clear failed: {exc}")
            self._connected = False

    def close(self) -> None:
        """Gracefully close the RPC connection."""
        try:
            if self._rpc and self._connected:
                self._rpc.close()
        except Exception:
            pass
        self._connected = False
        logger.info("RPC connection closed")
