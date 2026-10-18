"""
icons.py — Extract exe icons, upload to a public host, cache results.

Pipeline:
  1. Check icon_cache.json for an existing URL.
  2. (Optional) Query SteamGridDB for a polished icon.
  3. Extract the icon from the exe via the Windows Shell API.
  4. Upload the PNG to a public host (the configured one, then failover).
  5. Verify the URL length and content-type.
  6. Cache the result, or schedule the next attempt on a bounded ladder (`T-030`).

The last stage is the one that fails for real users — a host hiccup, a blocked network,
or an exe with no icon resource at all. `get_icon_url` is called on every poll, so the
ladder counts attempts itself: three tries, then an escalating park instead of an
extract-and-upload every `poll_interval` forever.
"""

import ctypes
import ctypes.wintypes
import io
import json
import logging
import struct
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import requests
import win32api
import win32con
import win32gui
import win32ui
from PIL import Image

from config import get_data_dir

logger = logging.getLogger("autorpc.icons")

_CACHE_PATH = get_data_dir() / "icon_cache.json"


# ---------------------------------------------------------------------------
# Retry ladder (T-030)
# ---------------------------------------------------------------------------

#: Attempts made before an app is parked. The poll loop asks for an icon every tick, so
#: only the first attempt is immediate; `_ATTEMPT_DELAYS` is the floor between the rest.
_MAX_ATTEMPTS = 3
_ATTEMPT_DELAYS = (1.0, 3.0)

#: Park lengths once a three-attempt sequence has failed, growing per consecutive failure.
#: A hard failure (nothing to extract) parks straight on the last rung — retrying cannot help.
_PARK_LADDER = (60.0, 300.0, 1800.0)
_HARD_PARK = 1800.0

#: Per-host timeout for retry attempts; the first attempt keeps the hosts' 20 s default.
_RETRY_NET_TIMEOUT = 4.0

#: How long a failed URL-validation verdict is remembered. Successes are kept for the
#: session, so an untrusted override URL is probed once instead of once per poll (`F6`).
_VALIDATION_FAILURE_TTL = 1800.0


class _Attempt:
    """What the ladder knows about one executable. In memory only; a restart clears it."""

    __slots__ = ("streak", "next_at", "rung", "parked_until", "reason")

    def __init__(self) -> None:
        self.streak = 0        # failures in the current attempt sequence
        self.next_at = 0.0     # earliest time for the next attempt
        self.rung = 0          # which _PARK_LADDER step the next park uses
        self.parked_until = 0.0
        self.reason = ""       # last failure, for the log and the Status pane


_attempts: dict[str, _Attempt] = {}
_validation_memo: dict[str, tuple[bool, float]] = {}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _load_cache() -> dict[str, str]:
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        # A corrupt or unreadable file must not take the poll loop down with it.
        logger.warning(f"{_CACHE_PATH.name} could not be read ({exc}); starting from an empty cache")
        return {}

    if not isinstance(data, dict):
        logger.warning(f"{_CACHE_PATH.name} is not a JSON object; starting from an empty cache")
        return {}
    return data


