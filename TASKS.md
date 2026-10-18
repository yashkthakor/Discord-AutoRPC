# TASKS.md — Work Queue

> **Purpose:** the single source of truth for what to do next. Update at the end of
> every session (check off, add, re-prioritize).
>
> **Status legend:** `TODO` · `IN PROGRESS` · `BLOCKED` · `DONE` · `WONTFIX`
> **Priority:** `P0` critical / `P1` high / `P2` medium / `P3` low / `P4` nice-to-have
>
> Rules: keep task ids stable once assigned, prefix each with its priority, and always
> state concrete **files** + **acceptance criteria** so the next agent can execute
> without re-deriving context. When you finish a task, move it to **§ Done** with the
> commit hash — do not delete it.

---

## § GUI rewrite (Tauri + React) — active workstream

> **Spec:** `GUI_HANDOFF_TAURI_REACT.md`. **§0.1 of that doc is authoritative** for the G0
> decisions; their rationale lives in `DECISIONS.md` `D-020`…`D-042`. **The Python/Qt build is
> in maintenance only** — do not add features to `gui.py`.
> **Ritual (from §11 of the handoff):** before writing code for any section, post the mapping
> from the §4 requirement IDs it covers to the components that implement it. If an ID has no
> home, stop and ask.
>
> **Phase 1 status (2026-10-18):** the shell, all six Settings panes, onboarding, quick rename,
> the tray, the design layer and the IPC contract are implemented under `desktop/`, and both
> builds are green — `npm run build` (tsc + vite, three entry points) and `cargo build`
> (Tauri 2, zero warnings). **The real engine is wired** (`T-022`, `D-057`): the shell spawns
> `main.py --engine-stdio` and drives detection, icons, taglines and the Discord connection from
> the Python pipeline, falling back to the mock only when no engine can be started. `G2` visual
> evidence (`T-023`) is what remains before the gate can be signed.

### T-018 — Obtain the G1 entry answers (Q4, Q5) — `P0` — `DONE` (2026-10-18)
- **Answers:** **Q4** → "Continue without connecting" (`D-044`). **Q5** → the Advanced group is
  **visible** in General (`D-045`, confirming `D-035`). Both recorded in the handoff §13.

### T-019 — Design the unified ignore list (`I-5`, `RSK-6`) — `P0` — `DONE` (2026-10-18)
- **Answer:** `D-047` — **`config.ignored_exes` is the one store.** It already holds the shipped
  twelve and is what the Python Settings pane wrote. The startup migration unions
  `ignore_list.json` into it (idempotent, reversible, file left in place); uncopied entries show in
  an "Added elsewhere" group. `%SystemRoot%` is prose, not rows.
- **Implemented in:** `desktop/src-tauri/src/ignore_store.rs`, `desktop/src/panes/IgnoredAppsPane.tsx`.
- **Still to prove:** the §10 manual test (tray → Settings → Ignored Apps shows it) on a real
  build. Tracked as `T-023`.

### T-020 — Produce the G1 design package — `P0` — `IN PROGRESS` — *partly delivered by the implementation*
- **Delivered:** the both-theme token sheet lives in `desktop/src/styles/tokens.css` (light, a
  guarded `prefers-color-scheme` dark, and the explicit `[data-theme="dark"]` override — `D-026`),
  and the frozen IPC contract is `desktop/src/ipc/types.ts` (§6).
- **Outstanding:** wireframes / annotated screenshots for the six panes in both themes, and the
  §8.1 contrast table computed for the unmeasured pairs. Either produce them or record a decision
  that the running implementation *is* the design artifact and the screenshots in `T-023` suffice.
- **Acceptance:** the owner signs the package off, or signs off the substitution.

### T-021 — Settle the engine seam (Q1) and the WebView2 requirement (Q2) — `P0` — `DONE (Q1) / OPEN (Q2)`
- **Q1 answered → Option A** (`D-043`): Tauri shell + the existing Python engine as a sidecar over
  stdio JSON-lines. The failure model is sketched in `D-050`: the shell never spawns `main.py`
  until it has `--engine-stdio` (`T-022`), an engine that is absent or silent leaves the UI in an
  explicit `offline` state, and a restart resyncs because the shell owns `config.json` and the
  engine re-reads it.
