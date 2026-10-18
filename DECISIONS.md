# DECISIONS.md — Decision Log (append-only)

> **Purpose:** durable memory of *why* the code looks the way it does, so future
> sessions don't relitigate settled questions or undo load-bearing choices.
>
> **Rules**
> 1. **Append-only.** Never delete or rewrite an entry. To change course, add a new
>    entry and mark the old one `SUPERSEDED BY D-0XX`.
> 2. **Every non-obvious choice gets an entry** — architecture, tradeoffs, rejected
>    alternatives. If you had to think for more than a minute, log it.
> 3. Copy the template, use the next free `D-0XX` id, date it.
>
> **ID counter: next free id is `D-043`.**

### Template

```
## D-0XX — <short title>
- **Date:** YYYY-MM-DD
- **Status:** Accepted | Superseded by D-0YY | Rejected proposal
- **Context:** what forced a choice
- **Decision:** what we chose
- **Consequences:** what we now live with (good and bad)
- **Evidence:** files/symbols/commits
```

---

## D-001 — Windows-only, native Win32 implementation
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** The product needs the *foreground* window and its true executable, plus
  high-resolution icons. Cross-platform window-title APIs are lossy and cannot see
  process ownership or extract icon resources.
- **Decision:** Target Windows 10/11 x64 exclusively and use `win32gui`,
  `win32process`, `win32api`, `win32event`, and GDI directly.
- **Consequences:** No macOS/Linux port without a rewrite of `detector.py` + `icons.py`.
  In exchange we get exact exe paths, PIDs, PE metadata, and native icon extraction.
  Wrapped in `try/except` because `AccessDenied`/`NoSuchProcess` are routine on Windows.
- **Evidence:** `detector._get_foreground_app`, `icons._extract_icon_image`, `requirements.txt`.

## D-002 — Poll the foreground window on an interval instead of installing a WinEvent hook
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** `SetWinEventHook` gives instant focus change callbacks, but requires a
  running message pump and complicates the threading model.
- **Decision:** Poll `GetForegroundWindow()` every `poll_interval` (default 5s, hot-reloadable).
- **Consequences:** Up to one interval of latency on app switches, hidden behind the
  `debounce_seconds` gate anyway. Massively simpler and thread-safe. Polling cost is negligible.
- **Evidence:** `main._poll_loop`, `detector.Detector.poll`.

## D-003 — Each user supplies their own Discord Application ID
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Discord Rich Presence requires an application registered in the Discord
  Developer Portal. Shipping a shared App ID would make every user appear as the same
  application and risks the app being flagged/rate-limited centrally.
- **Decision:** First-run wizard walks the user through creating a personal app and
  pasting its numeric `application_id`; validated as a 17–20 digit snowflake.
- **Consequences:** A mandatory ~60s onboarding step, but the displayed "Playing …"
  name is user-controlled and each user is rate-limited independently. If the user
  picks their own app name, it *is* the presence header. `application_id` must persist
  across launches (see commit `6f34a75`).
- **Evidence:** `config.validate_app_id`, `gui.OnboardingWizardDialog`, `config.example.json`.

## D-004 — Use PyQt6 `QSystemTrayIcon` on the main thread (supersedes `pystray`)
- **Date:** 2026-10-12 · **Status:** Accepted (supersedes the pystray approach of `ea3a532`)
- **Context:** The original `pystray` tray icon rendered in dev but was **invisible in the
  PyInstaller `--onefile --noconsole` build**, because pystray owns its own event loop and
  fought the GUI threading model.
- **Decision:** Run the Qt event loop on the main thread, create the tray icon with
  `QSystemTrayIcon`, and marshal all cross-thread tray mutations through `TrayBridge`
  `pyqtSignal`s. `pystray` remains in `requirements.txt` but is no longer the tray owner.
- **Consequences:** Tray is reliably visible in compiled builds; the tray menu is a
  styled `QMenu` reusing the Discord dark QSS. Cost: an extra dependency (PyQt6) and the
  rule that **no Qt object may be touched from the poll thread**.
- **Evidence:** commit `e4b51f1`, `main._create_qt_tray`, `main.TrayBridge`, `main._make_qt_tray_icon`.

## D-005 — `--startup` dormant mode supersedes the `watcher.pyw` supervisor
- **Date:** 2026-10-12 · **Status:** Accepted, **legacy artifacts not yet removed**
- **Context:** To avoid running when Discord is closed, the app needs to start at login
  but stay dormant. The old design used a separate `watcher.pyw` process that polled for
  `Discord.exe` and launched `main.py`.
- **Decision:** `main.py` itself accepts `--startup`, starts dormant (hidden tray, no RPC)
  when Discord is absent, and wakes up + reconnects when Discord appears. Autostart is a
  Startup-folder shortcut created by `config.set_autostart_enabled()`.
- **Consequences:** One process instead of two; `auto_close_with_discord` now cleanly
  closes the RPC connection and hides the tray. **Leftover:** `watcher.pyw`,
  `enable_autostart.bat`, and `disable_autostart.bat` still create a *second* shortcut
  (`DiscordAutoRPCWatcher.lnk`) that `is_autostart_enabled()` also honors — this is
  tracked as `B-1`/`T-008` and should be resolved by deleting the watcher path.
- **Evidence:** `main.main` (`is_startup`, `start_dormant`), `main._poll_loop` dormant block, `config.set_autostart_enabled`, `watcher.pyw`.

## D-006 — Dedupe presence updates and never re-send an identical payload
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Naively calling `presence.update()` every poll cycle made Discord's UI
  timer jump every ~15s instead of ticking smoothly, because each payload resets the
  client-side elapsed timer.
- **Decision:** Compute a key `f"{exe_path}|{pid}|{icon_url}|{display_name}|{tagline}"`;
  if unchanged, skip the RPC call entirely. Separately enforce a 15s `RATE_LIMIT_SECONDS`
  between *different* updates. Track per-exe start epochs keyed by exe path so switching
  away and back does not reset the timer unless the PID changed.
- **Consequences:** Smooth per-second timer; fewer RPC calls; less rate-limit risk. The
  tradeoff is that any payload field change (e.g. a dynamic tagline) legitimately forces
  a new send, and `clear()` must reset `_last_sent_key`.
- **Evidence:** `presence.PresenceManager.update`, `presence._get_start_time`.

## D-007 — Prefer `StatusDisplayType.NAME` so the presence header shows the app name
- **Date:** 2026-10-12 · **Status:** Accepted (with graceful fallback)
- **Context:** Without it, Discord shows the *developer-portal application name* in the
  "Playing …" header, which is the user's generic app name, not the detected app.
- **Decision:** When `pypresence` exposes `StatusDisplayType`, send `name=display_name`
  + `status_display_type=StatusDisplayType.NAME` and put the tagline in `details`.
  Otherwise fall back to `details=display_name`, `state=tagline`.
- **Consequences:** Header reads "Playing Photoshop" correctly. On old `pypresence`
  versions the tagline lands on the state line instead — logged as a warning at import.
- **Evidence:** `presence.HAS_STATUS_DISPLAY_TYPE`, `presence.PresenceManager.update`.

## D-008 — Icons: extract from the exe and upload to a public host, with a disk cache
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Discord RPC `large_image` accepts an HTTPS URL (or a pre-registered asset
  key) — not a local file path. Users cannot be expected to upload art per app.
- **Decision:** Pipeline = config override → cache → optional SteamGridDB → extract icon
  → upload → cache. Extraction tries `PrivateExtractIconsW` (native 256×256) and falls
  back to `ExtractIconEx`; conversion goes through a 32-bit top-down DIB and PIL.
- **Consequences:** Crystal-clear icons for arbitrary apps with zero setup, at the cost of
  a network dependency and third-party hosting. Upload failures degrade to
  `default_icon_url`, never to a crash.
- **Evidence:** `icons.get_icon_url`, `icons._extract_icon_image`, `icons._hicon_to_pil`.

## D-009 — FreeImage primary, Catbox fallback; cache the URL even if validation is inconclusive
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Free public image hosts are individually flaky. Also, many CDNs reject
  `HEAD` requests and serve ambiguous `Content-Type`s.
- **Decision:** Maintain an ordered host chain (`freeimage`↔`catbox` based on
  `upload_host`), and treat the successful upload response as authoritative: cache the URL
  immediately, then validate as a *secondary* check. Trust a whitelist of known hosts
  (catbox, iili.io, discordapp CDN, steamgriddb) with image extensions without probing.
- **Consequences:** Avoids re-uploading the same icon every poll cycle when a CDN's
  content-type check is fuzzy. Slight risk of caching a URL that later 404s — acceptable,
  since re-extraction is cheap and the cache can be cleared from the Settings GUI.
- **Evidence:** `icons._upload_png`, `icons._validate_icon_url`, `icons._TRUSTED_IMAGE_HOSTS`,
  `gui._reset_icon_cache`.

