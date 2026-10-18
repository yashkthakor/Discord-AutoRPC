"""
engine_stdio.py — the headless engine the desktop shell drives (`main.py --engine-stdio`).

The Tauri shell in `desktop/` owns the window, the tray and config.json; this process owns
everything that needs Win32 or Discord: foreground detection, display names, taglines, icon
extraction and upload, and the RPC connection itself. It is the *same* pipeline the tray build
runs — `detector`, `icons`, `presence` — started without Qt, so nothing can draw (`T-022`).

Transport: one JSON object per line over stdin/stdout.

    shell → engine    {"cmd": "set_paused", "paused": true}
                      {"cmd": "reload_config"}
                      {"cmd": "clear_icon_cache", "exePaths": ["C:\\Apps\\app.exe"] | null}
                      {"cmd": "get_icon_cache"}
                      {"cmd": "quit"}
    engine → shell    {"type": "ready",    "version": "0.1.0-beta", "pid": 4242}
                      {"type": "builtins", "taglines": {"notion.exe": "Working on a document"}}
                      {"type": "discord",  "status": "connected"}
                      {"type": "app",      "app": {...AppInfo...} | null}
                      {"type": "icon_cache", "entries": [{"path": "c:\\apps\\app.exe", "url": "https://..."}]}
                      {"type": "log",      "level": "INFO", "logger": "autorpc.detector", "message": "..."}
                      {"type": "update",   "tag": "0.1.1", "url": "https://..."}
                      {"type": "toast",    "kind": "error", "message": "..."}
                      {"type": "fatal",    "message": "..."}

`AppInfo` carries an `icon` object — `{"state": "ok" | "pending" | "parked", "attempts": n,
"retryAtMs": ms | null, "reason": str | null}` — so the Status pane can say *why* an icon is
the default instead of just showing one (`T-030`).

Three rules keep the seam honest:

* **stdout is the protocol.** Nothing may `print()` from here — a stray write would corrupt the
  stream. Logging goes to `autorpc.log` (same file, format and rotation as the tray build), and
  a handler mirrors each record to the shell so the Logs pane is live without tailing a file.
* **stdin closing means the shell is gone.** EOF ends the loop, so a crashed shell can never
  leave a stale presence glued to somebody's Discord profile.
* **config.json is shared truth.** The shell writes it; this process notices the mtime change
  (or takes a `reload_config` nudge) and rebuilds the detector from the new values.
"""

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from typing import Any

from config import get_data_dir, is_configured, load_config
from detector import AppInfo, Detector, built_in_taglines, is_discord_running, is_ignored
from icons import cached_icons, clear_icon_cache, get_icon_url, icon_state
from presence import PresenceManager
from updater import __version__, check_for_updates

logger = logging.getLogger("autorpc.engine")

# Discord statuses, matching `desktop/src/ipc/types.ts` (`DiscordStatus`).
CONNECTED = "connected"
OFFLINE = "offline"
NOT_RUNNING = "not-running"

# How long to sit still when there is nothing to watch (Discord closed, or no Application ID).
IDLE_SLEEP_SECONDS = 2.0

CONFIG_PATH = get_data_dir() / "config.json"
LOG_PATH = get_data_dir() / "autorpc.log"