- **Still open:** **Q2** (is a WebView2 runtime dependency acceptable, and what is the minimum
  version / fallback message — `RSK-5`), **Q7** (single- vs double-click on the tray — currently
  left-click opens Settings, `TR-14`), **Q8** (code-signing budget, `T-017`).

### T-022 — `main.py --engine-stdio` + wire the real sidecar — `P0` — `DONE` (2026-10-18)
- **Delivered (engine side):** `engine_stdio.py` and a `main.py` guard that handles `--engine-stdio`
  *before* the Qt imports, so the sidecar never loads PyQt6, never takes the tray build's
  single-instance mutex and never opens a window. JSON lines on stdin/stdout — commands
  `set_paused`, `reload_config`, `quit`; events `ready`, `builtins`, `discord`, `app`, `log`,
  `update`, `toast`, `fatal`. EOF on stdin is quit, so a crashed shell cannot leave a presence on
  somebody's Discord profile.
- **Delivered (shell side):** `sidecar.rs` (discovery: `AUTORPC_ENGINE_PYTHON` →
  `DiscordAutoRPC-engine.exe` → `python.exe` on `PATH`; spawn with `CREATE_NO_WINDOW`; stdout/stderr
  readers; a `builtins` cache; a polite `quit` with a 1.5 s grace before `kill`), `engine.rs`
  dispatch (`mock` | `python` | default `auto` → the real engine, mock as the fallback),
  `set_paused`/`reload_config` forwards in `service.rs` (so the tray cannot bypass them), and
  `main.rs`'s `ExitRequested` → `sidecar::shutdown`.
- **Delivered (small engine enablers):** `detector.is_discord_running()` (the copy in `main.py` is
  gone), `detector.built_in_taglines()` (closes `R-3`), `presence.connected`, and
  `presence.start_epoch()` — the *same* clock Discord was given, so the pane's ticking timer cannot
  drift from Discord's. `updater.py` gained `is_newer()` (`B-11`) and the `/releases` endpoint
  (`B-14`), so the check actually fires.
- **The frozen command table was not reproduced, on purpose.** The shell owns `config.json`, so the
  engine needs no `rename_app` / `ignore_app` / `get_built_ins` round trips: writes happen in Rust
  and the engine re-reads the file (mtime, or a `reload_config` nudge). One writer per file, one
  protocol for state. `started_at_ms` is epoch milliseconds as required — verified against
  Discord's own display.
- **Acceptance — verified end to end:** the smoke driver (`engine-smoke.py`) showed `ready` + 58
  built-ins, `connected`, real detection of the focused app with its real tagline and an uploaded
  icon, pause clearing the presence, and a clean `quit` (presence cleared, RPC closed, exit 0,
  nothing on stderr). In the shell itself the log shows the whole seam — `Starting the engine: …
  --engine-stdio`, `Python engine ready (v0.1.0-beta, pid …)`, real `autorpc.detector` /
  `autorpc.icons` / `autorpc.presence` lines — and the Status pane renders the real exe path, PID
  and detection time. Restarting the shell is handled by the EOF path, which logs `The shell closed
  the protocol pipe — stopping the engine` and clears the presence.
- **Not done, on purpose:** `restart_engine` / auto-restart (a silent restart loop would hide the
  failure that caused it); the tray's dormant state (`SH-6`, now `T-027`); a frozen engine exe for
  the release layout (`T-028`).

### T-023 — G2 evidence: run the real build and capture both themes — `P0` — `IN PROGRESS`
- **First dev run (2026-10-18):** `npm run tauri dev` compiled in ~29 s, created the window hidden
  and showed it after the frontend's `ready` call. Verified programmatically: window visible,
  996×739, process alive, **no ERROR/`autorpc.ui`/Traceback lines in `autorpc.log`** (a React crash
  would have been reported through the error boundary).
- **Also verified that run:** the ignore migration moved `ignore_list.json`'s `python3.12.exe` into
  `config.json` (12 → 13 entries, atomic rewrite, `ignore_list.json` untouched) and logged it as
  `autorpc.ignore - Moved 1 entry…`; the mock engine logged its "nothing is sent to Discord" line.