## D-010 — Display name from PE version resources, with category-suffix stripping
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Filenames like `photocraft_launcher_x64.exe` are ugly on a Discord profile,
  and `FileDescription` frequently includes marketing categories ("PhotoCraft image editor").
- **Decision:** Resolution priority = config override → PE `ProductName`/`FileDescription`
  → Title-Cased filename stem. Strip trailing category/arch tokens via
  `_CATEGORY_SUFFIX_REGEX`; when the description starts with the product name, prefer the
  product name as the concise brand.
- **Consequences:** Clean names for most Windows apps without configuration. Imperfect for
  apps with noisy metadata, mitigated by the 1-click rename + overrides manager.
- **Evidence:** `detector.resolve_display_name`, `detector._clean_display_name`, `detector._extract_pe_version_strings`.

## D-011 — Dynamic taglines derived from window titles, gated by a config flag
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Static per-app taglines ("Surfing the internet") are safe but dull; window
  titles contain the genuinely interesting context (file, video, repository).
- **Decision:** `context.extract_dynamic_tagline()` parses titles for browsers (curated
  platform recognizers), Office, Notion/Obsidian, IDEs, and media players. Precedence:
  override → dynamic → user tagline → built-in table → keyword match → empty.
  Controlled by `enable_dynamic_taglines`. All output passes `_clean_title`
  (strips `(4) ` unread badges, `●/*/•` dirty marks) and `_truncate` (128-char RPC limit).
- **Consequences:** Rich, personalized statuses. Risk: window titles can leak sensitive
  info, so URL/email-shaped candidates are rejected and the whole feature is toggleable.
  Parser failures fall back to static taglines — never to a raw title.
- **Evidence:** `context.extract_dynamic_tagline`, `context._BROWSER_PLATFORMS`, `detector.resolve_tagline`.

## D-012 — Skip anything under `%SystemRoot%`, plus a layered ignore/whitelist system
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Shell surfaces (`explorer.exe`, `SearchHost.exe`, `LockApp.exe`, …) would
  otherwise spam tiny, meaningless presences.
- **Decision:** Four filters applied in order: (1) any exe path under `%SystemRoot%` is
  ignored; (2) config `ignored_exes`; (3) runtime-added `ignore_list.json` (from the tray
  "Ignore current app" action); (4) `whitelist_only` mode, when enabled, requires an
  explicit `whitelist` entry. Plus the privacy gate (D-013).
- **Consequences:** Sensible defaults out of the box, with both deny-list and allow-list
  escape hatches. Note that a tracked app living under `C:\Windows` can never be shown —
  accepted as a deliberate simplification.
- **Evidence:** `detector.is_ignored`, `detector.load_ignore_list`, `config.DEFAULT_CONFIG["ignored_exes"]`.

## D-013 — Mask private/incognito browser windows by default
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Broadcasting "Surfing the internet" while the user is in a private window
  is a privacy hazard *and* leaks the very fact they're browsing privately.
- **Decision:** `is_incognito()` matches incognito/private markers in the title for the 8
  known browser exes; when matched the app is treated as ignored. On by default
  (`mask_private_browsing: true`).
- **Consequences:** Privacy-safe. Marker matching is heuristic per browser vendor wording,
  so new browsers/wordings need the token list extended.
- **Evidence:** `detector.is_incognito`, `detector._BROWSER_EXES`, `config.DEFAULT_CONFIG`.

## D-014 — Data directory: portable next to the exe, else `%APPDATA%\DiscordAutoRPC`
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** A `--onefile` exe may be run from a read-only location (Program Files,
  Downloads) where writing `config.json` next to it fails. But portable users want
  self-contained folders.
- **Decision:** Frozen: if `portable.txt` or `config.json` exists beside the exe, use that
  directory; otherwise use `%APPDATA%\DiscordAutoRPC`, copying in a nearby `config.json`
  on first run. Unfrozen (dev): use the repo root.
- **Consequences:** Users are never silently unconfigured after an update. Caveat: modules
  resolve the path at **import time** (`detector._BASE_DIR`, `icons._CACHE_PATH`).
- **Evidence:** `config.get_data_dir`, `detector._BASE_DIR`, `icons._CACHE_PATH`.

## D-015 — PyQt6 as the GUI toolkit
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** A settings GUI, modal wizard, and live log terminal were needed; the
  existing pystray/tkinter-era UI could not deliver consistent dark theming or a tray menu
  that survives `--onefile`.
- **Decision:** Standardize on PyQt6 with a single Discord-dark QSS string
  (`gui.DISCORD_DARK_QSS`) and one `QApplication` instance via `_ensure_qapp()`.
- **Consequences:** Consistent, polished dark UI and native tray integration. Cost:
  PyQt6's LGPL/GPL licensing and a large binary size (~onefile exe). Version pin `>=6.6.0`.
- **Evidence:** `gui.DISCORD_DARK_QSS`, `gui._ensure_qapp`, `requirements.txt`.

## D-016 — Live log terminal via a `logging.Handler` bridged to a Qt signal
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Users debugging detection needed visibility without a console
  (`--noconsole` builds have none), and log lines originate on a background thread.
- **Decision:** `QtLogHandler` forwards formatted records through `LogEmitter.log_signal`
  (a `pyqtSignal`) so the settings window can append them thread-safely; the window also
  tails the last 200 lines of `autorpc.log` on open. File logging is a
  `RotatingFileHandler` (2 MB × 3).
- **Consequences:** Debuggable UI builds, copy/export support, and one log source of truth.
  Caveat: the root logger is set to DEBUG and the Qt handler is attached eagerly in
  `gui.py` at import (module-level), so the terminal receives verbose logs.
- **Evidence:** `gui.QtLogHandler`, `gui.GLOBAL_EMITTER`, `main._setup_logging`.

## D-017 — `config.example.json` is maintained by hand and must mirror `DEFAULT_CONFIG`
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** The release zip ships `config.example.json` as a user-facing template, but
  the app's real defaults live in `config.DEFAULT_CONFIG`.