def _save_cache(cache: dict[str, str]) -> None:
    """Write atomically (temp + replace) so a concurrent reader never sees half a file."""
    tmp = _CACHE_PATH.with_name(_CACHE_PATH.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        tmp.replace(_CACHE_PATH)
    except OSError as exc:
        logger.warning(f"Could not write {_CACHE_PATH.name}: {exc}")


def clear_icon_cache(exe_paths: Sequence[str] | None = None) -> int:
    """Drop cached icon URLs and reset their retry state.

    Without *exe_paths* this clears everything. With a list it removes exactly those
    entries — the per-app clear in the desktop shell — and resets each app's ladder so
    the next poll fetches again immediately. Returns the number of removed entries.
    """
    cache = _load_cache()

    if exe_paths is None:
        count = len(cache)
        _save_cache({})
        _attempts.clear()
        logger.info(f"Cleared all {count} entries from the icon cache.")
        return count

    wanted = {str(path).lower() for path in exe_paths}
    removed = [key for key in cache if key.lower() in wanted]
    for key in removed:
        del cache[key]
    if removed:
        _save_cache(cache)
    for path in wanted:
        _attempts.pop(path, None)

    label = ", ".join(sorted(wanted)) or "nothing specified"
    logger.info(
        f"Cleared {len(removed)} cached icon(s) for {label} — "
        f"the next poll fetches them again."
    )
    return len(removed)


def cached_icons() -> list[dict[str, str]]:
    """Every cached icon as `{"path": exe, "url": url}`, stable-ordered for the settings list."""
    cache = _load_cache()
    return [
        {"path": path, "url": url}
        for path, url in sorted(cache.items())
        if isinstance(url, str)
    ]


_ICON_STATE_OK = "ok"
_ICON_STATE_PENDING = "pending"
_ICON_STATE_PARKED = "parked"


def icon_state(exe_path: str) -> dict[str, Any]:
    """What the retry ladder knows about *exe_path*, for the Status pane (`T-030`)."""
    state = _attempts.get(exe_path.lower())
    if state is None:
        return {"state": _ICON_STATE_OK, "attempts": 0, "retryAtMs": None, "reason": None}

    now = time.time()
    if state.parked_until > now:
        return {
            "state": _ICON_STATE_PARKED,
            "attempts": _MAX_ATTEMPTS,
            "retryAtMs": int(state.parked_until * 1000),
            "reason": state.reason or None,
        }
    if state.next_at > now or state.streak:
        return {
            "state": _ICON_STATE_PENDING,
            "attempts": state.streak,
            "retryAtMs": int(state.next_at * 1000) if state.next_at > now else None,
            "reason": state.reason or None,
        }
    return {"state": _ICON_STATE_OK, "attempts": 0, "retryAtMs": None, "reason": None}


# ---------------------------------------------------------------------------
# Icon extraction (Windows Shell API → PIL Image)
# ---------------------------------------------------------------------------

def _extract_icon_image(exe_path: str, size: int = 256) -> Image.Image | None:
    """
    Extract the highest resolution icon from *exe_path* and return it as a
    clean RGBA PIL Image.
    Prioritizes PrivateExtractIconsW (native 256x256), falling back to ExtractIconEx.
    """
    try:
        # --- Approach 1: PrivateExtractIconsW for native 256x256 icon resource ---
        hicons = (ctypes.wintypes.HICON * 1)()
        ids = (ctypes.wintypes.UINT * 1)()
        count = ctypes.windll.user32.PrivateExtractIconsW(
            exe_path, 0, size, size, hicons, ids, 1, 0
        )
        if count > 0 and hicons[0]:
            hicon = hicons[0]
            img = _hicon_to_pil(hicon, size)
            win32gui.DestroyIcon(hicon)
            if img:
                logger.debug(f"Extracted high-res {img.size[0]}x{img.size[1]} icon via PrivateExtractIconsW for {exe_path}")
                return img

        # --- Approach 2: Fallback to ExtractIconEx (standard system icon) ---
        large_icons, small_icons = win32gui.ExtractIconEx(exe_path, 0, 1)
        if large_icons:
            hicon = large_icons[0]
            for h in small_icons:
                win32gui.DestroyIcon(h)
            img = _hicon_to_pil(hicon, size)
            win32gui.DestroyIcon(hicon)
            if img:
                logger.debug(f"Extracted fallback icon via ExtractIconEx for {exe_path}")
                return img

        logger.debug(f"No icon found in {exe_path}")
        return None

    except Exception as exc:
        logger.warning(f"Icon extraction failed for {exe_path}: {exc}")
        return None


def _hicon_to_pil(hicon: int, target_size: int = 256) -> Image.Image | None:
    """Convert an HICON handle to a PIL RGBA Image at *target_size*."""
    try:
        # Get icon info to determine the bitmap size
        icon_info = win32gui.GetIconInfo(hicon)
        # icon_info: (fIcon, xHotspot, yHotspot, hbmMask, hbmColor)
        hbm_color = icon_info[4]
        hbm_mask = icon_info[3]

        # Get the bitmap header to find the actual icon dimensions
        bmp_info = win32gui.GetObject(hbm_color)
        width = bmp_info.bmWidth
        height = bmp_info.bmHeight

        # Create DCs
        hdc_screen = win32gui.GetDC(0)
        hdc = win32ui.CreateDCFromHandle(hdc_screen)
        hdc_mem = hdc.CreateCompatibleDC()

        # Create a 32-bit DIB section
        bmi = _make_bitmapinfo(width, height)
        hbm = ctypes.windll.gdi32.CreateDIBSection(
            hdc_mem.GetSafeHdc(), bmi, win32con.DIB_RGB_COLORS,
            ctypes.byref(ctypes.c_void_p()), None, 0,
        )
        if not hbm:
            return None

        hbm_old = ctypes.windll.gdi32.SelectObject(hdc_mem.GetSafeHdc(), hbm)

        # Draw the icon onto our DIB
        ctypes.windll.user32.DrawIconEx(
            hdc_mem.GetSafeHdc(), 0, 0, hicon,
            width, height, 0, None, 0x0003,  # DI_NORMAL
        )

        # Read pixel data
        buf_size = width * height * 4
        buf = ctypes.create_string_buffer(buf_size)
        ctypes.windll.gdi32.GetBitmapBits(hbm, buf_size, buf)

        # Build PIL Image (BGRA → RGBA, top-down DIB so no flip needed)
        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)

        # Clean up GDI
        ctypes.windll.gdi32.SelectObject(hdc_mem.GetSafeHdc(), hbm_old)
        ctypes.windll.gdi32.DeleteObject(hbm)
        hdc_mem.DeleteDC()
        hdc.DeleteDC()
        win32gui.ReleaseDC(0, hdc_screen)
        win32gui.DeleteObject(hbm_mask)
        win32gui.DeleteObject(hbm_color)

        # Resize to target only if dimensions differ
        if img.size != (target_size, target_size):
            img = img.resize((target_size, target_size), Image.LANCZOS)
        return img

    except Exception as exc:
        logger.warning(f"HICON → PIL failed: {exc}")
        return None