- **Second and third dev runs (2026-10-18, same session):** the owner reviewed the UI by eye and
  asked for two changes — a fake title bar, and working scrollbars. Both landed and both were
  verified by *driving the running window* instead of asserting: the window's style at startup is
  `0x140F0000` (no `WS_CAPTION`, `WS_THICKFRAME` intact), `WM_NCHITTEST` at the edges returns
  `HTLEFT` / `HTRIGHT` / `HTTOP` / `HTBOTTOM` with `HTCLIENT` in the middle, maximizing returns
  `0x150F0000` (still no caption) and flips the glyph to restore, and at 1000×500 three wheel
  notches bring the `Behaviour` rows into view that were unreachable before. The raw evidence is in
  `D-055` / `D-056`.
- **Also confirmed:** the plugin's stale `decorated: true` / `visible: false` state was the reason
  the restored window came back 1447 px tall with a caption on the *first* run of this pass; the
  plugin now restores geometry only (`D-055`).
- **Remaining evidence (needs eyes, not assertions):** screenshots of every pane in **light and
  dark** at 100/150/200%; the no-flash check on open in both themes; a live System-mode OS theme
  change being followed with the window open; the appearance choice surviving a restart; the tray
  icon on light and dark taskbars; keyboard-only completion of onboarding and Settings; and the
  three entry points resolving on a real build (`index.html`, `onboarding.html`, `rename.html`).

### T-024 — Updater: tray item and native save dialogs — `P2` — `TODO` *(half done)*
- **Done (`D-057`):** the real check exists — the engine calls `updater.check_for_updates()`,
  publishes `{"type":"update"}`, and the shell stores it in `state.updateTag` and logs it.
  `B-11` (string inequality) and `B-14` (`/releases/latest` 404s while every release is a
  prerelease) are fixed in `updater.py`, so the check fires for this project's release style.
- **Remaining deliverable:** show the tray item only when `state.updateTag` is set (`TR-4`, opens
  the release page), and add the native save dialog behind `export_config` / `export_logs`
  (`D-051`).
- **Acceptance:** with no release newer than the running build the tray shows the version header
  alone; with one, it shows `Update to vX.Y.Z` and opens the release page.

### T-025 — Single-source `config.json` defaults — `P2` — `TODO` *(removes `D-053` debt)*
- **Problem:** `config.py::DEFAULT_CONFIG`, `config.example.json`, and
  `config_file.rs::DEFAULT_CONFIG_JSON` now describe the same table.
- **Deliverable:** have the engine report defaults over the `T-022` protocol (or ship
  `config.example.json` as a bundle resource) and delete the Rust copy. `AGENTS.md` §6's
  "adding a config key = 4 edits" then becomes true again.
- **Acceptance:** exactly one editable source of the table; a new key added there shows up in the
  UI with no Rust change.

### T-026 — Windows 11 snap-layout flyout on the custom maximize button — `P2` — `TODO`
- **Problem:** the frameless chrome (`D-055`) draws its own maximize button, and hovering it does
  **not** open Windows 11's snap-layout flyout: the flyout is triggered by the window answering
  `WM_NCHITTEST` with `HTMAXBUTTON` over the button's rectangle, which a frontend-drawn button
  cannot do. Nothing regressed — dragging to an edge still snaps, and dragging to the top still
  maximizes — but this is the one piece of native maximize behaviour the custom chrome loses.
- **Deliverable:** answer `WM_NCHITTEST` for the button rectangle (a Rust-side hit test against
  bounds published by `WindowControls` over the existing `window-state` channel), or record the
  loss as accepted.
- **Acceptance:** hovering the maximize button opens the flyout, and every other hit-test result
  (`HTLEFT`, `HTTOP`, `HTCLIENT`, …) is unchanged.

### T-027 — Dormant/hidden window while broadcasting is paused (`SH-6`) — `P3` — `TODO`
- **Problem:** `SH-6` asks for the Settings window to hide while paused, leaving the tray up.
  Nothing implements it today; pausing only clears the presence (`D-057`).
- **Deliverable:** decide whether pause should hide the window at all (it fights `D-054`'s
  "close hides, the tray is the way back"), then implement it in `windows.rs`.
