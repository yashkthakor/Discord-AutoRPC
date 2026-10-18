# AGENTS.md — Operating Manual for AI Agents

> **Audience:** any AI coding agent (or human) starting a fresh session on this repo.
> **Read order:** `AGENTS.md` (this file) → `STATE.md` → `TASKS.md` → `DECISIONS.md`.
> **Never** start implementing before reading `STATE.md` and `TASKS.md`.
> **Always** update `STATE.md`, `TASKS.md`, and `DECISIONS.md` before ending a session.

---

## 1. What this project is

**Discord AutoRPC** — a Windows-only background utility that watches the foreground
window and broadcasts the active app/game to Discord as a Rich Presence, including
extracted 256×256 icons, a contextual "tagline" second line, and a smooth ticking
timer. MIT licensed. Currently `0.1.0-beta` (open beta).

Repo: `https://github.com/yashkthakor/Discord-AutoRPC` · Default branch: `main`

The GUI is being rewritten as a **Tauri 2 + React desktop shell** under `desktop/`
(`GUI_HANDOFF_TAURI_REACT.md` is the spec). `gui.py` (PyQt6) is **maintenance only** — new UI work
belongs in `desktop/`. The detection/icon/presence engine stays Python and is shared by both: the
shell spawns it as a sidecar through `engine_stdio.py` (`D-057`).

---

## 2. Ground rules

1. **Windows-only.** Do not attempt to make this cross-platform. It depends on
   `win32gui`, `win32process`, `win32api`, `win32event`, GDI, and the Windows Shell
   icon API by design.
2. **Keep the UI thread clean.** All Qt objects (`QSystemTrayIcon`, `QMenu`, dialogs)
   live on the **main thread**. The polling loop runs on a **daemon thread** and may
   only touch Qt through the `TrayBridge` signals in `main.py`. Violating this is what
   caused the historical "tray icon invisible in the compiled exe" bug (see D-004).
3. **Never re-send an identical presence.** `PresenceManager` dedupes on
   `exe_path|pid|icon_url|display_name|tagline`. Re-sending every poll cycle resets
   Discord's client-side timer and makes it jump every 15s instead of ticking each
   second. This is a correctness requirement, not an optimization (see D-006).
4. **Respect the 15s RPC rate limit.** All updates funnel through
   `PresenceManager.RATE_LIMIT_SECONDS`.
5. **Privacy is a feature.** Incognito/private browser windows must never be
   broadcast (`mask_private_browsing`). Do not weaken `is_incognito()` or the
   `mask_private_browsing` gate without an explicit decision entry.
6. **Prefer minimal, surgical diffs.** Match the existing style: module docstrings,
   `logger = logging.getLogger("autorpc.<module>")`, type hints, `from __future__`-free
   (3.11+) syntax.
7. **Never commit user data.** `config.json`, `icon_cache.json`, `ignore_list.json`,
   `autorpc.log*`, `build/`, `dist/`, `*.spec` are git-ignored. `config.example.json`
   is the committed template — keep it in sync with `DEFAULT_CONFIG` in `config.py`.
8. **`D:\yash\Discord AutoRPC` is the live dev working dir**, and it *is* the dev data
   dir (see §4), so stray `config.json`/logs here are expected, not repo content.

---

## 3. Architecture map

| File | Responsibility | Notes |
|---|---|---|
| `main.py` | Entry point (**tray build**). Logging setup, single-instance mutex, Qt app + tray menu, spawns the poll thread. Also routes `--engine-stdio` to `engine_stdio.py` *before* the Qt imports. | Qt event loop owns the main thread. |
| `engine_stdio.py` | Headless second entry point (`main.py --engine-stdio`): the same `detector` / `icons` / `presence` pipeline with no Qt, speaking JSON lines to the Tauri shell on stdin/stdout. | **stdout is the protocol** — never `print()` here. EOF on stdin = quit + clear the presence (`D-057`). |
| `config.py` | Config load/save/merge, `DEFAULT_CONFIG`, App ID validation, data-dir resolution, autostart shortcut management. | `load_config()` merges missing defaults. |
| `detector.py` | Foreground-window polling, debounce, ignore/whitelist/incognito rules, display-name resolution (PE version strings), tagline resolution, dynamic ignore list. | The "brain". |
| `context.py` | Pure functions that parse raw window titles into dynamic taglines (browser platform, Office file, IDE file/project, media). | Stateless; no RPC/Qt deps. |
| `icons.py` | Extract icon from exe (`PrivateExtractIconsW` → `ExtractIconEx` → MSIX package manifest assets for Store apps, `T-031`), optional SteamGridDB lookup, upload to freeimage/catbox with failover, URL validation, disk cache, and the bounded retry ladder + per-app cache clearing (`T-030`). | Network + GDI heavy; reads `…\WindowsApps\…` package files for Store apps. |
| `presence.py` | `PresenceManager`: connect/update/clear/close, rate limiting, dedupe, per-app start-time tracking. | Only module that talks to `pypresence`. |
| `gui.py` | PyQt6: onboarding wizard, quick-rename dialog, settings window (5 tabs), Discord-dark QSS theme, live log terminal via a logging handler. | **Maintenance only** — new UI work belongs in `desktop/`. `_ensure_qapp()` is the single QApplication factory. |
| `desktop/` | **The rewrite: Tauri 2 + React shell.** `src-tauri/src/*.rs` holds the tray, window ownership, atomic config/prefs writes, the unified ignore store, and `sidecar.rs` (spawns and drives `engine_stdio.py`). `src/` is the UI. | Spec: `GUI_HANDOFF_TAURI_REACT.md` · map: `desktop/COMPONENT_MAP.md`. Build: `npm run tauri dev` / `npm run build` in `desktop/`. |
| `updater.py` | `__version__` constant and GitHub Releases update check (async). | Source of truth for the version string. |
| `watcher.pyw` | **Legacy** console-less supervisor that launches `main.py` when Discord starts. Superseded by the `--startup` dormant mode in `main.py`. | See D-005 / T-008. Not built into the exe. |
| `DiscordAutoRPC.spec` | PyInstaller spec (windowed, onefile, bundles `assets/`). | **Untracked** (`.gitignore` has `*.spec`). CI does *not* use it — it passes equivalent CLI flags. |
| `config.example.json` | User-facing config template shipped in the release zip. | Must mirror `config.py::DEFAULT_CONFIG`. |
| `.github/workflows/build-release.yml` | CI: on `v*` tag, build exe + zip + GitHub Release (prerelease). | Python 3.12, `windows-latest`. |