def _make_bitmapinfo(width: int, height: int):
    """Build a BITMAPINFO struct for a 32-bit top-down DIB."""

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.wintypes.DWORD),
            ("biWidth", ctypes.wintypes.LONG),
            ("biHeight", ctypes.wintypes.LONG),
            ("biPlanes", ctypes.wintypes.WORD),
            ("biBitCount", ctypes.wintypes.WORD),
            ("biCompression", ctypes.wintypes.DWORD),
            ("biSizeImage", ctypes.wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.wintypes.LONG),
            ("biYPelsPerMeter", ctypes.wintypes.LONG),
            ("biClrUsed", ctypes.wintypes.DWORD),
            ("biClrImportant", ctypes.wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
        ]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB
    return ctypes.byref(bmi)


# ---------------------------------------------------------------------------
# Upload hosts
# ---------------------------------------------------------------------------

def _upload_catbox(png_bytes: bytes, filename: str = "icon.png", timeout: float = 20.0) -> str | None:
    """Upload a PNG to catbox.moe and return the direct URL. Raises on transport/API errors."""
    resp = requests.post(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": (filename, png_bytes, "image/png")},
        timeout=timeout,
    )
    resp.raise_for_status()
    url = resp.text.strip()
    if url.startswith("https://"):
        return url
    raise ValueError(f"unexpected response {url[:80]!r}")


def _upload_freeimage(png_bytes: bytes, filename: str = "icon.png", timeout: float = 20.0) -> str | None:
    """Upload a PNG to freeimage.host and return the direct Cloudflare CDN URL (iili.io).

    Raises on transport/API errors; `_upload_png` collects the reasons.
    """
    resp = requests.post(
        "https://freeimage.host/api/1/upload",
        data={
            "key": "6d207e02198a847aa98d0a2a901485a5",
            "action": "upload",
            "format": "json",
        },
        files={"source": (filename, png_bytes, "image/png")},
        timeout=timeout,
    )
    resp.raise_for_status()
    url = (resp.json().get("image") or {}).get("url")
    if isinstance(url, str) and url.startswith("https://"):
        return url
    raise ValueError(f"no image URL in the response (HTTP {resp.status_code})")


# Registry of upload hosts
_UPLOAD_HOSTS = {
    "freeimage": _upload_freeimage,
    "catbox": _upload_catbox,
}


def _upload_png(png_bytes: bytes, host: str = "freeimage",
                filename: str = "icon.png",
                timeout: float | None = None) -> tuple[str | None, str]:
    """Upload a PNG, trying the configured host and then the other one.

    Returns `(url, detail)`. *detail* names the host that answered, or lists what each one
    said when they all failed — the caller logs it, so a fallback to the default icon always
    names the stage and the host that broke (`T-030`).
    """
    if host == "catbox":
        chain = [_upload_catbox, _upload_freeimage]
    else:
        chain = [_upload_freeimage, _upload_catbox]

    effective = 20.0 if timeout is None else timeout
    problems: list[str] = []

    for uploader in chain:
        name = uploader.__name__.removeprefix("_upload_")
        try:
            url = uploader(png_bytes, filename, effective)
        except Exception as exc:
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if url:
            if problems:
                logger.debug(f"Icon upload fell through to {name}: {'; '.join(problems)}")
            return url, name
        problems.append(f"{name}: no URL returned")

    return None, "; ".join(problems) or "no host tried"