- **Acceptance:** an explicit decision entry, and the chosen behaviour verified from the tray.

### T-028 — Ship a frozen engine for the release layout — `P1` — `TODO`
- **Problem:** the shell finds `DiscordAutoRPC-engine.exe` beside itself, else a `python.exe` on
  `PATH`. A user who installs the shell alone gets the mock fallback and never a presence
  (`R-7`).
- **Deliverable:** build the `engine_stdio.py` pipeline into `DiscordAutoRPC-engine.exe`
  (PyInstaller, `--engine-stdio` as the entry, no Qt) as a CI artifact, ship it in the release zip
  beside the shell exe, and teach `.github/workflows/build-release.yml` to include it.
- **Acceptance:** on a machine with no Python installed, the release build shows a real presence
  from a real foreground app.

### T-029 — Engine-side extras over the protocol — `P3` — `TODO`
- **Deliverable:** the two calls the shell still cannot make because they are HTTP/GDI work that
  belongs to the engine: the SteamGridDB "Test key" check (`G-11`) and `restart_engine` (only if
  the restart question is ever revisited — `D-057` rejected a silent restart for now).
- **Acceptance:** each is a documented protocol message with a failure shape the UI can display.

---

## § Now (P0–P1, do these first)

### T-008 — Remove the legacy `watcher.pyw` autostart path *(fixes B-1, B-2)* — `P1` — `TODO`
- **Problem:** Two independent autostart mechanisms exist and both count as "enabled",
  so the app can be launched twice and users get inconsistent behavior.
  - `config.set_autostart_enabled()` → `DiscordAutoRPC.lnk` → `main.py --startup` ✅ (current design, D-005)
  - `enable_autostart.bat` → `DiscordAutoRPCWatcher.lnk` → `watcher.pyw` ❌ (legacy, D-005)
  - `config.is_autostart_enabled()` treats **either** shortcut as enabled.
- **Deliverable:**
  1. Delete `watcher.pyw`, `enable_autostart.bat`, `disable_autostart.bat`.
  2. In `config.set_autostart_enabled()`, also clean up a stale `DiscordAutoRPCWatcher.lnk`.
  3. Keep `is_autostart_enabled()` tolerant of the legacy shortcut for one release
     (detect-then-remove on next toggle).
- **Acceptance:** Fresh install + toggle autostart → exactly one `.lnk`
  (`DiscordAutoRPC.lnk`) in the Startup folder; no process named from `watcher.pyw`.
- **Risk:** Users upgrading from source installs who relied on the watcher keep working
  via `--startup`, but their old shortcut must not double-launch.

### T-001 — Add a smoke/integration test suite — `P1` — `TODO` *(fixes B-7)*
- **Deliverable:** `tests/` with `pytest`, covering the pure logic that has no OS/network
  dependency:
  - `context.extract_dynamic_tagline` — one case per parser (browser platform match,
    Excel file, IDE `file (project)`, Spotify, noise stripping, 128-char truncation).
  - `detector.resolve_display_name` / `_clean_display_name` — suffix stripping + override precedence
    (mock `_extract_pe_version_strings`).
  - `detector.resolve_tagline` — full precedence order incl. `enable_dynamic_taglines: false`.
  - `detector.is_ignored` / `is_incognito` — system path, config list, runtime list,
    whitelist-only, incognito markers (pure functions, mock `_load_json_list`).
  - `config.validate_app_id` / `load_config` merge + fallback on corrupt JSON (use `tmp_path`).
  - `presence.PresenceManager` dedupe + rate limit (stub `Presence`).
- **Acceptance:** `pytest` passes on Windows with PyQt6 installed but no Discord running;
  add `requirements-dev.txt` (pytest, ruff) and a `.github/workflows/ci.yml` that runs on
  push/PR.

### T-002 — Add linting + formatting config — `P2` — `TODO` *(fixes B-7)*
- **Deliverable:** `ruff` (or `flake8` + `black`) config in `pyproject.toml`.
- **Acceptance:** `ruff check .` exits 0 on the current tree; wire it into the T-001 CI job.
- **Note:** first pass will flag the unused imports in `B-8`; clean them up here.

---