def _setup_logging() -> None:
    """
    `main._setup_logging` minus the console handler.

    stdout carries the protocol here, so a stream handler pointed at it would corrupt every
    line the shell reads. The file handler stays byte-identical to the tray build's.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = RotatingFileHandler(
        LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)


class _StdioHandler(logging.Handler):
    """
    Mirrors the pipeline's log records to the shell.

    Every logger involved (`autorpc.detector`, `autorpc.icons`, `autorpc.presence`, …) belongs
    to this process, so its lines only reach the Logs pane through here — while the file handler
    above still writes them, keeping `autorpc.log` complete for a bug report.

    Level is INFO, matching the tray build's console handler: the file keeps the DEBUG detail,
    the stream the shell reads stays readable.
    """

    def __init__(self, send) -> None:
        super().__init__(level=logging.INFO)
        self._send = send

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._send(
                {
                    "type": "log",
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
            )
        except Exception:  # a broken pipe must never take the engine down
            pass


def _mtime(path) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return -1.0


def _iter_stdin_lines() -> Iterator[str]:
    """Yield the shell's protocol lines, one at a time.

    Raw `os.read` rather than `sys.stdin` on purpose: this runs in a daemon thread that is
    normally *blocked* right here when the process exits, and a buffered reader still holding
    its lock at interpreter shutdown aborts CPython with `_enter_buffered_busy`. A raw read
    holds no Python lock, so the process can exit under it and let the OS reclaim the thread.

    The shell always hands us a pipe; the text fallback covers anything that hands us a console
    instead (running this module by hand, mainly).
    """
    try:
        fd = sys.stdin.fileno()
    except (AttributeError, OSError, ValueError):
        fd = -1

    if fd >= 0:
        pending = b""
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return  # closed under us, or not readable at all: the same as EOF
            if not chunk:
                return  # EOF

            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                yield line.decode("utf-8", errors="replace")
    else:
        for raw in sys.stdin:
            yield raw


class Engine:
    """
    One polling loop, one RPC connection, one JSON line per event.

    Threading is deliberately dull: the reader thread only ever sets a flag or an Event, and the
    loop thread does all the work, so nothing is shared by reference and no lock is held across
    a network call. `quit` interrupts a sleeping loop immediately because the loop waits on the
    Event rather than on `time.sleep`.
    """

    def __init__(self) -> None:
        self._write_lock = threading.Lock()
        self._quit = threading.Event()
        self._reload_requested = False
        self._paused = False
        self._paused_cleared = False

        self._config: dict[str, Any] = {}
        self._config_mtime: float = -1.0
        self._detector: Detector | None = None
        self._presence: PresenceManager | None = None

        # Icon cache intent, recorded by the reader thread and applied by the loop (`T-030`).
        self._icon_clear_requested = False
        self._icon_clear_paths: list[str] | None = None

        self._app_id = ""
        self._discord_status = ""
        self._last_app: dict | None = None

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def send(self, payload: dict) -> None:
        """Write one protocol line.

        Bytes, not text: `ensure_ascii` keeps the JSON pure ASCII, and going straight to the
        binary buffer avoids the locale codec Windows would otherwise apply to a pipe (`cp1252`
        would raise on the first em dash in a tagline). Flushed every time — the shell is
        blocked on a line, not on a frame.
        """
        line = json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"
        data = line.encode("ascii", errors="replace")

        with self._write_lock:
            try:
                stream = getattr(sys.stdout, "buffer", None)
                if stream is None:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    stream.write(data)
                    stream.flush()
            except Exception:
                # The shell is gone; the reader thread's EOF path ends the loop.
                pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> int:
        logger.info(
            f"Engine running headless over stdio (v{__version__}, pid {os.getpid()})"
        )
        self.send({"type": "ready", "version": __version__, "pid": os.getpid()})
        self.send({"type": "builtins", "taglines": built_in_taglines()})

        self._start_reader()
        self._apply_config(load_config())
        self._check_updates()

        code = 0
        try:
            self._loop()
        except Exception as exc:
            logger.exception("Engine loop crashed")
            self.send({"type": "fatal", "message": f"{type(exc).__name__}: {exc}"})
            code = 1
        finally:
            self._shutdown()

        return code

    def _start_reader(self) -> None:
        def _read() -> None:
            for line in _iter_stdin_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"Ignoring a non-JSON line on stdin: {line[:200]}")
                    continue
                self._handle(message)

            # EOF: the shell exited without saying goodbye.
            logger.info("The shell closed the protocol pipe — stopping the engine")
            self._quit.set()

        threading.Thread(target=_read, name="engine-stdin", daemon=True).start()

    def _handle(self, message: dict) -> None:
        """Record intent only — the loop thread owns every piece of state."""
        command = message.get("cmd")

        if command == "set_paused":
            paused = bool(message.get("paused"))
            if paused != self._paused:
                self._paused = paused
                if not paused:
                    self._paused_cleared = False
                logger.info("Paused from the shell" if paused else "Resumed from the shell")
        elif command == "reload_config":
            self._reload_requested = True
        elif command == "clear_icon_cache":
            paths = message.get("exePaths")
            self._icon_clear_paths = [str(path) for path in paths] if isinstance(paths, list) else None
            self._icon_clear_requested = True
        elif command == "get_icon_cache":
            # Read-only and stateless, so the reader thread answers directly: the settings
            # pane wants the list on the next frame, not on the next poll.
            self.send({"type": "icon_cache", "entries": cached_icons()})
        elif command == "quit":
            logger.info("Quit requested by the shell")
            self._quit.set()
        else:
            logger.warning(f"Ignoring an unknown command from the shell: {command!r}")

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while not self._quit.is_set():
            if self._reload_requested:
                self._reload_requested = False
                self._apply_config(load_config())
            else:
                self._reload_if_changed()

            # Applies per-app or full icon-cache clears from the shell before anything is
            # resolved this cycle, so the refreshed icon is the one that gets announced.
            self._drain_icon_requests()

            if self._paused:
                self._clear_once_while_paused()
                self._quit.wait(1.0)
                continue

            if not self._sync_discord():
                self._quit.wait(IDLE_SLEEP_SECONDS)
                continue

            try:
                self._tick()
            except Exception:
                logger.exception("Poll cycle failed; keeping the loop alive")

            self._quit.wait(self._poll_interval())

    def _poll_interval(self) -> float:
        try:
            return max(1.0, float(self._config.get("poll_interval", 5)))
        except (TypeError, ValueError):
            return 5.0

    def _clear_once_while_paused(self) -> None:
        if self._paused_cleared:
            return
        self._paused_cleared = True
        if self._presence is not None:
            self._presence.clear()
        self._forget_app()

    def _sync_discord(self) -> bool:
        """
        Mirror `main._poll_loop`'s lifecycle rules, minus the tray, which the shell owns.

        Returns True when a presence can be sent. Dormancy is not a thing here: the shell stays
        on screen and simply reads `discord: "not-running"` from the status line.
        """
        if self._presence is None:
            return False

        if not is_discord_running():
            if self._discord_status != NOT_RUNNING:
                self._presence.clear()
                self._forget_app()
                self._set_status(NOT_RUNNING)
                logger.info("Discord is not running — waiting for it to come back")
            return False

        if not self._presence.connected:
            # The first sight of Discord connects immediately; later retries respect the
            # manager's own RECONNECT_INTERVAL so the IPC pipe is not hammered every second.
            force = self._discord_status in ("", NOT_RUNNING)
            self._presence.connect(force=force)
            self._set_status(CONNECTED if self._presence.connected else OFFLINE)

        return self._presence.connected

    def _tick(self) -> None:
        """One detection sample: poll, resolve, broadcast, and tell the shell what is on screen."""
        if self._detector is None:
            self._detector = Detector(self._config)

        detector = self._detector
        detector.config = self._config
        detector.overrides = self._config.get("overrides", {})

        app = detector.poll()
        if app is None:
            # Only retract what was actually broadcast: Discord drops the presence on its own
            # when nothing was ever sent, and clearing every idle cycle would log a line a
            # minute for no reason.
            if self._presence is not None and self._last_app is not None:
                self._presence.clear()
            self._forget_app()
            return

        # Stamp the start time before any icon work: Discord's timer must count from when the
        # app was detected, not from when a slow or retrying icon fetch finished (`T-030`).
        if self._presence is not None:
            self._presence.start_epoch(app.exe_path, app.pid)

        icon_url = get_icon_url(app.exe_path, app.display_name, self._config)
        if self._presence is not None:
            self._presence.update(
                display_name=app.display_name,
                icon_url=icon_url,
                exe_path=app.exe_path,
                pid=app.pid,
                tagline=app.tagline,
            )

        self._announce(app, icon_url)

    def _drain_icon_requests(self) -> None:
        """Apply a `clear_icon_cache` from the shell, then publish the refreshed listing."""
        if not self._icon_clear_requested:
            return

        self._icon_clear_requested = False
        requested = self._icon_clear_paths
        self._icon_clear_paths = None

        cleared = clear_icon_cache(requested)
        self.send({"type": "icon_cache", "entries": cached_icons()})
        self.send({
            "type": "toast",
            "kind": "info",
            "message": (
                f"Cleared {cleared} cached icon{'s' if cleared != 1 else ''} — "
                f"fetching again on the next poll."
                if cleared
                else "No cached icon to clear — trying again on the next poll."
            ),
        })

    def _announce(self, app: AppInfo, icon_url: str) -> None:
        """Tell the shell what is on screen, once per distinct answer."""
        started = (
            self._presence.start_epoch(app.exe_path, app.pid)
            if self._presence is not None
            else int(time.time())
        )

        info = {
            "exe": app.exe_name,
            "path": app.exe_path,
            "pid": app.pid,
            "displayName": app.display_name,
            "tagline": app.tagline or None,
            "iconUrl": icon_url or None,
            # Why the icon is what it is — the Status pane shows the ladder's state (`T-030`).
            "icon": icon_state(app.exe_path),
            "startedAtMs": started * 1000,
            "ignored": is_ignored(app, self._config),
        }

        if info == self._last_app:
            return

        self._last_app = info
        self.send({"type": "app", "app": info})

    def _forget_app(self) -> None:
        if self._last_app is not None:
            self._last_app = None
            self.send({"type": "app", "app": None})

    def _set_status(self, status: str) -> None:
        """Push a Discord status, but only when it changes. An empty status means "unknown"."""
        if status == self._discord_status:
            return
        self._discord_status = status
        if status:
            self.send({"type": "discord", "status": status})

    # ------------------------------------------------------------------
    # Config and updates
    # ------------------------------------------------------------------

    def _reload_if_changed(self) -> None:
        mtime = _mtime(CONFIG_PATH)
        if mtime == self._config_mtime:
            return

        self._config_mtime = mtime
        logger.info("config.json changed on disk — reloading")
        self._apply_config(load_config())

    def _apply_config(self, config: dict) -> None:
        self._config = config

        # Every applied config *is* the file's current contents, so the watcher starts counting
        # from here. Without this the next tick would announce a change for a file it just read.
        self._config_mtime = _mtime(CONFIG_PATH)

        # Debounce state, cached display names and tagline context are all derived from the
        # config, so a fresh detector is the honest way to apply a change (the tray build does
        # the same when Settings saves).
        self._detector = None

        if not is_configured(config):
            if self._presence is not None:
                self._presence.close()
                self._presence = None
            self._app_id = ""
            self._set_status(OFFLINE)
            logger.warning(
                "No valid Application ID in config.json — waiting for Settings to save one"
            )
            return

        app_id = str(config.get("application_id", ""))
        if app_id != self._app_id:
            if self._presence is not None:
                self._presence.close()
            self._presence = PresenceManager(app_id)
            self._app_id = app_id
            self._discord_status = ""  # reconnect from scratch on the next tick
            logger.info(f"Using Application ID {app_id}")

    def _check_updates(self) -> None:
        """One check, in the background, exactly like the tray build does at startup."""

        def _worker() -> None:
            available, tag, url = check_for_updates()
            if available and tag:
                logger.info(f"Update available: v{tag}")
                self.send({"type": "update", "tag": tag, "url": url or ""})

        threading.Thread(target=_worker, name="engine-update", daemon=True).start()

    def _shutdown(self) -> None:
        """Leave Discord exactly as we found it: no presence, no socket."""
        if self._presence is not None:
            self._presence.clear()
            self._presence.close()
        logger.info("Engine stopped")


def run() -> int:
    """Entry point used by `main.py --engine-stdio`."""
    _setup_logging()
    engine = Engine()
    logging.getLogger().addHandler(_StdioHandler(engine.send))
    return engine.run()


if __name__ == "__main__":
    sys.exit(run())
