"""
icons.py — Extract exe icons, upload to a public host, cache results.

Pipeline:
  1. Check icon_cache.json for an existing URL.
  2. (Optional) Query SteamGridDB for a polished icon.
  3. Extract the icon from the exe via the Windows Shell API.
  4. Upload the PNG to a public host (catbox.moe by default).
  5. Verify the URL length and content-type.
  6. Cache the result.
"""

import ctypes
import ctypes.wintypes
import io
import json
import logging
import struct
import tempfile
from pathlib import Path

import requests
import win32api
import win32con
import win32gui
import win32ui
from PIL import Image

logger = logging.getLogger("autorpc.icons")

_BASE_DIR = Path(__file__).resolve().parent
_CACHE_PATH = _BASE_DIR / "icon_cache.json"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _load_cache() -> dict[str, str]:
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, str]) -> None:
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def clear_icon_cache() -> int:
    """Clear icon_cache.json, returning the number of cleared entries."""
    cache = _load_cache()
    count = len(cache)
    _save_cache({})
    logger.info(f"Cleared {count} entries from icon cache.")
    return count


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

def _upload_catbox(png_bytes: bytes, filename: str = "icon.png") -> str | None:
    """Upload a PNG to catbox.moe and return the direct URL."""
    try:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (filename, png_bytes, "image/png")},
            timeout=20,
        )
        resp.raise_for_status()
        url = resp.text.strip()
        if url.startswith("https://"):
            return url
        logger.warning(f"Catbox returned unexpected response: {url!r}")
        return None
    except Exception as exc:
        logger.debug(f"Catbox upload failed: {exc}")
        return None


def _upload_freeimage(png_bytes: bytes, filename: str = "icon.png") -> str | None:
    """Upload a PNG to freeimage.host and return the direct Cloudflare CDN URL (iili.io)."""
    try:
        resp = requests.post(
            "https://freeimage.host/api/1/upload",
            data={
                "key": "6d207e02198a847aa98d0a2a901485a5",
                "action": "upload",
                "format": "json",
            },
            files={"source": (filename, png_bytes, "image/png")},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            url = data.get("image", {}).get("url")
            if url and url.startswith("https://"):
                return url
        logger.warning(f"FreeImage upload returned status {resp.status_code}")
    except Exception as exc:
        logger.debug(f"FreeImage upload failed: {exc}")
    return None


# Registry of upload hosts
_UPLOAD_HOSTS = {
    "freeimage": _upload_freeimage,
    "catbox": _upload_catbox,
}


def _upload_png(png_bytes: bytes, host: str = "freeimage",
                filename: str = "icon.png") -> str | None:
    """
    Upload PNG with automatic multi-host fallback.
    Tries primary host first; if it drops or fails, immediately falls back to backup.
    """
    if host == "catbox":
        chain = [_upload_catbox, _upload_freeimage]
    else:
        chain = [_upload_freeimage, _upload_catbox]

    for uploader in chain:
        try:
            url = uploader(png_bytes, filename)
            if url:
                return url
        except Exception:
            continue
    return None


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

def get_icon_url(exe_path: str, display_name: str, config: dict) -> str:
    """
    Return a public URL for the application's icon.

    Checks cache → SteamGridDB → extract+upload → fallback.
    """
    default_url: str = config.get("default_icon_url",
                                  "https://cdn.discordapp.com/embed/avatars/0.png")
    host: str = config.get("upload_host", "freeimage")
    sgdb_key: str = config.get("steamgriddb_api_key", "")
    overrides: dict = config.get("overrides", {})

    exe_name = Path(exe_path).name.lower()

    # 1. Check config override for a manual icon_url
    for key, val in overrides.items():
        if key.lower() == exe_name and isinstance(val, dict):
            override_url = val.get("icon_url")
            if override_url and _validate_icon_url(override_url):
                return override_url

    # 2. Check cache
    cache = _load_cache()
    cached = cache.get(exe_path.lower())
    if cached and _validate_icon_url(cached):
        return cached

    # 3. Try SteamGridDB
    if sgdb_key:
        sgdb_url = _try_steamgriddb(display_name, sgdb_key)
        if sgdb_url and _validate_icon_url(sgdb_url):
            cache[exe_path.lower()] = sgdb_url
            _save_cache(cache)
            logger.info(f"SteamGridDB icon cached for {display_name}")
            return sgdb_url

    # 4. Extract from exe and upload
    img = _extract_icon_image(exe_path)
    if img is not None:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        safe_name = exe_name.replace(" ", "_").replace(".exe", "") + ".png"
        url = _upload_png(png_bytes, host=host, filename=safe_name)
        if url:
            # Cache immediately — upload returned a URL, so the file exists.
            # Validation is a secondary check; don't let a flaky HEAD/GET
            # discard a good upload and cause re-uploads every poll cycle.
            cache[exe_path.lower()] = url
            _save_cache(cache)
            if _validate_icon_url(url):
                logger.info(f"Uploaded & validated icon for {display_name}: {url}")
            else:
                logger.info(
                    f"Uploaded icon for {display_name}: {url} "
                    f"(validation couldn't confirm content-type, using anyway)"
                )
            return url

    # 5. Fallback
    logger.info(f"Using default icon for {display_name}")
    return default_url