## § Next (P2)

### T-030 — Icon reliability: bounded retries + per-app cache clearing — `P2` — `BLOCKED`
- **Blocked on:** the owner's answers to the five questions in
  [`ICON_RELIABILITY_RESEARCH.md`](ICON_RELIABILITY_RESEARCH.md) §7. **No code has been written**,
  at the owner's request (2026-10-18).
- **Problem (measured — the doc's appendix):** the retained log shows 117 fallbacks for WhatsApp
  Desktop (its packaged/MSIX exe has *no* icon resource to extract — a hard failure, retried every
  poll) and 68 for Antigravity IDE inside one 13-minute window that *no* log line explains.
  `icons.get_icon_url` runs on **every** tick, so a failing app is re-extracted and re-uploaded
  every `poll_interval` (5 s) with no backoff, no attempt count and no negative cache — "3 retries"
  already happen accidentally, unlimited and invisible.
- **Deliverable (the doc's S1–S3; each ships alone):**
  1. **S1** — failure logging with stage + reason at WARNING; stamp `presence.start_epoch` at
     detection so a slow fetch cannot shift Discord's timer; atomic `icons._save_cache`; memoize
     `_validate_icon_url`'s verdict so an untrusted override URL is not probed every tick.
  2. **S2** — a 3-attempt ladder in `icons.py` (1 s / 3 s gaps, ~6 s per-tick budget, an escalating
     60 s → 5 min → 30 min park; hard failures park immediately) plus an optional `iconState` field
     in the `app` event.
  3. **S3** — `icons.clear_icon_cache(exe_paths)` + `icons.cached_icons()` → the protocol pair
     (`clear_icon_cache` / `get_icon_cache`) → shell `clear_icon_cache(exe_keys)` +
     `icon_cache_listing()` → Status-card **Refresh icon**, a searchable per-app list in the Logs
     dialog, and `invalidateAppIcon()` in `src/lib/icons.ts`.
- **Acceptance:** an app whose upload fails shows the default for at most one ladder rung and then
  recovers to the real icon without an app switch; a per-app clear refreshes exactly that app's icon
  within one tick and leaves the other entries alone; the log names the failing stage; the Discord
  timer matches the pane's "Detected at".
- **Folds in:** `T-013` (per-app icon refresh). Option `S5`/`E1` (packaged-app icons via the
  Explorer route) stays gated on the `T9` probe.

### T-003 — Single-source the version string — `P2` — `TODO` *(fixes B-3)*
- **Problem:** `updater.__version__`, README badges, and the git tag are all independent.
- **Deliverable:** One canonical version (e.g. `__version__` in `updater.py` or a
  `version.py`) read by the tray menu, the update checker, and the build. Add a release
  checklist: bump version → update README badge → tag `vX.Y.Z` → push.
- **Acceptance:** Changing the version in exactly one place updates `update_action` text,
  `check_for_updates()` comparison, and the built artifact name/zip name.

### T-004 — De-duplicate the built-in tagline table — `P2` — `TODO` *(fixes B-6)*
- **Problem:** `config.DEFAULT_CONFIG["taglines"]` and `detector._BUILTIN_TAGLINES`
  hold overlapping mappings; GUI edits only mutate the config side.
- **Deliverable:** Decide the layering (suggested: keep `_BUILTIN_TAGLINES` as the shipped
  fallback *source*, and seed/generate `DEFAULT_CONFIG["taglines"]` from it or drop the
  config-side duplicates), then implement so there is one editable list.
- **Acceptance:** Editing a tagline in Settings behaves identically to the built-in value;
  documented in `DECISIONS.md` as a new entry.

### T-005 — Document + centralize the third-party upload hosts — `P2` — `TODO` *(fixes B-4, B-5)*
- **Problem:** `icons.py` docstring claims catbox is the default (it is `freeimage`);
  the freeimage API key is hardcoded in source.
- **Deliverable:** Fix the module docstring, move the freeimage key into a module constant
  with a comment on its origin, and note in `README.md` the privacy implication of
  uploading extracted icons to a public host (and that `upload_host` is configurable).
- **Acceptance:** Docstrings match `DEFAULT_CONFIG["upload_host"]`; no behavior change.

### T-006 — Make `presence.py` error handling precise — `P2` — `TODO`
- **Problem:** `except (pp_exceptions.InvalidID, BrokenPipeError, Exception)` is a bare
  `Exception` in disguise, and `_rpc.update()` failures silently drop the presence.
- **Deliverable:** Catch specific `pypresence`/OS exceptions, log at a useful level, and
  add a bounded reconnect backoff so a dead Discord IPC pipe doesn't spin.
- **Acceptance:** Killing Discord mid-session produces one clear log line and recovery
  within `RECONNECT_INTERVAL` after Discord returns.

---

## § Later (P3)

### T-007 — Auto-update (download & replace) — `P3` — `TODO`
- **Context:** `updater.py` only *notifies*; the tray menu opens the release page.
- **Deliverable:** Optional self-update: download the zip/exe, verify, swap on exit
  (careful: a running `.exe` cannot overwrite itself — use a helper/rename dance).
- **Acceptance:** Documented design in `DECISIONS.md` before implementation; must never
  corrupt an install or lose `config.json`.

### T-009 — Dedicated "Ignored apps" management parity in the tray — `P3` — **SUPERSEDED**
- **SUPERSEDED 2026-10-18 by `D-037`.** The rewrite merges `config.ignored_exes` and
  `ignore_list.json` into one source of truth; the design is tracked as **T-019**. Do not
  implement this in `gui.py`.
- **Problem:** The tray can *add* to `ignore_list.json`, but removal requires the Settings
  GUI tab; the runtime list and `config["ignored_exes"]` are surfaced differently.
- **Deliverable:** Decide whether runtime ignores should live in `config.json` (single
  source) or stay in `ignore_list.json` (current, D-012); then unify the UI.
- **Acceptance:** Whatever is added from the tray appears removable from the tray.

### T-010 — SteamGridDB key UX — `P3` — `TODO` — *subsumed by T-020 (`D-035`)*
- **Problem:** `steamgriddb_api_key` exists in config but has no GUI field.
- **Deliverable:** Add a masked input in the Settings → General tab (+ "test key" button),
  and document that lookups are optional and rate-limited.
- **Acceptance:** Setting a key makes `icons._try_steamgriddb` run before exe extraction.

### T-011 — Reduce binary size / cold start — `P4` — `TODO`
- **Context:** PyQt6 + `--onefile` produces a large exe and re-unpacks to `_MEIPASS` each launch.
- **Deliverable:** Evaluate `--onedir`, PyInstaller `excludes` for unused Qt modules, and
  measure startup time; only adopt if the tradeoff is documented.

---

## § Backlog / Ideas (not yet prioritized)

- T-012 — Tray tooltip should reflect the currently broadcast app.
- T-013 — *(`SUPERSEDED` by `T-030`, 2026-10-18)* Per-app icon refresh button in Settings
  (currently only a global cache reset).
- T-014 — Accessibility/UX: keyboard navigation in the Settings tabs. *(subsumed by T-020 —
  the rewrite requires keyboard-only completion of onboarding and Settings)*
- T-015 — i18n / localized taglines for the built-in table.
- T-016 — Surface `poll_interval` in the GUI (it exists in config but is not editable).
  *(subsumed by T-020 / `D-035`; its visibility is Q5, still open)*
- T-017 — Signed releases / checksums for the downloadable exe (SmartScreen trust).

---

## § Done

| Task | Commit | Date | Notes |
|---|---|---|---|
| `T-018` | `1795dce` | 2026-10-18 | G1 answers — Q4 "Continue without connecting" (`D-044`), Q5 Advanced visible (`D-045`). |
| `T-019` | `1795dce` | 2026-10-18 | Unified ignore list: `config.ignored_exes` is the one store (`D-047`). |
| `T-021` | `1795dce` | 2026-10-18 | Q1 answered — Option A, the Python sidecar over stdio (`D-043`). Q2/Q7/Q8 stayed open and live in the handoff §13. |
| `T-022` | `2f07b9f` | 2026-10-18 | Engine seam: `engine_stdio.py` + `sidecar.rs`, verified end to end on a live Discord client. Design and rationale in `D-057`; detail in the entry above. |
