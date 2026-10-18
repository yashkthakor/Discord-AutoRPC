# STATE.md — Current Project Snapshot

> **Volatile file.** Overwrite freely. It answers: *"where are we right now?"*
> Last updated: **2026-10-18** · Updated by: **MSIX/Store app icons fetched from the package's manifest assets — the `T9` probe run and implemented (`T-031`, `D-059`)**
> Keep it short enough to read in 60 seconds.

---

## 1. Identity

| Field | Value |
|---|---|
| Project | Discord AutoRPC |
| Shipped version | `0.1.0-beta` (`updater.py::__version__`) — the Python/Qt build is still the shippable artifact; only additive changes this pass |
| Desktop shell version | `0.2.0` (`desktop/package.json`, `desktop/src-tauri/Cargo.toml`, `tauri.conf.json`) |
| Status | Python build: open beta, no test suite. **Rewrite: committed (`1795dce`), the real engine is wired and verified end to end (`2f07b9f`, `T-022`, `D-057`), the icon pipeline is bounded, reported and per-app clearable (`bd2543e`, `T-030`, `D-058`), and the Store-app icon failure measured in the log is now fixed — real icons from the package's manifest assets (`05b1bb5`, `T-031`, `D-059`). `G2` visual evidence (`T-023`) is all that is left before the gate.** |
| Branch | `main` |
| HEAD | `05b1bb5` — feat(icons): packaged (MSIX) app icons from package manifest assets (T-031) |
| Working tree | clean after the T-031 docs commit |
| Platform | Windows 10 / 11 x64 only |
| Python | 3.11+ (CI targets 3.12) · local 3.12.10 (Microsoft Store `python.exe`, on `PATH`) |
| Toolchain | Node 24.15.0 · npm 11.12.1 · rustc/cargo 1.96.1 · MSVC 17.14.37314.3 |
| Remote | `https://github.com/yashkthakor/Discord-AutoRPC.git` |

---

## 2. Current focus

**The shell now drives the real engine.** `desktop/` is committed, and `main.py --engine-stdio`
(`engine_stdio.py`) is spawned and supervised by `desktop/src-tauri/src/sidecar.rs` (`D-057`).
Detection, display names, taglines, icon extraction/upload and the Discord connection all come
from the Python pipeline the tray build uses. `AUTORPC_ENGINE=mock` still exists to review the UI
without touching Discord, and `AUTORPC_ENGINE=python` insists on the real engine instead of
falling back to the mock.

- **What is left before `G2`:** `T-023` — the visual pass. Screenshots of every pane in **light and
  dark** at 100/150/200%, the no-flash check in both themes, a live System-mode OS theme change,
  tray-icon legibility on light/dark taskbars, keyboard-only onboarding/Settings, and the three
  entry points in a **bundled** build — plus a by-eye check of the two new controls the icon work
  added (`T-030`): the Status card's **Refresh icon** button and the **Icon cache** section in
  App Names, and a WhatsApp focus (its icon now resolves through the package assets, `T-031`).
- **Next engineering task:** `T-028` (`P1`) — freeze the engine into `DiscordAutoRPC-engine.exe`
  and ship it beside the shell; without it an end user who installs the shell alone silently gets
  the mock.
- **Still-open owner questions:** **Q2** (is a WebView2 runtime dependency acceptable for end
  users — this machine has `155.0.4283.62`), **Q7** (tray single- vs double-click; today
  left-click opens Settings, `TR-14`), **Q8** (code-signing budget, `T-017`).
- **Just landed:** `T-031` / `D-059` (`05b1bb5`) — the `T9` probe measured every shell icon route
  (`SHGetFileInfoW` LARGE, `SHGetImageList` JUMBO, `IShellItemImageFactory::GetImage`) returning
  Windows' *generic placeholder* for Store-app stub exes, so `icons._extract_icon_image` gained a
  third approach that reads the real icon from the package's `AppxManifest.xml` assets
  (`targetsize-256`, unplated preferred). WhatsApp now caches a real 256×256 icon with **no
  override** — the measured dominant failure from `T-030` is gone. (Unchanged from `T-030`/`D-058`:
  the bounded retry ladder and the per-app cache controls.)