# ---------------------------------------------------------------------------
# SteamGridDB (optional)
# ---------------------------------------------------------------------------

def _try_steamgriddb(game_name: str, api_key: str) -> str | None:
    """Search SteamGridDB for a game icon. Returns a direct image URL or None."""
    if not api_key:
        return None
    try:
        headers = {"Authorization": f"Bearer {api_key}"}

        # Search for the game
        search_resp = requests.get(
            "https://www.steamgriddb.com/api/v2/search/autocomplete/" + requests.utils.quote(game_name),
            headers=headers,
            timeout=10,
        )
        search_resp.raise_for_status()
        data = search_resp.json().get("data", [])
        if not data:
            return None

        game_id = data[0]["id"]

        # Fetch icons
        icons_resp = requests.get(
            f"https://www.steamgriddb.com/api/v2/icons/game/{game_id}",
            headers=headers,
            timeout=10,
        )
        icons_resp.raise_for_status()
        icons = icons_resp.json().get("data", [])
        if icons:
            url = icons[0].get("url") or icons[0].get("thumb")
            if url and len(url) < 256:
                return url

    except Exception as exc:
        logger.debug(f"SteamGridDB lookup failed for '{game_name}': {exc}")
    return None


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

# Hosts we trust to serve images without needing a network probe
_TRUSTED_IMAGE_HOSTS = {
    "files.catbox.moe",
    "iili.io",
    "freeimage.host",
    "cdn.discordapp.com",
    "www.steamgriddb.com",
    "cdn2.steamgriddb.com",
}

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}


def _validate_icon_url(url: str) -> bool:
    """Ensure the URL is short enough for Discord and serves an image."""
    if not url or len(url) >= 256:
        logger.warning(f"Icon URL too long or empty ({len(url) if url else 0} chars)")
        return False

    from urllib.parse import urlparse
    parsed = urlparse(url)

    # Fast-path: trust known CDN hosts + image extension
    if parsed.hostname in _TRUSTED_IMAGE_HOSTS:
        ext = Path(parsed.path).suffix.lower()
        if ext in _IMAGE_EXTENSIONS:
            return True

    # Untrusted hosts need a probe, but the poll loop validates the same override URL every
    # tick — memoize so that is one probe, not one every `poll_interval` (`T-030` / F6).
    # Successes live for the session; failures expire so a URL fixed on the server comes back.
    memo = _validation_memo.get(url)
    now = time.time()
    if memo is not None and (memo[0] or now - memo[1] < _VALIDATION_FAILURE_TTL):
        return memo[0]

    ok = _probe_icon_url(url)
    _validation_memo[url] = (ok, now)
    return ok


def _probe_icon_url(url: str) -> bool:
    """The network half of `_validate_icon_url`: one ranged GET, no memo involved."""
    from urllib.parse import urlparse
    parsed = urlparse(url)

    # Network probe: use GET with Range header (many CDNs reject HEAD)
    try:
        resp = requests.get(
            url,
            headers={
                "Range": "bytes=0-0",
                "User-Agent": "DiscordAutoRPC/1.0",
            },
            timeout=10,
            allow_redirects=True,
            stream=True,
        )
        ct = resp.headers.get("Content-Type", "")
        resp.close()
        if "image" in ct or "octet-stream" in ct:
            return True
        # If the server returned 200/206 and the URL ends with an image ext,
        # trust it even if Content-Type is generic
        if resp.status_code in (200, 206):
            ext = Path(parsed.path).suffix.lower()
            if ext in _IMAGE_EXTENSIONS:
                return True
        logger.warning(f"Icon URL content-type is '{ct}', expected image/*")
    except Exception as exc:
        logger.debug(f"Icon URL validation failed: {exc}")
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _note_failure(key: str, display_name: str, reason: str, *, hard: bool) -> None:
    """Record a failed attempt, schedule the next one, park the app when they run out."""
    state = _attempts.setdefault(key, _Attempt())
    state.streak += 1
    state.reason = reason

    if state.streak < _MAX_ATTEMPTS:
        delay = _ATTEMPT_DELAYS[min(state.streak - 1, len(_ATTEMPT_DELAYS) - 1)]
        state.next_at = time.time() + delay
        logger.warning(
            f"No icon for {display_name} yet ({reason}) — attempt {state.streak}/{_MAX_ATTEMPTS}, "
            f"trying again in {delay:g}s"
        )
        return

    seconds = _HARD_PARK if hard else _PARK_LADDER[min(state.rung, len(_PARK_LADDER) - 1)]
    if not hard:
        state.rung = min(state.rung + 1, len(_PARK_LADDER) - 1)
    state.streak = 0
    state.next_at = 0.0
    state.parked_until = time.time() + seconds

    until = time.strftime("%H:%M:%S", time.localtime(state.parked_until))
    logger.info(
        f"Using default icon for {display_name} — {reason}; parked for "
        f"{_human_seconds(seconds)} (trying again at {until})"
    )