### Data / runtime flow

```
Windows foreground window
        │ win32gui.GetForegroundWindow()
        ▼
detector.Detector.poll()  ── debounce / ignore / whitelist / incognito ──► AppInfo
        │                                              │
        │                                              └─► resolve_display_name()  (PE metadata, overrides)
        │                                              └─► resolve_tagline()       ──► context.extract_dynamic_tagline()
        ▼
icons.get_icon_url()   cache → override → SteamGridDB → extract+upload → default
        ▼
presence.PresenceManager.update()   rate-limit + dedupe → Discord IPC
```

Threading: `main.main()` (main thread) → `QApplication.exec()`.
`_poll_loop()` (daemon thread) → reads `state` dict → talks to Qt only via `TrayBridge`.
Config is hot-reloaded every 30s via `JsonReloader`.

### Single-instance / IPC

- Named mutex: `DiscordAutoRPC_SingleInstance_Mutex`
- Wake event: `DiscordAutoRPC_Wakeup_Event` — a second launch signals the running
  instance to show Settings instead of starting a duplicate.

---

## 4. Data directory resolution (`config.get_data_dir()`)

- **Dev (not frozen):** the repo root (`BASE_DIR`).
- **Frozen (`.exe`):**
  - If `portable.txt` **or** `config.json` sits next to the exe → that directory (portable mode).
  - Otherwise `%APPDATA%\DiscordAutoRPC\` (created on demand; an existing `config.json`
    next to the exe is copied in on first run).
- Files living there: `config.json`, `autorpc.log` (+3 rotated backups, 2 MB each),
  `icon_cache.json`, `ignore_list.json`.

> ⚠️ `detector.py` and `icons.py` capture `get_data_dir()` at **import time**. If you
> ever change data-dir logic, verify nothing caches it too early.

---

## 5. Commands

```powershell
# Run from source (dev)
pip install -r requirements.txt
python main.py

# Run console-less (what the watcher/autostart uses)
pythonw main.py --startup

# Build the standalone exe (mirrors CI)
pip install pyinstaller
python -m PyInstaller --noconsole --onefile --icon="assets/icon.ico" --name="DiscordAutoRPC" main.py
# or: pyinstaller DiscordAutoRPC.spec

# Release: bump version, commit, then tag
git tag v0.1.1 && git push origin v0.1.1

# Desktop shell (Tauri 2 + React) — spawns the Python engine as a sidecar
cd desktop
npm install
npm run tauri dev                      # real engine; falls back to the mock and says why
$env:AUTORPC_ENGINE = "mock"; npm run tauri dev   # review the UI without touching Discord
npm run build                          # tsc + vite, three entry points
cargo build                            # inside desktop/src-tauri (cargo check while it runs)
```

**There is no test suite, linter config, or type-check config.** (Tracked as T-002.)

---

## 6. Configuration keys

Canonical defaults live in `config.py::DEFAULT_CONFIG`. Current keys:

`application_id`, `poll_interval`, `debounce_seconds`, `idle_timeout_seconds`,
`default_icon_url`, `auto_close_with_discord`, `mask_private_browsing`,
`whitelist_only`, `whitelist`, `ignored_exes`, `taglines`, `overrides`,
`steamgriddb_api_key`, `upload_host` (`freeimage` | `catbox`), `enable_dynamic_taglines`.

`overrides[<exe>]` = `{ "name": str, "tagline"?: str, "icon_url"?: str }`.

**Adding a config key = 4 edits:** `DEFAULT_CONFIG`, `config.example.json`,
the Settings GUI (if user-facing), and `README.md` config reference.

---

## 7. Session protocol (do this every time)

### On start
1. Read `AGENTS.md`, `STATE.md`, `TASKS.md`, and skim `DECISIONS.md`.
2. Run `git log --oneline -10` and `git status` — `STATE.md` may be stale.
3. Pick work from `TASKS.md` (respect the priority ordering) unless the human directs otherwise.
4. Verify `STATE.md`'s "known broken" list still matches reality before trusting it.

### On finish
1. **`STATE.md`** — update version, current focus, last commits, what works / what's
   broken, files touched, and environment realities you discovered.
2. **`TASKS.md`** — check off finished items, add newly discovered ones, re-order by priority.
3. **`DECISIONS.md`** — append a new entry for **every** non-obvious decision
   (architecture, tradeoff, rejected alternative). Never rewrite history; supersede.
4. Do not edit `AGENTS.md` unless conventions/architecture themselves changed.

### Writing style for these files
- Terse, factual, dated, and specific (file paths + symbol names, not vibes).
- Never delete prior decisions or task history — mark them `SUPERSEDED` / `DONE`.
- If you were blocked, say exactly what blocked you so the next session doesn't repeat it.