- **Also live:** `T-030` / `D-058` (`bd2543e`) — an app whose icon fails retries exactly three times
  (1 s / 3 s gaps), parks for 60 s → 5 min → 30 min (hard failures at once), logs *why* each attempt
  failed, and can be cleared per app from Settings (Status card **Refresh icon**, App Names
  **Icon cache**).
- **Run it:**
  - Dev shell: `cd desktop && npm run tauri dev` (spawns the engine; it finds `main.py` by walking
    up from the dev binary).
  - Mock shell: `$env:AUTORPC_ENGINE="mock"; npm run tauri dev`.
  - Engine alone: `python main.py --engine-stdio` (type JSON lines; EOF quits). Smoke harness:
    `%TEMP%\opencode\engine-smoke.py`.
  - Icon harnesses (they fake extraction/upload or build a temp package tree; the real cache and
    Discord are never touched): `%TEMP%\opencode\icon-ladder-test.py`, `engine-proto-test.py`
    (`T-030`), `msix-icon-test.py` (`T-031`, ends with the real WhatsApp package when installed).
  - `T9` probe (read-only, one PNG per route): `%TEMP%\opencode\t9-probe.py` → `t9-out\`.
  - Builds: `npm run build` in `desktop/`, `cargo build` in `desktop/src-tauri/`.

---

## 3. Recent history (most recent first)

| Commit | Date | Summary |
|---|---|---|
| `05b1bb5` | 2026-10-18 | **Store-app icons (`T-031`, `D-059`).** The `T9` probe: `PrivateExtractIconsW`/`ExtractIconEx` and every shell/COM route fail or return the generic placeholder for `WhatsApp.Root.exe`; the package's manifest assets hold the real 256×256 icon. `icons._extract_icon_image` gained approach 3: scope `\WindowsApps\`, walk up to the package root, parse `AppxManifest.xml` (bounded cache), match by exe basename, prefer `targetsize-256` unplated with corrupt/non-square fallthrough; `ExtractIconEx` gained a local catch. Verified: 17 new checks + the real WhatsApp package + the 22 ladder and 9 protocol checks re-run. |
| `bd2543e` | 2026-10-18 | **Icon reliability (`T-030`, `D-058`).** A 3-attempt ladder with an escalating park in `icons.py` (hard failures park for 30 min), stage/host/error logging, atomic cache writes, a memoized URL-validation verdict, a detection-time `start_epoch` stamp, the `clear_icon_cache`/`get_icon_cache` protocol pair plus an `icon_cache` event and `AppInfo.icon`, and the UI: Status-card **Refresh icon** + App Names **Icon cache** section + memo invalidation. Verified by 22 ladder checks + 9 protocol checks + the 9-case `cargo test` suite; both builds clean. |
| `f01cb02` | 2026-10-18 | Docs: the icon-reliability research and proposal (`ICON_RELIABILITY_RESEARCH.md`) + `T-030`/`T-013` bookkeeping. No code, by owner request. |
| `2f07b9f` | 2026-10-18 | **Engine seam (`T-022`, `D-057`).** `engine_stdio.py` + a `main.py --engine-stdio` guard above the Qt imports; `sidecar.rs` (spawn, JSON lines, built-ins cache, polite quit, EOF reaping); `engine.rs` dispatch `mock`/`python`/`auto`; `set_paused` + `reload_config` forwards through `service.rs` so the tray cannot bypass them; `ExitRequested` → `sidecar::shutdown`; `detector.is_discord_running`/`built_in_taglines`, `presence.connected`/`start_epoch`; `B-11` and `B-14` fixed in `updater.py`. Verified: a real presence on a live Discord client, a real icon upload, and a clean EOF shutdown. |
| `1795dce` | 2026-10-18 | **Rewrite Phase 1 committed** — the Tauri 2 shell + React/TS UI under `desktop/` (tray, six panes, onboarding, quick rename, design tokens, frozen IPC contract, mock engine), plus the spec and research docs. 80 files, 18.9k lines. Includes the owner-review fixes below. |
| *(in `1795dce`)* | 2026-10-18 | **Owner-review fixes:** frameless chrome in all three windows (`D-055`, `windows.rs::strip_caption` because tao keeps `WS_CAPTION`) and scrolling panes (`D-056`, `min-height: 0` + reserved scrollbar gutter). Verified by driving the window: no caption at startup or maximized, `HTLEFT`/`HTTOP`/… hit tests intact, wheel scrolling reaches previously unreachable rows. |
| `6f34a75` | 2026-10-12 | Persist App ID across launches; auto-sync lifecycle with Discord (dormant/hidden tray when Discord is closed). |
| `e4b51f1` | 2026-10-12 | Migrate to native `QSystemTrayIcon` on the main thread — fixed tray invisibility in the compiled exe. |
| `a32af3c` | 2026-10-12 | Smart PE app-name cleanup, 1-click tray rename, App Overrides manager. |
| `97083b0` | 2026-10-12 | Smart Win32 window-title dynamic semantic extraction (`context.py`). |
| `a9e305d` | 2026-10-12 | GUI migrated to PyQt6 with real-time log terminal; FreeImage CDN failover. |
| `ea3a532` | 2026-10-12 | Initial release v0.1.0-beta (pystray-based). |

---

## 4. What works

### Python / Qt build (still shippable; additive changes only this pass)

- Foreground detection + debounce + idle timeout (`detector.Detector.poll`).
- Ignore list (config + runtime `ignore_list.json`), whitelist-only mode, `C:\Windows` auto-skip.
- Incognito/private browsing masking for 8 browsers (`detector.is_incognito`).
- Display-name resolution from PE `ProductName` / `FileDescription` with category-suffix stripping.
- Dynamic taglines: browsers, Office, Notion/Obsidian, IDEs, media players.
- Icon pipeline: `PrivateExtractIconsW` (256×256) → `ExtractIconEx` → **MSIX package manifest assets**
  for Store apps whose exe has no icon resource (`T-031`, `D-059`) → freeimage/catbox upload with
  failover → `icon_cache.json`, with a bounded retry ladder (3 attempts with 1 s / 3 s gaps, then a
  60 s → 5 min → 30 min park; hard failures park for 30 min) and per-app cache clearing
  (`T-030`, `D-058`).
- Discord RPC with 15 s rate limit, dedupe, per-app start-time timer, auto-reconnect.
- PyQt6 tray menu, 5-tab Settings window, onboarding wizard, single-instance mutex + wake event.

### Engine seam (`engine_stdio.py` ↔ `sidecar.rs`) — verified end to end

- **Ready handshake:** `ready` (version + pid) and the 58-string `builtins` table arrive within a
  second of spawn; the shell logs `Python engine ready (v0.1.0-beta, pid …)`.
- **Real detection:** the focused app shows up after the configured debounce (~10 s), with the real
  exe path, PID, PE display name, dynamic tagline (e.g. `Document: Indian Theatre` for Notion) and
  an uploaded icon URL. The Status pane's timer ticks from `presence.start_epoch` — the same clock
  Discord was given, so it cannot drift.
- **Pause/resume** reach the engine (`Paused from the shell` / `Resumed from the shell`) and clear
  the presence. **Every config write** (Settings, rename, ignore, reset) is followed by
  `reload_config`, and the engine also watches `config.json`'s mtime as a second net.
- **Quit:** the tray's Quit sends `quit`; the engine answers with `Presence cleared` +
  `RPC connection closed` and exits 0. If the shell dies first, the pipe's EOF does the same thing
  (`The shell closed the protocol pipe — stopping the engine`).
- **Crash reporting:** an engine that dies is reported once (exit code + a toast), the state flips
  to `offline`, and nothing auto-restarts it — the reason is never hidden.

### Rewrite — `desktop/` (run many times in `tauri dev`; owner-reviewed by eye)

- **Shell:** Tauri 2 single instance, window-state persistence (geometry only), tray with a native
  menu, left-click → Settings, tooltip + labels following engine state, runtime-generated grey
  pause icon (`D-052`).
- **No-flash boot:** windows are created hidden and shown by the frontend's `ready` call after the
  theme is applied to frame *and* webview background (`D-046`).
- **Three entry points** (`index.html`, `onboarding.html`, `rename.html`); no `@tauri-apps/api`
  import anywhere in `src/`.
- **Config writes are atomic** (temp + rename) with unknown keys preserved — `B-10`'s fix, applied
  to every file the shell writes. **Prefs:** `ui_prefs.json` (appearance only).
- **Ignore:** one store — `config.ignored_exes` — written by the tray *and* the pane, with
  `ignore_list.json` folded in on startup (`D-047`).
- **Logs:** ring buffer + rAF batching, level filter, search with `<mark>`, follow-the-tail, copy,
  export, open folder, reset icon cache, and a 200-line seed from `autorpc.log`. The engine's lines
  arrive as `log` events and are only *mirrored* to the pane — the engine writes them to the file
  itself, so nothing is duplicated on disk.
- **Real (not mocked) shell features:** Discord IPC probe for Test connection, autostart read/write
  with read-back, atomic config/prefs writes, icon-URL resolution, log seeding/export, clipboard.
- **Icon cache management (`T-030`):** the Status pane's Details card reports the ladder's state
  (`Resolved` / `Default — retrying (n of 3)` / `Default until HH:MM` with the failure reason), and
  its **Refresh icon** button clears that app's entry. App Names carries an **Icon cache** section —
  every cached icon with a per-row Clear and a Clear all. Clears route through the engine while it
  runs (one writer per file, direct atomic file edit otherwise), and the per-window icon memo is
  invalidated so a refresh shows without reloading.
- **Frameless chrome** (`D-055`): all three windows draw their own caption; the Win32 caption is
  stripped and re-stripped after every show/maximize/minimize/resize. **Every pane scrolls**
  (`D-056`).

---

## 5. Known broken / rough edges (verify before trusting)

| # | Issue | Location | Severity |
|---|---|---|---|
| **R-1** | **`G2` visual evidence is still missing:** light-theme screenshots of every pane, the no-flash check in both themes, a live System-mode OS theme change, tray legibility on light/dark taskbars, 100/150/200% scaling, keyboard-only flows, and the three entry points in a **bundled** build. Add a by-eye pass of `T-030`'s two new controls (Status card **Refresh icon**, App Names **Icon cache** section) and of a WhatsApp focus (its icon now resolves through the package assets, `T-031`). This is `T-023`. | `desktop/` | Blocker for `G2` |
| **R-4** | **The update *finding* has no UI surface.** The engine performs a real check and the shell stores it in `state.updateTag`, but nothing shows it yet (no tray item, no banner) — `T-024`. | `commands.rs`, `tray.rs` | Known `P2` |
| **R-5** | **`config.json` defaults are mirrored in Rust** (`config_file.rs::DEFAULT_CONFIG_JSON`) next to `config.py::DEFAULT_CONFIG` and `config.example.json` — "adding a config key" is 5 edits until `T-025`. | `config_file.rs` | Known debt (`D-053`) |
| **R-6** | Exports write to `<data dir>\exports\` instead of a native save dialog (`T-024`); the SteamGridDB "Test key" (`G-11`) and `restart_engine` are still unbuilt (`T-029`). | `commands.rs` | Known `P2` |
| **R-7** | **No frozen engine ships with the shell.** `sidecar.rs` finds `python.exe` on `PATH` (dev machine) or `DiscordAutoRPC-engine.exe` beside the exe (not built yet), so an installed release build falls back to the mock — `T-028`. | `sidecar.rs`, CI | Blocker for shipping |
| **R-8** | **Two presence writers are possible:** if the Qt build and the shell run at once, both broadcast. The sidecar deliberately does *not* take the Qt build's single-instance mutex (that would make launching the old app silently do nothing) — ownership is undecided (`D-057`). | `main.py`, `sidecar.rs` | Known interaction |
| B-1 | **Two competing autostart mechanisms** (`config.set_autostart_enabled()` → `main.py --startup`; `enable_autostart.bat` → `watcher.pyw`). Both count as enabled. | `config.py`, `watcher.pyw`, `*.bat` | High (Python build) |
| B-2 | `watcher.pyw` is **not bundled** into the built exe, yet the README/bat files still reference the watcher workflow. | `watcher.pyw`, `enable_autostart.bat` | Medium |
| B-3 | Version string is duplicated: `updater.py::__version__` vs README badges vs the release tag. | `updater.py`, `README.md` | Medium |
| ~~B-4~~ | **FIXED (`T-030`):** the `icons.py` docstring no longer names a default upload host; it names the configured one plus failover. The key constant and the README note remain as `T-005`. | `icons.py` | Resolved |
| B-5 | `freeimage.host` API key is hardcoded in source. | `icons.py` | Low |
| B-6 | Built-in tagline table is duplicated (`detector._BUILTIN_TAGLINES` vs `DEFAULT_CONFIG["taglines"]`). | `detector.py`, `config.py` | Low |
| B-7 | No tests, no linter, no type checking, no CI test job **for the Python build** (the shell has `tsc` + `cargo build`, plus five `cargo test` cases covering protocol parsing since `D-057`). | repo-wide | Medium |
| B-8 | `main.py` imports `CONFIG_PATH` then reassigns it; `BASE_DIR` unused. | `main.py`, `context.py` | Trivial |
| B-9 | `autorpc.log` rotates at 2 MB × 3; the dev-dir log accumulates. | `main.py`, `engine_stdio.py` | Info |
| B-10 | **`config.save_config()` writes non-atomically.** A crash mid-write corrupts `config.json`. The shell already avoids this; the Python build still has it. | `config.py::save_config` | Medium |
| ~~B-11~~ | **FIXED (`D-057`):** `updater.is_newer()` compares parsed versions (`0.1.0-beta` → `((0,1,0), 0, "beta")`), so a prerelease no longer "upgrades" to its own release. | `updater.py` | Resolved |
| B-12 | App ID validation accepts 17–21 characters but the Python error string says "17–20"; the shell's copy says 17–21 (`D-048`). | `config.validate_app_id` | Low |
| ~~B-13~~ | **FIXED (`D-057`):** the headless mode exists (`engine_stdio.py`, `main.py --engine-stdio`), so the sidecar has something to spawn. | `main.py`, `engine_stdio.py` | Resolved |
| ~~B-14~~ | **FIXED (`D-057`):** the update check called `/releases/latest`, which 404s while every release is a prerelease; it now lists `/releases` (verified 200). | `updater.py` | Resolved |

---

## 6. Environment realities learned

- Dev working dir **is** the data dir when running unfrozen → `config.json`, `autorpc.log`,
  `icon_cache.json`, `ignore_list.json`, `ui_prefs.json`, `exports/` appear in the repo root and
  are git-ignored. Do not "clean them up".
- **The shell resolves the data dir the same way** (`paths.rs`): `AUTORPC_DATA_DIR` wins, a debug
  build uses the repo root, a release build uses the exe's folder when `portable.txt` /
  `config.json` sits beside it, else `%APPDATA%\DiscordAutoRPC`.
- **The engine's interpreter in dev** is the Microsoft Store `python.exe` on `PATH`
  (`…\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe`). `sidecar.rs`
  spawns `python.exe` with `CREATE_NO_WINDOW` — `pythonw.exe` was rejected because the protocol
  *is* stdout (`D-057`).
- **Never `print()` from `engine_stdio.py`** — stdout is the protocol. Logging goes through a
  `RotatingFileHandler` on `autorpc.log` (same format/rotation as the tray build) plus a handler
  that mirrors INFO+ records to the shell as `log` events; DEBUG stays in the file.
- **`sys.stdin` is unusable in the reader thread:** a daemon thread holding a `BufferedReader`
  lock at interpreter shutdown aborts CPython with `_enter_buffered_busy` (exit code `0xC0000005`).
  `engine_stdio.py` reads the raw fd with `os.read` instead (`D-057`).
- **Store-app packages are readable:** a `…\WindowsApps\…` package folder, its `AppxManifest.xml`
  and `Assets\*.png` all read fine as a normal user (verified 2026-10-18, `T9`) — the ACL note in
  the icon research doc was wrong on this machine. The path is version-stamped, which is a *cache
  advantage*: a detected exe path always carries the current package version.
- **Shell icon routes do not help Store stubs:** `SHGetFileInfoW` (LARGE and `SHGFI_SYSICONINDEX` +
  `SHGetImageList` JUMBO) and `IShellItemImageFactory::GetImage` answer with Windows' generic
  placeholder for exes like `WhatsApp.Root.exe`; only the package manifest has the real artwork.
- **`tauri dev` restarts the app on every Rust edit** — each restart kills the shell, so the engine
  sees EOF and exits. That is the expected path, not a bug; it is why the log shows repeated
  `Starting the engine` / `The shell closed the protocol pipe` pairs.
- **`cargo build` cannot relink while the dev app is running**; use `cargo check` (no link) or quit
  the app first.
- Invoking `cargo` from PowerShell prints a `NativeCommandError` wrapper on stderr even on success —
  PowerShell reacting to cargo's stderr, not a failure. Read the last lines.
- **TypeScript 6 removed `baseUrl`;** `tsconfig.json` must use relative `paths`.
- `tauri` needs the `image-png` + `image-ico` features for `Image::from_bytes`.
- **WebView2 is installed** here (`155.0.4283.62`, 64-bit view under `WOW6432Node`); `Q2` is about
  end users.
- The **frontend is testable in a plain browser** (`npm run dev` → `localhost:1420`) because
  `ipc/client.ts` falls back to the mock backend.
- **`decorations(false)` does not remove the native caption on Windows** — `windows.rs::strip_caption`
  removes it and re-strips after every show/maximize/minimize/resize (`D-055`); `SWP_FRAMECHANGED`
  must be conditional or the call recurses inside `WM_SIZE`.
- `tauri-plugin-window-state` stores `decorated`/`visible` too; the plugin is built with
  `SIZE | POSITION | MAXIMIZED` only, so a stale state file cannot resurrect the caption.
- The primary display here is **3440×1440 at 100%**, so physical and logical pixels agree.
- **GitHub's `/releases/latest` 404s for prerelease-only projects** (`B-14`) — any future update
  logic must use `/releases`.

---

## 7. Local uncommitted data (expected, git-ignored)

Python side: `config.json`, `icon_cache.json`, `ignore_list.json`, `autorpc.log`, `build/`,
`dist/`, `__pycache__/`.

Rewrite side: `desktop/node_modules/`, `desktop/dist/`, `desktop/src-tauri/target/`,
`desktop/src-tauri/gen/`, plus `ui_prefs.json` / `exports/` / `portable.txt` in the data dir.
The shell's window geometry lives in `%APPDATA%\com.yashkthakor.discordautorpc\.window-state.json`
(outside the repo).

---

## 8. Documentation set (committed with the seam)

| File | Role |
|---|---|
| `AGENTS.md` | Operating manual: ground rules, architecture map (now including `engine_stdio.py` and `desktop/`), data-dir rules, session protocol. **Read first.** |
| `STATE.md` | This snapshot. Volatile. |
| `TASKS.md` | Work queue. `T-023` (G2 evidence) and `T-028` (frozen engine) are the live ones. |
| `DECISIONS.md` | Append-only decision log. `D-001`…`D-019` = Python/engine era; `D-020`…`D-042` = G0; `D-043`…`D-053` = Phase 1; `D-054`…`D-056` = owner-review fixes; `D-057` = the engine seam (supersedes `D-050`'s mock default); `D-058` = the icon retry ladder + per-app cache clearing; `D-059` = Store-app icons from the package manifest assets (`T-031`). Next free id `D-060`. |
| `GUI_HANDOFF_TAURI_REACT.md` | The rewrite spec: §4 parity inventory (stable IDs), §11 gates, §13 open questions. **§0.1 is authoritative.** |
| `desktop/COMPONENT_MAP.md` | §4 ID → component mapping, `P1`/`P2` markers, deferral table. Kept in step with the code. |
| `ICON_RELIABILITY_RESEARCH.md` | **Accepted and implemented (`T-030`, `D-058`), plus the `T9` probe result (`T-031`, `D-059`):** why an icon falls back to the default, the retry ladder as built, per-app cache clearing, the route-by-route probe table (shell routes → placeholder; manifest assets → the real icon), and the measurement plan for the tradeoffs. §7 records the owner's answers; `S4` stays gated. |
| `RUST_MIGRATION_RESEARCH.md` | Deprioritized: the full-Rust-rewrite research. Reference only. |

> The Python engine's public surface grew by four additive helpers (`detector.is_discord_running`,
> `detector.built_in_taglines`, `presence.connected`, `presence.start_epoch`) plus the
> `--engine-stdio` guard and two `updater.py` fixes. The Qt build's behaviour is unchanged, except
> that its update check now actually fires.