- **Decision:** Keep both hand-synced. Accepted the duplication for now.
- **Consequences:** Drift is possible (and has happened — see D-018's docstring drift and
  `B-6`'s duplicated tagline table). Any config change must touch both, plus the GUI and
  README if user-facing.
- **Evidence:** `config.py::DEFAULT_CONFIG`, `config.example.json`.

## D-018 — Single-instance enforcement via a named mutex + wake event
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Double-launching (e.g. user double-clicks the exe while autostart already
  ran it) would create two RPC connections and duplicate polling.
- **Decision:** Acquire `DiscordAutoRPC_SingleInstance_Mutex`; a second instance signals
  `DiscordAutoRPC_Wakeup_Event` and exits. The running instance polls that event and opens
  the Settings window (also un-hiding the tray if dormant).
- **Consequences:** Predictable single-process behavior and a nice "second click opens
  settings" UX. Requires the `pywin32` event APIs and careful handle cleanup.
- **Evidence:** `main.main` mutex block, `main.TrayBridge`, `main._poll_loop` wakeup checks.

## D-019 — Release automation: tag-triggered GitHub Actions on Windows
- **Date:** 2026-10-12 · **Status:** Accepted
- **Context:** Shipping a Windows binary requires a Windows runner and a reproducible build.
- **Decision:** On a `v*` tag, `windows-latest` + Python 3.12 builds a `--noconsole
  --onefile` exe with PyInstaller, zips it with `config.example.json`, `LICENSE`, and
  `README.md`, and attaches everything to a **prerelease** GitHub Release.
- **Consequences:** One-command release (`git tag vX.Y.Z && git push origin vX.Y.Z`).
  Releases are always prerelease until explicitly flipped — appropriate for beta.
  There is **no CI test/lint job**.
- **Evidence:** `.github/workflows/build-release.yml`, `DiscordAutoRPC.spec`.

---

# GUI rewrite (Tauri + React) — G0 decisions, 2026-10-18

> The entries below were issued by the owner at gate **G0** of the GUI rewrite and are recorded
> here because they are deviations from the handoff spec
> (`GUI_HANDOFF_TAURI_REACT.md`) and because they are load-bearing for everything after them.
> They are **scoped to the rewrite**: they do not change the shipped Python/Qt build, except
> where noted (`D-037`, the unified ignore list). Handoff cross-references use the `A1`…`A23`
> amendment IDs defined in that document's §0.1.

## D-020 — Adopt the macOS System Settings layout language inside a native Windows frame
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The Qt GUI is a 5-tab dialog on a Discord-dark theme. Two directions were
  available: iterate on the Windows/11 idiom (ribbon, Fluent), or adopt the sidebar + grouped
  inset-list layout that users now associate with "modern settings".
- **Decision:** Take the **layout and component language** of macOS System Settings — sidebar
  navigation, grouped inset cards, label-left/control-right rows — but keep a **native Windows
  frame**. Native decorations are retained; no fake traffic lights, no custom titlebar in v1.
- **Consequences:** The interior can be redesigned freely while snap layouts, maximize, DPI
  correctness, and accessibility keep working for free. Consistent with `D-022` (no fake glass);
  a frameless window would have made both harder. Do not "improve" this later by drawing a
  fake titlebar.
- **Evidence:** `GUI_HANDOFF_TAURI_REACT.md` §0.1 `A1`, §5.6; audit row `UI-3`.

## D-021 — Emoji and glyph-as-icon characters are banned in the rewrite
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The Qt build uses emoji as UI icons (`⚙️`, `🏷️`, `💬`, `🚫`, `🖥️`) and as success
  marks (`✓`, `⭐`). Emoji glyph coverage varies by Windows font version, so the same binary
  renders differently across machines and can show tofu.
- **Decision:** **No emoji anywhere** — not in the UI, copy strings, tray labels, or toasts.
  Also no typographic glyphs used as icons (`✓`, `⭐`). Use one icon library at one size and one
  stroke weight, with `aria-label` on icon-only controls.
- **Consequences:** Every emoji quoted in the handoff's §4 inventory is superseded by this rule;
  copy that relied on an emoji for emphasis must carry meaning in words. Adds a bundled font
  requirement (see `D-028`) so glyphs don't depend on the OS.
- **Evidence:** `gui.py` tab labels; handoff §0.1 `A2`, §5.8; audit row `UI-1`.

## D-022 — No vibrancy, glass, or gradients in v1; solid surfaces only
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The handoff proposed a Mica/acrylic backdrop on Windows 11 via
  `window-vibrancy`. Separately, the temptation exists to fake depth with CSS
  `backdrop-filter`.
- **Decision:** **Solid surfaces only in v1.** No vibrancy, no glass, no gradients. CSS
  `backdrop-filter` is explicitly rejected: it cannot blur the desktop *behind* the window
  (the webview only composites its own layer), so the effect would be a fake. **Mica is
  optional later**, and if adopted must degrade to a solid surface on Windows 10 and in both
  themes.
- **Consequences:** Both themes are defined purely by the token sheet (§8.1 of the handoff),
  which makes contrast auditable and screenshots reproducible. Rejected alternative: an
  acrylic-styled CSS layer, which would have looked wrong over bright wallpapers.
- **Evidence:** handoff §0.1 `A3`, §5.6; audit row `UI-2`.

## D-023 — Light / Dark / System appearance control (reverses the dark-only deferral)
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The handoff deferred light mode with the line "dark-only is the brand", on the
  grounds that a second theme doubles the design and verification surface.
- **Decision:** **Reversed.** A user-facing Appearance control (segmented: **System / Light /
  Dark**) ships in Settings → General. Default is **System**, which follows the OS live,
  including while Settings is open. Dark-only is no longer a defensible position for a utility
  that sits next to Explorer and Discord on a light desktop.
- **Consequences:** Every component must be audited in both themes; contrast is a gate item, not
  a nitpick (`D-026`). This is the single largest scope addition at G0 and it must be reflected
  in the G1 wireframes and the G2 screenshots.
- **Evidence:** handoff §0.1 `A4`, §2, §8.1; audit rows `THEME-1`…`THEME-5`.

## D-024 — The appearance preference lives in `ui_prefs.json`, not `config.json`
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** `config.json` is the shared contract with the shipped Python/Qt build; adding a
  key risks a build that doesn't understand it rewriting or dropping it.
- **Decision:** A **new file**, `ui_prefs.json`, in the same data dir (per `config.get_data_dir()`
  semantics, `D-014`), holding UI-only state: `{ "appearance": "system|light|dark" }`. It is
  written **only** by a backend command (native side), never by the frontend, and atomically.
  A missing file or key means `System`.
- **Consequences:** `config.json` stays byte-compatible so the two builds can share a data dir
  during migration. Adds one file to the "user data" set in `AGENTS.md` §4 and one IPC command
  pair (`get_ui_prefs` / `set_ui_prefs`). Rejected alternative: `localStorage` in the webview,
  which is invisible to the engine and fragile across webview data resets.
- **Evidence:** handoff §0.1 `A5`, §6.1, §6.2; audit row `THEME-2`.

## D-025 — The native frame theme follows the in-app appearance choice
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** With native decorations retained (`D-020`), the OS draws the title bar. If the
  user picks Dark inside the app while Windows is in light mode, the frame stays light.
- **Decision:** Call the window's `set_theme` with Light, Dark, or **None** (System) whenever the
  appearance changes at runtime, so the title bar and borders track the in-app choice.
- **Consequences:** One more IPC command (`set_window_theme`). Chosen over a frameless window,
  which would have removed the problem by removing snap layouts and accessibility.
- **Evidence:** handoff §0.1 `A6`, §6.2; audit row `THEME-4`.

## D-026 — Theme token architecture and the accent-colour contrast requirement
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** Two themes can be implemented as duplicated stylesheet rules, as a class swap, or
  as a token cascade. Duplication guarantees drift; a class swap without a media query breaks
  "follow the OS live".
- **Decision:** **Every colour is a CSS variable; components never hard-code a colour.** Cascade
  exactly: light tokens on `:root`; dark tokens under `@media (prefers-color-scheme: dark)`
  guarded by `:root:not([data-theme="light"])`; dark tokens again under `:root[data-theme="dark"]`.
  `System` removes the attribute so the media query wins and OS changes are followed live.
  **Stock Apple blues are rejected as the accent fill**: `#007AFF` / `#0A84FF` measure only
  4.02 / 3.65 against white text and fail AA. The fills are deliberately darker (`#0071E3` /
  `#0A6FE0`, 4.70 / 4.81). `accent` is a single token, so brand blurple (`#5865F2`) is a
  one-line swap — but the `accent.text` variants must then be re-checked.
- **Consequences:** The full token and contrast tables are normative in the handoff (§8.1).
  Pairs not measured there (e.g. light `text.secondary` on `bg.hover`) must be verified at G1.
  **State must never be conveyed by colour alone.** A hard-coded colour is a rejection reason.
- **Evidence:** handoff §0.1 `A7`, §8.1; audit rows `A11Y-3`, `THEME-5`, `RSK-13`.

## D-027 — No-flash boot sequence and an instant theme switch
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** A webview app that shows its window before the theme resolves flashes white (or
  black) on every open. The usual fix is an inline script in the HTML, which is banned here
  (`SEC-1`).
- **Decision:** The window **starts hidden**. The backend resolves the stored preference, sets
  the window background to the resolved theme colour **before showing**, and the frontend entry
  module sets `data-theme` **synchronously** before React renders. The window is shown after
  first paint. **No inline script.** Separately, a theme switch is **instant** — no colour
  transition, no crossfade.
- **Consequences:** Requires a real "ready" handshake between the frontend and the backend
  shell. Adds a hard rejection reason at G2 for both themes.
- **Evidence:** handoff §0.1 `A8`, §8.4; audit row `THEME-3`, `RSK-13`.

## D-028 — Type, icon, and shape system (Inter bundled locally)
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The rewrite needs one typographic and geometric system. Two constraints decide
  most of it: the CSP forbids remote fonts, and SF Pro is not licensed for non-Apple platforms.
- **Decision:** **Inter**, bundled with the app, falling back to Segoe UI Variable then
  `system-ui`. Log font: Cascadia Mono → Consolas at 12px. Scale **20 / 15 / 13 / 12** with
  weights **400 / 500 / 600 only**. Icons: Lucide (or Phosphor) at one stroke weight (~1.5),
  16px in the sidebar, `currentColor`. Shape: 4px grid, **10px** card radius, **6px** control
  radius, 1px hairlines, shadows **only** on popovers and dialogs. Window: resizable, min
  **820×560**, state restored, title **"Settings"**, ~**680px** centred content column.
- **Consequences:** Font licensing is not a risk and offline rendering is correct. Bundling adds
  ~100–300 KB of woff2 and a build step to keep the subsets current. No SF Symbols.
- **Evidence:** handoff §0.1 `A9`, §8.2, §8.3; audit row `FONT-1`.

## D-029 — The tray icon must be legible on light *and* dark taskbars
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The current tray icon is a single PNG generated from `assets/icon.png`. The
  taskbar theme is independent of the app theme — a user can run the app in light mode on a dark
  taskbar and vice versa.
- **Decision:** Ship a **multi-resolution `.ico`** (16/20/24/32/48) for the normal state **and**
  the paused state, and verify each against both taskbar themes. Legibility on the taskbar is a
  separate requirement from the in-app palette.
- **Consequences:** `TR-1`/`TR-2` gain a verification step; the G2 gate explicitly includes a
  taskbar check on both themes. Blur at high DPI is no longer an acceptable outcome.
- **Evidence:** handoff §0.1 `A10`, §4.10; audit row `THEME-6`.

## D-030 — Six-pane sidebar navigation; command palette and `Ctrl+K` dropped
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The handoff proposed a sidebar with 7–8 sections and a `Ctrl+K` command palette as
  a cheap "modern" signal. The G0 direction (`D-021`, `D-022`, restraint) argues against adding
  an interaction surface that isn't needed.
- **Decision:** The sidebar has exactly **six** panes, in order: **Status, General, App Names,
  Taglines, Ignored Apps, Logs.** Shortcuts are `Ctrl+1…6` for sections and `Esc` for dialogs
  and popovers. **The command palette and `Ctrl+K` are dropped**; `Ctrl+S` is obsolete under
  autosave (`D-031`).
- **Consequences:** Handoff rows `SS-1` and `SS-3` are amended and §5.9 is withdrawn. Pane
  labels are plain text (`D-021`). Revisit the palette only on explicit owner request.
- **Evidence:** handoff §0.1 `A11`, §4.3, §5.1, §5.9.

## D-031 — Autosave replaces the Save button (resolves `SEM-3` and `SEM-8`)
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The Qt build mixed four save semantics, and `Save All Changes` refused to save
  *anything* if the App ID was invalid — so adding a tagline could be blocked by an unrelated
  field (`SEM-8`). The handoff listed this as the owner's call.
- **Decision:** **Autosave. There is no Save button.** Commit points: **toggles write
  immediately**; **steppers are debounced**; **text fields write on blur or `Enter`**. An invalid
  field **never writes and never blocks any other field** — errors are inline and scoped to that
  field. Every mutation is **atomic** (temp + rename) and **optimistic with rollback** on backend
  error, followed by a toast. Removals offer Undo. The engine is notified on every mutation.
- **Consequences:** `SS-2` (the Save/Close bar) is dropped; `SEM-3` is replaced, `SEM-8` is
  decomposed, `SEM-5` (autostart) writes on toggle and must read the real OS state back. The
  Settings window no longer closes after a save, because there is no save. New risk: eager writes
  (`RSK-14`) — test rapid typing and a held stepper arrow.
- **Evidence:** handoff §0.1 `A12`, §4.12, §3.2 of the G0 note.

## D-032 — Control vocabulary: switches, steppers, segmented controls, inset lists
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The Qt build uses checkboxes for booleans, `QSpinBox` (`0–3600`) for timing, and
  tables for every list — three different interaction idioms for two kinds of data.
- **Decision:** Use **switches** (`role="switch"`) instead of checkboxes; a **number field with a
  stepper** for `debounce_seconds` and `idle_timeout_seconds`; **segmented controls** for small
  mutually-exclusive sets (appearance, log level); and **grouped inset lists** (label left,
  control right, description under the label) for settings groups.
- **Consequences:** Checkboxes and data tables disappear from the component inventory; `Tabs`
  and `CommandPalette` are also removed. A switch is a commit-on-toggle control, which is exactly
  the autosave model in `D-031`.
- **Evidence:** handoff §0.1 `A13`, §8.3.

## D-033 — Feedback model: bottom-centre toast pill, inline validation, dialogs only for destructive actions
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The Qt build routes eight distinct events through blocking `QMessageBox` calls,
  including pure successes ("Copied", "Saved"). Under autosave, a modal per commit would be
  unusable.
- **Decision:** A quiet **toast pill at bottom-centre** with an optional **Undo** action
  (`aria-live="polite"`), **inline** validation adjacent to the field, and **alert-style dialogs
  only** for destructive or irreversible actions: reset icon cache, reset settings, multi-delete.
  All eight `QMessageBox` call sites are replaced.
- **Consequences:** `FB-1`…`FB-4` are amended. Toasts must be non-blocking and never steal focus;
  Undo must be a real reversal, not a re-do. A success path that opens a modal is a rejection
  reason at G3/G4.
- **Evidence:** handoff §0.1 `A14`, §4.11.

## D-034 — "Status" is a full landing pane, not a card
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The handoff's biggest proposed upgrade was a live "Now Broadcasting" surface,
  described as a card that could appear in several places. It also proposed a "why this tagline?"
  disclosure showing which rule won.
- **Decision:** Ship it as a **single dedicated pane named "Status"**, first in the sidebar and
  the default landing surface, showing: app icon, display name, resolved tagline, ticking timer,
  Discord connection state (text + indicator), and Pause/Resume, Rename, Ignore this app.
  **The "why this tagline?" disclosure is deferred.**
- **Consequences:** Answers Q9. The card is not duplicated across panes. The rename action here
  and the standalone rename window (`D-040`) share one component.
- **Evidence:** handoff §0.1 `A15`, §5.3.

## D-035 — General pane composition *(provisional pending Q5)*
- **Date:** 2026-10-18 · **Status:** Accepted — **provisional**
- **Context:** The Qt General tab mixes Discord credentials, four unrelated toggles, and two
  spin boxes, with no grouping.
- **Decision:** Group the pane into: **Discord** (Application ID with inline validation,
  "Test connection", "Re-run setup"); **Behaviour** (auto-close with Discord, launch at login
  reading the real OS state, mask private browsing — not buried, not default-off, smart dynamic
  details with a hint and example); **Timing** (debounce 2–60 s, idle timeout 10–600 s, each with
  a one-line trade-off note); **Appearance** (System/Light/Dark, `D-023`); **Advanced**
  (`poll_interval`, `whitelist_only`, `upload_host` with a privacy disclosure, and the
  SteamGridDB key); and a destructive **Reset** with "export config first".
- **Consequences:** Covers `G-1`…`G-12`. The **Advanced group's visibility is Q5, still open** —
  this entry is provisional until that is answered, and Q5 blocks G1. `mask_private_browsing` is
  a privacy feature (`D-013`) and must not become default-off.
- **Evidence:** handoff §0.1 `A16`, §4.5.

## D-036 — List panes: one inset-list pattern, normalization preserved verbatim
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** App Names, Taglines, and Ignored Apps are three differently-built Qt tables with
  select-then-click-Delete interactions. The exe-key normalization (lowercase + `.exe`) is
  load-bearing and easy to "clean up" by accident.
- **Decision:** All three panes use the **same inset-list pattern**: a filter field above, a
  `+` / `−` bar below, adding via a small popover, deleting via `−` **and** the `Delete` key,
  with an undo toast. **Normalization is preserved exactly** (lowercase + `.exe`) —
  `O-4`/`T-4`/`I-3` are behavior contracts, not style. Recent-app suggestions and real empty
  states. **Taglines** additionally gets a live preview, a character counter that warns near
  128, built-ins rendered as a read-only group (`T-6`), and the precedence one-liner (`T-7`).
- **Consequences:** The data-grid `Table` component is not part of v1 for these panes. A
  normalization difference is a rejection reason at G3.
- **Evidence:** handoff §0.1 `A17`, §4.4/§4.6/§4.7.

## D-037 — The two ignore lists are merged into one source of truth (must resolve before G1)
- **Date:** 2026-10-18 · **Status:** Accepted — implementation pending at G1
- **Context:** `config.ignored_exes` (Settings → Ignored Apps) and `ignore_list.json` (tray →
  "Ignore current app") are **different stores**. Ignoring an app from the tray never makes it
  appear in Settings, and removing it in Settings does not stop the engine from skipping it.
  This is the #1 correctness trap in the current GUI (`I-5`, `RSK-6`).
- **Decision:** **One list.** `ignore_list.json` is retired as a separate store; existing entries
  are **migrated** into the unified list. Built-in defaults and the `%SystemRoot%` skip
  (`D-012`) are shown as a **read-only group** so the user can see *why* an app is being skipped.
  The design must be approved at G1.
- **Consequences:** Migration must be **idempotent** and must not lose entries if the app is
  closed mid-migration. The tray and the pane read and write the same store (`SEM-4`). Because
  this touches the shared data dir, this is the one G0 decision that also affects the Python
  build's files — it must be reversible and documented in the release notes.
- **Evidence:** handoff §0.1 `A18`, §4.7 `I-5`; `detector.py` ignore handling; `config.py::DEFAULT_CONFIG`.

## D-038 — Logs pane is Console-style; the detection digest is deferred
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The Qt log tab is a read-only `QPlainTextEdit` at 9pt with three buttons: Copy,
  Export, Clear, plus a quick-rename field bolted on.
- **Decision:** A Console-style pane: **search with highlight**, a **minimum-level segmented
  control** (Debug / Info / Warning / Error), a **follow toggle** with "Jump to latest", **Copy**
  (visible lines only), **Export…** (backend write via a native save dialog), **Clear View**
  (labelled so it is obviously not deleting the file), and **Reset Icon Cache** with a confirm
  and the entry count. The existing throughput requirements (`PERF-1`) are unchanged. The
  proposed **detection digest is deferred**.
- **Consequences:** Export must go through the backend — the frontend never gets filesystem
  access (`SEC-2`). Rename is removed from this pane (`D-040`).
- **Evidence:** handoff §0.1 `A19`, §4.8, §5.5.

## D-039 — Onboarding becomes a 3-step Setup Assistant
- **Date:** 2026-10-18 · **Status:** Accepted — cancel behaviour pending Q4
- **Context:** The Qt wizard is a single 640×720 scrollable page with a Back button that is
  always disabled and a 220px link-button in place of a proper portal step.
- **Decision:** A **three-step** assistant in its own window, centred single column, with real
  **Back / Continue**: (1) Welcome; (2) Create the app in the Developer Portal — opening the same
  URL via the opener, with numbered sub-steps; (3) Paste the App ID, with the two defaults-on
  toggles, and a **Verify connection** step (`OB-12`). Do not hide the portal button behind a
  step the user cannot complete.
- **Consequences:** `OB-13` is amended to a definite 3-step stepper; `OB-12` (a dry-run
  connection test before saving) becomes part of step 3. **Cancel behaviour is Q4 and still open** —
  today it exits the app, which is a first-run dead end.
- **Evidence:** handoff §0.1 `A20`, §4.2; `gui.OnboardingWizardDialog`.

## D-040 — Quick rename is a standalone window *and* a Status-pane sheet
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** Quick rename is invoked from the tray. Native tray menus (`D-041`) cannot anchor
  a webview popover — the menu owns the click and dismisses on blur.
- **Decision:** Quick rename is a **small standalone window** (two fields, a live "Playing …"
  preview, Cancel / Apply) **and** the same component appears as a **sheet on the Status pane**.
  An empty tagline means "fall back to automatic" (`R-4`/`R-7`), applied instantly.
- **Consequences:** Not a blocking modal. The preview keeps the exact "Playing …" framing. This
  is a UI over the existing instant-apply rename action (`SEM-2`), so no new engine work.
- **Evidence:** handoff §0.1 `A21`, §4.9; `gui.QuickRenameDialog`.

## D-041 — Tray uses the native menu, plain text, no emoji
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The Qt `QMenu` is dark-themed and matches the app. Native Win32 menus (Tauri/muda)
  are OS-rendered and **cannot be styled**. This was flagged as the top implementation risk.
- **Decision:** **Use the native menu.** Accept the loss of styling. Labels are plain text (no
  emoji, `D-021`). All existing states and dynamic relabelling are preserved (`TR-1`…`TR-16`).
- **Consequences:** Closes `RSK-1`. Expected benefit: correct behaviour at every DPI, real
  accessibility, correct multi-monitor placement, and the Windows 11 menu look for free. A custom
  borderless webview popup is **rejected for v1**; proposing it later is a scope change requiring
  owner sign-off.
- **Evidence:** handoff §0.1 `A22`, §4.10; `main.py` tray menu construction.

## D-042 — Gate additions: both-theme tokens, both-theme evidence, and per-ID decision references
- **Date:** 2026-10-18 · **Status:** Accepted
- **Context:** The original neutral gate set (`G0`…`G6`) assumed one theme and did not require
  traceability from a changed requirement back to its decision.
- **Decision:** **G1** additionally requires the token sheet for both themes with the contrast
  table, and wireframes of all surfaces **in both themes** including empty, loading, and error
  states, plus the resolved unified ignore-list design. **G2** additionally requires screenshots
  of every pane in light and dark at 100/150/200%, no flash on open in either theme, a live
  System-mode OS change being followed, the appearance choice surviving a restart, and the tray
  icon verified on light and dark taskbars. **G5** requires the parity table with evidence and a
  `DECISIONS.md` reference for **every changed ID** (`SS-1`, `SS-2`, `SS-3`, `R-1`, `OB-13`, the
  `SEM-*` autosave decision, and the §2 / §8.1 reversals).
- **Consequences:** The gate list is stricter than the original, and the traceability requirement
  makes silent behaviour changes detectable. `AGENTS.md` needs no change; the ritual in it
  ("stale docs are bugs") already implies the handoff is the spec and this log is the court of
  record.
- **Evidence:** handoff §0.1 `A23`, §11, §14.

## D-043 — Q1 answered: Tauri shell around the existing Python engine, joined by a stdio sidecar
- **Date:** 2026-10-18 · **Status:** Accepted (owner answered Q1)
- **Context:** The rewrite could either replace the engine or keep it. The engine holds the
  Windows-only logic that is hardest to re-derive: foreground polling, PE-metadata display names,
  title parsing, GDI icon extraction, and the presence dedupe/rate-limit rules.
- **Decision:** **Option A.** The Tauri 2 + React shell owns the UI, the tray, the window theme,
  `config.json` / `ui_prefs.json` / the ignore list, and the log surface. The existing Python
  engine becomes a **sidecar** that speaks **JSON-lines over stdio**. The frontend is written
  against the IPC contract only, so the later move to a full Rust engine (if it ever happens)
  cannot require a UI rewrite.
- **Consequences:** No engine rewrite in Phase 1, and the Python build keeps working. Two
  processes and a protocol to define (`T-022`). Until that protocol exists the shell runs a mock
  engine and **never auto-spawns `main.py`** (`D-050`).
- **Evidence:** handoff §2, §3, §13 `Q1`; `desktop/src-tauri/src/engine.rs`.

## D-044 — Q4 answered: onboarding's Cancel is "Set up later", never a dead end
- **Date:** 2026-10-18 · **Status:** Accepted (owner answered Q4)
- **Context:** The Setup Assistant needs an Application ID, but a user may not have one yet. The
  old wizard's Cancel closed the app.
- **Decision:** **"Continue without connecting."** The dismiss control reads **Set up later**, the
  app keeps running unconfigured, the tray stays functional, and General carries a persistent
  **Set up Discord** affordance (the Status pane points at it).
- **Consequences:** An unconfigured install is a supported state, not a broken one. `get_state`
  reports `configured: false` and the Status pane explains what is missing instead of showing an
  empty timer.
- **Evidence:** handoff §4.2 `OB-10`, §13 `Q4`; `desktop/src/windows/Onboarding.tsx`.

## D-045 — Q5 answered: the Advanced group is visible in General
- **Date:** 2026-10-18 · **Status:** Accepted (owner answered Q5; resolves the provisional note in D-035)
- **Context:** `D-035` was written as provisional precisely because "should ordinary users see
  `poll_interval`, `whitelist_only` and the SteamGridDB key?" was still open (`Q5`).
- **Decision:** **Visible.** General ends with an **Advanced** group holding poll interval, the
  allow-list switch plus its list, the icon upload host with a privacy note, and the SteamGridDB
  key. Nothing is hidden behind a disclosure triangle, and no setting is unreachable from the UI.
- **Consequences:** `D-035` stands with the provisional note resolved. The cost is a longer General
  pane; the benefit is that the "everything is a dead end" failure mode of the old Advanced tab
  cannot recur. `whitelist_only` still carries the "this is the usual cause of nothing broadcasting"
  warning inline.
- **Evidence:** handoff §13 `Q5`, `D-035`; `desktop/src/panes/GeneralPane.tsx`.

## D-046 — No-flash boot: hidden window + a `ready` handshake with the backend
- **Date:** 2026-10-18 · **Status:** Accepted (deviation from the literal `A8` reading)
- **Context:** `A8` asked for a synchronous `data-theme` before React renders, which in practice
  means an inline `<script>` in `index.html`. That is exactly what a strict CSP
  (`script-src 'self'`) is designed to prevent, and it cannot know the *saved* preference without
  either a blocking read or a value baked into the URL.
- **Decision:** **Invert it.** Every window is created **hidden**; the frontend boots, awaits
  `getPrefs()`, applies `data-theme`, waits two animation frames, and only then calls
  `invoke("ready")`. The backend paints the OS frame theme *and* the webview background colour
  before it shows the window. No inline script, no boot value in the URL or hash.
- **Consequences:** No flash in either theme, and CSP stays strict. The trade-off: a window that
  fails to boot would stay invisible, so the backend shows it anyway after four seconds. The
  `Theme` token sheet and `apply_theme` must stay in step (`--bg` in `tokens.css`).
- **Evidence:** `desktop/src/lib/boot.ts`, `desktop/src/lib/theme.ts`,
  `desktop/src-tauri/src/windows.rs`, `desktop/src-tauri/src/commands.rs::ready`; `A8`, `THEME-3`.

## D-047 — One ignore store: `config.ignored_exes`
- **Date:** 2026-10-18 · **Status:** Accepted (resolves `D-037`; verified against `detector.py`)
- **Context:** `D-037` said the two lists must become one without breaking the Python build.
  Reading `detector.is_ignored` settled what they actually are: **(1)** anything under
  `%SystemRoot%`, hardcoded; **(2)** `config.ignored_exes`, seeded with twelve Windows apps;
  **(3)** `ignore_list.json`, written by the Python tray. The Qt Settings pane showed only (2),
  so tray-added entries were invisible in the UI — the real bug.
- **Decision:** **`config.ignored_exes` is the one store.** Both the tray's *Ignore current app*
  and the Ignored Apps pane write it, because it is where the shipped defaults already live and
  where the Python Settings pane already wrote. On startup, any `ignore_list.json` entry missing
  from it is **copied across** (union, idempotent, reversible). The file itself is neither deleted
  nor rewritten; anything still uncopied is shown in an **Added elsewhere** group. Entries that
  are part of the shipped twelve are tagged *shipped default* but are fully editable. The only
  truly read-only rule is `%SystemRoot%`, which is stated in prose rather than listed as
  removable rows.
- **Consequences:** One list a user can reason about, no hidden entries, and the Python build
  keeps reading every file it knows. Deviates from the earlier `I-5`/`I-6` wording (which assumed
  the tray list was managed and the config list was read-only) — the code is the corrected model.
- **Evidence:** `detector.py::is_ignored`, `config.py::DEFAULT_CONFIG`;
  `desktop/src-tauri/src/ignore_store.rs`, `desktop/src/panes/IgnoredAppsPane.tsx`.

## D-048 — Application IDs are 17–21 digits, in the check *and* the copy
- **Date:** 2026-10-18 · **Status:** Accepted (closes `B-12`)
- **Context:** `config.validate_app_id` accepts 17–21 digits but its error string says "17–20".
  Discord's snowflakes are 17–20 today and will roll to 21 when the epoch advances.
- **Decision:** **17–21 in both places.** The frontend `validateAppId`, the copy, and
  `config_file::is_valid_app_id` in the shell all use 17–21. No behaviour change; the old string
  was the defect.
- **Consequences:** The check and its explanation can no longer disagree. `B-12` is closed for the
  new UI; the Python string is left alone until the engine is next touched, since changing it
  would alter shipped user-facing text for no functional gain.
- **Evidence:** `desktop/src/lib/validation.ts`, `desktop/src-tauri/src/config_file.rs`.

## D-049 — Window identity is an HTML entry point, not a hash route
- **Date:** 2026-10-18 · **Status:** Accepted (supersedes the `#fragment` routing sketched for `A21`)
- **Context:** `WebviewUrl::App` takes a path; a `#fragment` in it can be percent-encoded as
  `%23` by the time the webview resolves it, which would silently send every aux window to the
  Settings route.
- **Decision:** Three entry points — `index.html`, `onboarding.html`, `rename.html` — each mounting
  the same bundle with a route prop (`vite.build.rollupOptions.input`). The Rust shell creates the
  window with the entry it wants. **No `@tauri-apps/api` import exists anywhere in `src/`**, and
  no plugin JS API is exposed to the webview: the capability set is `core:default` only.
- **Consequences:** Routing cannot break through URL encoding, and the frontend keeps running in a
  plain browser against the mock backend. Three HTML files is a trivial cost.
- **Evidence:** `desktop/vite.config.ts`, `desktop/src/mount.tsx`, `desktop/src/entries/*`,
  `desktop/src-tauri/capabilities/default.json`.

## D-050 — The shell ships a mock engine by default, and never auto-spawns the Qt app
- **Date:** 2026-10-18 · **Status:** Accepted (Phase-1 scope)
- **Context:** `main.py` has no engine mode. Launching it starts the **old Qt app** — its own tray
  icon, its own single-instance mutex, its own presence loop — which on a dev machine means two
  tray icons fighting over one Discord connection.
- **Decision:** `AUTORPC_ENGINE=mock` is the default and drives the UI with cycled demo apps and
  synthetic log lines. `AUTORPC_ENGINE=python` reports `offline` and logs why. `T-022` adds
  `--engine-stdio` to `main.py`, after which the switch becomes real.
- **Consequences:** The UI is fully explorable today, and nothing can accidentally start a second
  presence loop. The mock is honest about two things: it says in the log that it sends nothing to
  Discord, and it probes Discord's IPC pipe for real, so the Status pane cannot show a green
  "connected" pill while Discord is closed.
- **Evidence:** `desktop/src-tauri/src/engine.rs`, `desktop/src-tauri/src/discord.rs`.

## D-051 — Phase-1 deferrals, each with the task that closes it
- **Date:** 2026-10-18 · **Status:** Accepted (owner visibility)
- **Context:** Some `MUST` items in the handoff depend on services the shell does not have yet.
  Shipping a stub that pretends to work would be worse than shipping a smaller, finished slice.
- **Decision:** Everything below is deliberately **not** implemented, and each is visible in the UI
  as an empty state or an absent control rather than as fake data:
  | Deferred | Reason | Closed by |
  |---|---|---|
  | Native save dialog for Export / Export logs | avoids a fourth plugin before the engine seam is real; exports go to `<data dir>\exports\` and the toast names the full path | `T-024` |
  | Tray "update available" item (`TR-4`) | needs a real update check; the version header is present, the item appears only when there is something to say | `T-024` |
  | Built-in tagline list (`T-6`) | the table lives in `detector.py::_BUILTIN_TAGLINES`; copying 58 strings into Rust would create a second source of truth | `T-022` |
  | SteamGridDB "Test key" (`G-11`) | needs an HTTP call, which belongs on the engine side | `T-022` |
  | Icon extraction / upload fallback (`G-10`) | GDI + uploads stay in the engine | `T-022` |
  | Presence itself (everything in `SS-*` that reads Discord) | the engine owns the IPC connection | `T-022` |
- **Consequences:** Phase 1 is honest but incomplete, and the gaps are enumerable. `G5` cannot be
  signed until `T-022` lands.
- **Evidence:** `desktop/COMPONENT_MAP.md` (`P2` markers), `TASKS.md` `T-022`/`T-024`.

## D-052 — The paused tray icon is generated, not shipped as a second asset
- **Date:** 2026-10-18 · **Status:** Accepted (`TR-2`)
- **Context:** `TR-2` wants the tray icon to change when broadcasting is paused. Two `.ico`
  assets must be kept in step by hand, and a stale copy is invisible until someone pauses.
- **Decision:** Derive it at runtime: take the app icon, desaturate to luma and drop alpha to 70%,
  and swap it in on a **state change** (never per poll). `TrayIcons` holds both images.
- **Consequences:** No asset can drift. The icon is legible on light and dark taskbars by
  construction, since it is the same silhouette in grey. A hand-drawn pause icon would still be
  nicer; that is a polish item, not a correctness one.
- **Evidence:** `desktop/src-tauri/src/tray.rs::desaturate`.

## D-053 — `config.json` defaults are duplicated in Rust for Phase 1 (`T-025` removes it)
- **Date:** 2026-10-18 · **Status:** Accepted (known debt, tracked)
- **Context:** The shell must show *effective* settings even when `config.json` is missing or was
  written by an older build. The authoritative table is `config.py::DEFAULT_CONFIG`.
- **Decision:** Mirror it in `config_file.rs::DEFAULT_CONFIG_JSON` with a comment saying so, plus a
  shallow merge that matches `load_config()` exactly. `T-025` moves the table onto the engine
  protocol so the shell stops carrying a copy.
- **Consequences:** Three places now describe the defaults (`config.py`, `config.example.json`,
  and this constant) and they must agree — the existing "adding a key = 4 edits" rule in
  `AGENTS.md` becomes 5 until `T-025` lands. Accepted because the alternative (a shell that
  guesses, or lies about `mask_private_browsing` being off) is worse.
- **Evidence:** `desktop/src-tauri/src/config_file.rs`, `AGENTS.md` §6, `config.py`.

## D-054 — Closing the Settings window hides it; only the tray's Quit exits
- **Date:** 2026-10-18 · **Status:** Accepted (fixes a documented-but-unimplemented behaviour, found by running the app)
- **Context:** The first `tauri dev` run **ended by itself** the moment the window was closed with the X — Tauri tears the app down as soon as its last window closes, taking the tray icon with it. `SH-9` and `TR-13` had been written as if closing Settings kept the app alive; the claim was aspirational. No compiler, test, or code read would have caught it: closing a window is not something you can assert from source.
- **Decision:** **Two guards, both required.** (1) `on_window_event` → `CloseRequested` on the `settings` label calls `api.prevent_close()` and then `hide()`, so the webview is kept warm and reopening from the tray is instant. (2) `RunEvent::ExitRequested` with `code.is_none()` calls `prevent_exit()`, which covers the case where a transient window (`rename`, `onboarding`) is the last one open while Settings is hidden. `app.exit(0)` from tray → Quit carries a code, so it passes straight through.
- **Consequences:** The X now behaves the way a tray app should, and "window closed, app still running in the tray" is a normal state rather than a crash. The guard is **label-scoped on purpose**: a future window must decide explicitly whether closing it hides or destroys. `TR-13` is again the only path to a full exit.
- **Evidence:** `desktop/src-tauri/src/main.rs` (`on_window_event`, `.build(..).run(..)`), `windows.rs::SETTINGS`, `tray.rs` (`"quit" => app.exit(0)`).

## D-055 — The windows are frameless, and the caption is stripped by hand (supersedes `A1`'s "native Windows frame")
- **Date:** 2026-10-18 · **Status:** Accepted (owner directive after the first hands-on review; verified at runtime)
- **Context:** `A1` asked for "the macOS System Settings interior in a **native** Windows frame". The owner ran the first build and rejected the frame itself: a Win32 caption — system font, its own dark theme, its own buttons — sitting directly on top of a macOS-styled toolbar reads as two applications stacked. There is no supported way to theme that caption to match `--bg-window`.
- **Decision:**
  - `decorations(false)` on all three windows, with the caption drawn by the frontend. **Settings keeps one bar, not two:** `StatusHeader` becomes the window's toolbar (drag region + `WindowControls`), because a separate strip would have cost 40 px of height in a window whose panes already scroll. `onboarding` and `rename` get `TitleBar` (app name, drag region, close only), and because their layouts are fixed, their window heights grew by the strip's 40 px rather than the content losing it.
  - Controls sit on the **right, in Windows order** (minimize, maximize/restore, close). A left-hand traffic light is a novelty on Windows and this app is Windows-only; the *styling* is the part the native caption could not give us. The fixed-size aux windows also get `maximizable(false)`/`minimizable(false)`, otherwise double-clicking their strip would maximize a 520 px dialog.
  - **`decorations(false)` alone does not remove the caption.** tao's `to_window_styles()` always starts from `WS_CAPTION | WS_CLIPSIBLINGS | WS_SYSMENU` and consults the decorations flag only for `AdjustWindowRectEx` and for child windows, so the flag changes the *sizing math*, not the frame. `windows.rs::strip_caption` clears `WS_CAPTION` with `SetWindowLongPtrW` + `SWP_FRAMECHANGED`, and it is re-applied everywhere tao can put the bits back: at creation, after **every** `show()` (visibility is a flag change), after our own minimize/maximize commands, and on **every** `Resized` event — which is what catches Tauri's injected double-click maximize and anything the window manager does on its own. `SWP_FRAMECHANGED` is skipped when the caption is already gone, so the `SetWindowPos` inside a `WM_SIZE` handler cannot recurse.
  - `tauri-plugin-window-state` now restores **size, position and maximized only**. Its other flags are traps here: the state file written by the previous build contained `"decorated": true` and `"visible": false`, either of which would resurrect the caption or fight the no-flash handshake.
  - Three commands (`minimize_window`, `toggle_maximize`, `close_window`) rather than JS plugin calls, so `client.ts` stays the only file that imports `@tauri-apps/api`. Dragging and double-click-to-maximize are Tauri's injected drag-region script, which costs exactly two permissions — `core:window:allow-start-dragging` and `core:window:allow-internal-toggle-maximize` — and is why the regions use `data-tauri-drag-region="deep"`: buttons inside them are ignored by that script.
- **Consequences / verified at runtime:** the window's style at startup is `0x140F0000` — no `WS_CAPTION`, **`WS_THICKFRAME` intact** — and `WM_NCHITTEST` at its edges returns `HTLEFT` / `HTRIGHT` / `HTTOP` / `HTBOTTOM` with `HTCLIENT` in the middle, so the OS still owns edge resizing and Aero Snap (`start_dragging` performs a real `WM_NCLBUTTONDOWN`). Maximizing through our own button gives `0x150F0000` (maximized, still no caption) and the glyph flips to restore. Corner rounding needed no code after all: DWM rounds the undecorated window by default, which closes the earlier "unverified" worry. **One deliberate loss:** hovering our maximize button does not open the Windows 11 snap-layout flyout — that needs an `HTMAXBUTTON` hit-test and is tracked as `T-026`.
- **Rejected:** traffic lights on the left (novelty, and their hover glyphs and colours would have to be hand-drawn to look right); `transparent(true)` + CSS `border-radius` for the corners (a real risk of black corners or a lost compositing path, and now unnecessary); frontend resize handles calling `start_resize_dragging` (nine elements to replace a border the OS still draws — the hit-test above proved they would have been dead weight).
- **Evidence:** `desktop/src-tauri/src/windows.rs` (`strip_caption`, the builder chain), `src-tauri/src/main.rs` (the `Resized` branch, window-state flags), `src-tauri/src/commands.rs`, `capabilities/default.json`, `src/shell/StatusHeader.tsx`, `src/shell/TitleBar.tsx`, `src/components/WindowControls.tsx`; screenshots and the style/hit-test results recorded under `T-023`.

## D-056 — Panes scroll because their boxes can shrink (`min-height: 0`), and the scrollbars are styled
- **Date:** 2026-10-18 · **Status:** Accepted (bug found by the owner in the first hands-on review)
- **Context:** With the window resized small, the bottom of every pane became unreachable and no scrollbar ever appeared. `.page` **already had** `overflow-y: auto`, which is exactly why this looked impossible when reading the CSS: the box never got the chance to overflow. `.page` is a flex item of `.main`, which is itself a grid item of `.app`, and both default to `min-height: auto` — "never shorter than my content". So the pane grew to fit its content, `.main` grew with it, and `body { overflow: hidden }` clipped the excess below the window. Nothing was scrolling because nothing was *overflowing*; the content was simply laid out past the bottom edge.
- **Decision:** `min-height: 0` on `.main` and `.page`, and the same treatment for `.onboard` and `.crash`, which have the identical shape inside `.window`. `scrollbar-gutter: stable` on each scroll container so a pane that grows a scrollbar does not shift its content sideways. The bars themselves are drawn rather than left to the platform: `::-webkit-scrollbar` (WebView2 is Chromium, so this is the only knob) renders a token-coloured pill — `--separator-strong`, `--text-secondary` on hover, a 3px transparent border with `background-clip: padding-box` so it floats inside the track instead of filling it.
- **Consequences:** Every pane is reachable at any window size, and the fix generalises — the same declaration protects any future scroll container in this layout, so the bug cannot come back in a new pane. Styling the scrollbars at all also switches WebView2 from overlay bars to classic ones, which is what makes the reserved gutter real rather than theoretical. Legibility in both themes came for free, because the colours are tokens and not literals.
- **Rejected:** hiding overflow per pane and giving each one an inner scroller (six copies of the same bug, and the tab order would still leave the viewport); a `<ScrollArea>` component (a component does not fix a layout minimum, and it would have hidden the real cause).
- **Evidence:** `desktop/src/styles/components.css` (`.main`, `.page`, `.onboard`, `.crash`), `desktop/src/styles/base.css` (the `::-webkit-scrollbar` block). Verified by driving the running window: at 1000×500 the General pane shows only down to "Start with Windows", and after three wheel notches the `Behaviour` rows below it are on screen — the rows that were previously unreachable.

## D-057 — The shell drives the real engine: `main.py --engine-stdio` over JSON lines (supersedes `D-050`'s "the mock is the only driver")
- **Date:** 2026-10-18 · **Status:** Accepted (implements `T-022`; verified end to end with a live Discord client)
- **Context:** Phase 1 shipped the whole interface against a mock driver on purpose (`D-050`): the alternative was a half-wired sidecar. The seam was frozen in advance — `desktop/src/ipc/types.ts` is the contract the UI already reads — and `engine.rs` documented `AUTORPC_ENGINE=python` as the switch it would become. Nothing in the shell had ever exercised detection, icon extraction, taglines or a real presence.
- **Decision:**
  - **The engine is a child process that speaks JSON lines over stdio**, started as `main.py --engine-stdio`. `engine_stdio.py` is the headless half: no Qt (the flag is handled *above* `main.py`'s Qt imports, so PyQt6 is never loaded), no tray, no windows, no single-instance mutex. It runs the same `detector` → `icons` → `presence` pipeline the tray build runs, adds a `logging` handler that mirrors every record to the shell, and treats EOF on stdin as quit.
  - **The Python side owns the truth.** It reports the Discord status (`PresenceManager.connected`, a new read-only property), the current app, the start epoch (`presence.start_epoch` — the same clock Discord was given, so the UI's ticking timer cannot drift from Discord's) and its built-in tagline table (`detector.built_in_taglines`, which closes `R-3`). It also answers the update check, which closes `R-4`'s *check*; the finding still has no UI surface.
  - **The shell owns `config.json`.** Every command that writes it (`set_config`, `reset_config`, `rename_app`, `remove_override`, `ignore_app`, `unignore_app`) follows the write with `reload_config`, so the engine re-reads immediately instead of waiting for its own file check, and `pause`/`resume` forward `set_paused` so the engine clears the presence and stops polling. The file stays the single source of truth between the halves; no settings travel over the protocol.
  - **Default is `auto`:** try the real engine, fall back to the mock with a log line that says why. `AUTORPC_ENGINE=mock` still forces the mock for interface review, and `AUTORPC_ENGINE=python` insists on the real engine and reports the failure rather than mocking it. Discovery order: `AUTORPC_ENGINE_PYTHON` (interpreter) + `AUTORPC_ENGINE_SCRIPT`, then a frozen `DiscordAutoRPC-engine.exe` next to the shell, then `python.exe` on `PATH` with `main.py` found by walking up from the dev binary (`main.py` **and** `detector.py` in the same folder).
  - **Shutdown is polite first:** `quit` on stdin, a 1.5 s grace, and only then `kill` — the engine needs the chance to clear the presence, or Discord keeps showing it until the socket drops. `RunEvent::ExitRequested` (a real exit, i.e. tray → Quit) is what asks for it; a crashed shell is covered from the other side by the EOF rule, which is the guarantee that matters most: **no stale presence can outlive the interface.**
  - `B-11` was fixed on the way, because the engine is now the thing that answers the update check: `updater.is_newer()` compares *parsed* versions (`0.1.0-beta` → `((0,1,0), 0, "beta")`), so a pre-release no longer "upgrades" to its own release and a downgrade is never offered.
  - `B-14` was found by the first live run and fixed: `check_for_updates()` called `/releases/latest`, which GitHub answers with **404 while every published release is a prerelease** — exactly this project's situation — so the check could never fire. It now lists `/releases?per_page=5` and takes the newest entry (verified: HTTP 200, `v0.1.0-beta`, and a correct "no update" for the running build).
- **Consequences:**
  - Detection, icons, taglines and presence are real: the smoke runs confirmed `Connected to Discord RPC`, `App confirmed: Notion (Notion.exe) | tagline: 'Document: Indian Theatre'`, an uploaded icon URL, the `app` event with that data, pause clearing the presence, and a clean `Presence cleared` + `RPC connection closed` + exit code 0 on quit.
  - **Two presence writers are possible** if the tray build is run at the same time — nothing enforces ownership, and the sidecar deliberately does *not* take the Qt build's mutex, because `ERROR_ALREADY_EXISTS` would make launching the old app silently do nothing. Documented as a known interaction while both exist.
  - The engine's own lines are written to `autorpc.log` by Python and only *mirrored* to the pane by `sidecar.rs`; shell lines go through `service::ui_log`. Neither half duplicates the other's file writes.
  - Engine death is reported once, with its exit code, plus a toast — and never auto-restarted, because a silent restart loop would hide the failure that caused it.
- **Rejected:** porting the pipeline to Rust now (that is `RUST_MIGRATION_RESEARCH.md`'s work, and it would have shipped a Windows-API rewrite in the same change as the engine seam); embedding CPython in the shell (one process and no protocol, but an engine crash would take the UI down with it); `pythonw.exe` for the sidecar (its stdout is only reliable when a pipe is attached, and stdout *is* the protocol — `python.exe` + `CREATE_NO_WINDOW` is deterministic and shows no console window); auto-restart on crash; taking the tray build's mutex; and reading the protocol with `sys.stdin` in the reader thread, which aborts CPython at shutdown with `_enter_buffered_busy` when the daemon thread still holds the buffered reader's lock — raw `os.read` holds no Python lock, so the process can exit under the thread.
- **Evidence:** `engine_stdio.py` (new), `main.py` (the `--engine-stdio` guard, `detector.is_discord_running` replacing the local copy), `detector.py` (`is_discord_running`, `built_in_taglines`), `presence.py` (`connected`, `start_epoch`), `updater.py` (`_version_key`, `is_newer`, the `/releases` endpoint for `B-14`); `desktop/src-tauri/src/sidecar.rs` (new: discovery, spawn, protocol, built-ins cache, shutdown), `engine.rs` (driver dispatch), `commands.rs` (the `reload_config`/`set_paused` forwards, `get_built_ins` from the cache), `main.rs` (`ExitRequested` → `sidecar::shutdown`), `state.rs` (`DISCORD_CONNECTING` is now accepted from the engine). Smoke driver kept at `C:\Users\Yash Thakor\AppData\Local\Temp\opencode\engine-smoke.py`.

## D-058 — Icon resolution is a bounded, reported ladder, and the cache clears per app (`T-030`)
- **Date:** 2026-10-18 · **Status:** Accepted (owner-reviewed; implements `ICON_RELIABILITY_RESEARCH.md` S1–S3)
- **Context:** `get_icon_url` ran on every poll, so an app whose icon could not be resolved was
  re-extracted and re-uploaded every `poll_interval` (5 s) forever — no attempt count, no backoff,
  no negative cache — and the only visible log line named neither the stage nor the cause. The
  retained log shows the cost: 117 WhatsApp fallbacks (114 in one day) for an MSIX exe that has no
  icon resource at all, and 68 Antigravity fallbacks inside one 13-minute window that no log line
  explains. The only user remedy was a global wipe (`Logs → Reset icon cache`, and `gui.py`'s
  button) — no way to say "this app's icon is wrong, fetch it again".
- **Decision (the five gating questions answered in the doc's §7):**
  - **A three-attempt ladder, then a park** (`icons.py`): attempt 1 is immediate; attempts 2–3 land
    on later polls with 1 s / 3 s minimum gaps (so a `poll_interval` of 1 s cannot hammer); after a
    full sequence fails the app parks for **60 s → 5 min → 30 min**, growing per consecutive failed
    sequence. A **hard** failure (nothing to extract) parks for 30 min immediately — retrying cannot
    produce a resource that is not there. While parked or waiting, `get_icon_url` returns the
    default and does no GDI or network work.
  - **Only the last stage is retried.** Override → cache → SteamGridDB → extract+upload is
    unchanged; the ladder counts the extract+upload stage. Each failed attempt logs at WARNING with
    the stage, host(s) and error; the park logs once at INFO
    (`Using default icon for <app> — <reason>; parked for … (trying again at HH:MM:SS)`). Parked
    ticks are silent — a DEBUG line per tick would have repeated the disease in the file log, which
    writes DEBUG.
  - **An override still wins while parked** (checked before the ladder gate), so the documented
    WhatsApp workaround — an `icon_url` override — applies immediately.
  - **Per-app clearing:** `icons.clear_icon_cache(exe_paths)` removes exactly those entries and
    resets their ladders so the next poll fetches again; `cached_icons()` feeds the list. The
    protocol pair `clear_icon_cache` / `get_icon_cache` plus the `icon_cache` event connect the
    shell; `commands.rs` forwards to the engine while it is connected — one writer per file — and
    falls back to a direct atomic file edit when it is not. UI: **Refresh icon** in the Status card
    and an **Icon cache** section in App Names (per-row Clear + Clear all), with the per-window icon
    memo invalidated after a clear.
  - **The failure state is visible:** the `app` event carries
    `icon: {state: ok|pending|parked, attempts, retryAtMs, reason}` and the Status pane's Details
    card renders it (`Resolved`, `Default — retrying (n of 3)`, `Default until HH:MM`).
  - **Scope is `desktop/`.** No per-app UI in `gui.py` (maintenance only, per `AGENTS.md`); the Qt
    build still gets the engine-side improvements because it shares `icons.py`, and its global reset
    keeps working because `clear_icon_cache()` stayed call-compatible.
  - **Smaller fixes from the same read:** `_save_cache` is atomic (temp + replace); a corrupt
    `icon_cache.json` warns and starts empty instead of taking the poll loop down; upload failures
    name the host and the error (previously swallowed at DEBUG); an untrusted override URL's
    validation verdict is memoized (successes for the session, failures for 30 min) so it is probed
    once instead of once per poll; and `presence.start_epoch` is stamped **at detection**, before
    the icon work, so a slow or retrying fetch cannot shift the timer Discord counts from.
- **Consequences:** A stuck app costs three attempts per park rung instead of an extract+upload
  every 5 s; the log names the failing stage once per attempt; "the icon is wrong" has a per-app
  remedy in the shell. `icon_cache.json` keeps its `{exe: url}` string format — turning the values
  into objects would crash older builds (`urlparse(dict)` on `icons.py`).
- **Rejected:** a forced presence update to push a refreshed icon immediately (it would bypass the
  15 s rate limit and the dedupe contract, `D-006`); revalidating *trusted-host* cached URLs every
  tick (dead-URL self-healing — tradeoff `T7` — stays measurement-gated; the per-app clear is the
  manual remedy, and `S4` remains the automated one); retrying harder for packaged/MSIX exes —
  WhatsApp's exe genuinely has no icon resource, so the Explorer-route extraction (`S5`/`E1`) stays
  gated on the `T9` probe.
- **Evidence:** `icons.py` (ladder, `clear_icon_cache`, `cached_icons`, `icon_state`, atomic write,
  memoized validation), `engine_stdio.py` (protocol pair, `icon_cache` event, `AppInfo.icon`, the
  detection-time stamp and the docstring's protocol table), `main.py` (the same stamp),
  `desktop/src-tauri/src/{state,sidecar,service,commands}.rs`,
  `desktop/src/{ipc/types.ts,ipc/mock.ts,lib/icons.ts,state/engine.ts}`,
  `desktop/src/panes/{StatusPane,AppNamesPane,LogsPane}.tsx`; `ICON_RELIABILITY_RESEARCH.md` §7.
  Verified: 22 ladder checks (`%TEMP%\opencode\icon-ladder-test.py`), 9 protocol checks
  (`engine-proto-test.py`), the 9-case `cargo test` suite, `cargo check` and `npm run build`.
  Landed as `bd2543e`.