def _human_seconds(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:g}h"
    if seconds >= 60:
        return f"{seconds / 60:g} min"
    return f"{seconds:g}s"


def get_icon_url(exe_path: str, display_name: str, config: dict) -> str:
    """
    Return a public URL for the application's icon.

    Order: override → cache → SteamGridDB → extract + upload → the configured default.

    The last stage is retried on a bounded ladder: three attempts (at most one per poll,
    so the loop is never blocked for long) and then a park on the escalating cooldown,
    instead of an extract-and-upload on every tick forever (`T-030`).
    """
    default_url: str = config.get("default_icon_url",
                                  "https://cdn.discordapp.com/embed/avatars/0.png")
    host: str = config.get("upload_host", "freeimage")
    sgdb_key: str = config.get("steamgriddb_api_key", "")
    overrides: dict = config.get("overrides", {})

    exe_name = Path(exe_path).name.lower()
    key = exe_path.lower()

    # 1. Check config override for a manual icon_url. Before the ladder gate, so a user's
    #    fix applies immediately even while the app is parked.
    for ovr_key, val in overrides.items():
        if ovr_key.lower() == exe_name and isinstance(val, dict):
            override_url = val.get("icon_url")
            if override_url and _validate_icon_url(override_url):
                _attempts.pop(key, None)
                return override_url

    # Parked, or waiting for the next scheduled attempt: the three tries already happened,
    # so this tick answers with the default and does no GDI or network work. Quiet on
    # purpose — the park line and each attempt warning already said what is happening.
    state = _attempts.get(key)
    if state is not None and max(state.parked_until, state.next_at) > time.time():
        return default_url

    # 2. Check cache
    cache = _load_cache()
    cached = cache.get(key)
    if cached and _validate_icon_url(cached):
        _attempts.pop(key, None)
        return cached

    # 3. Try SteamGridDB
    if sgdb_key:
        sgdb_url = _try_steamgriddb(display_name, sgdb_key)
        if sgdb_url and _validate_icon_url(sgdb_url):
            cache[key] = sgdb_url
            _save_cache(cache)
            _attempts.pop(key, None)
            logger.info(f"SteamGridDB icon cached for {display_name}")
            return sgdb_url

    # 4. Extract from exe and upload — the stage the ladder counts
    attempt = 1 + (state.streak if state is not None else 0)
    img = _extract_icon_image(exe_path)
    if img is not None:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        safe_name = exe_name.replace(" ", "_").replace(".exe", "") + ".png"
        # Retries use a shorter per-host timeout so a black-holed network cannot stretch
        # the poll cycle by two full default timeouts per attempt.
        timeout = None if attempt == 1 else _RETRY_NET_TIMEOUT
        url, detail = _upload_png(png_bytes, host=host, filename=safe_name, timeout=timeout)
        if url:
            # Cache immediately — upload returned a URL, so the file exists.
            # Validation is a secondary check; don't let a flaky HEAD/GET
            # discard a good upload and cause re-uploads every poll cycle.
            cache[key] = url
            _save_cache(cache)
            _attempts.pop(key, None)
            if _validate_icon_url(url):
                logger.info(f"Uploaded & validated icon for {display_name}: {url}")
            else:
                logger.info(
                    f"Uploaded icon for {display_name}: {url} "
                    f"(validation couldn't confirm content-type, using anyway)"
                )
            return url

        _note_failure(key, display_name, f"upload failed on every host ({detail})", hard=False)
    else:
        _note_failure(key, display_name, "no icon resource to extract", hard=True)

    # 5. Fallback — `_note_failure` logged the detail; while parked this stays quiet.
    return default_url
