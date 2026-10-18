# Rust Migration Research — Discord AutoRPC

> **Status:** Research only. **No code has been changed.** This document exists to decide
> *whether*, *how*, and *in what order* to port Discord AutoRPC from Python to Rust.
> Authored: **2026-10-18** · Scope: full codebase (`main.py`, `config.py`, `detector.py`,
> `context.py`, `icons.py`, `presence.py`, `gui.py`, `updater.py`, `watcher.pyw`)
>
> Companion docs: `AGENTS.md` (conventions), `STATE.md` (current snapshot),
> `DECISIONS.md` (D-001…D-019 — the Python-era decisions this port must honor or
> consciously overturn), `TASKS.md` (open work).
>
> **Crate/version data below was verified against crates.io on 2026-10-18.** Anything
> marked ⚠️ is my inference and must be validated by a spike before committing.

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [The behavioral contract (what must survive the port)](#2-the-behavioral-contract)
3. [Decision drivers and hard constraints](#3-decision-drivers-and-hard-constraints)
4. [Top-level architecture options](#4-top-level-architecture-options)
5. [Library & technology decision records (LD-01…LD-28)](#5-library--technology-decision-records)
6. [File-by-file port map](#6-file-by-file-port-map)
7. [Phased migration plan](#7-phased-migration-plan)
8. [What NOT to port](#8-what-not-to-port)
9. [Risk register](#9-risk-register)
10. [Effort estimate](#10-effort-estimate)
11. [Open questions needing an owner decision](#11-open-questions-needing-an-owner-decision)
12. [v1.0 acceptance criteria](#12-v10-acceptance-criteria)
13. [Appendix A — dependency license matrix](#appendix-a--dependency-license-matrix)
14. [Appendix B — verified crate data](#appendix-b--verified-crate-data)
15. [Appendix C — Win32 API surface required](#appendix-c--win32-api-surface-required)

---

## 1. Executive summary

**Verdict: technically straightforward, strategically large.** Every Python dependency has
a mature, actively-maintained Rust equivalent, and one of the hardest parts — Discord's
`status_display_type: "name"` behavior that `presence.py` depends on — is already supported
by the leading Rust RPC crate (verified, see LD-06). The rewrite is *not* blocked by any
missing capability.

**The cost is the GUI.** `gui.py` is 998 lines of PyQt6 covering an onboarding wizard, a
rename dialog, a 5-tab settings window, a themed dark stylesheet, and a live log terminal.
That is ~60% of the porting effort and 100% of the visual-regression risk. The presence
*engine* (`detector`, `context`, `icons`, `presence`, `config`, `updater`) is ~1,700 lines
of logic that ports almost mechanically.

**Three findings that should shape the decision:**

1. **The engine and the GUI must be separated into different crates.** The engine is
   UI-agnostic and ports 1:1. If we put the engine behind its own crate boundary with a
   typed API, the GUI framework choice becomes **reversible** and can even be deferred.
   This is the single most important architectural instruction in this document.
2. **A hybrid (PyO3) path exists and is dramatically lower risk** — rewrite only the
   hot/OS-heavy modules in Rust as a Python extension and keep the PyQt6 GUI. It captures
   the performance/robustness wins without a UI rewrite. See §4 Option B.
3. **Two popular crates are licensing landmines for an MIT project:** `slint`
   (GPL-3.0-only in its free tier) and `win-icon-extractor` (AGPL-3.0-only). Both would
   force a license change. Avoid unless the owner intends to relicense. See LD-03/LD-10.

**Recommended path (pending owner sign-off):** Option A/C — full native Rust, engine in its
own crate, UI in a thin shell — executed in the 6 phases of §7, shipping as **v0.2.0** with
`config.json` backward compatibility and a Rust-vs-Python golden test suite proving parser
parity. Expected size: **~2,500–3,500 lines of Rust** for parity, versus ~3,300 lines of
Python today (9 modules).

**Do not start by writing the GUI.** See §7.

---

## 2. The behavioral contract

Everything below is *observable behavior* that users and the release process depend on.
The port is only successful if all of it is preserved (or a deviation is explicitly
recorded in `DECISIONS.md`).

### 2.1 Engine behaviors

| ID | Behavior | Source | Must preserve? |
|---|---|---|---|
| BC-01 | Poll foreground window every `poll_interval` (default 5s) | `main._poll_loop`, D-002 | Yes |
| BC-02 | `debounce_seconds` (default 10s) before switching the reported app | `detector.Detector.poll` | Yes |
| BC-03 | `idle_timeout_seconds` (default 60s) before clearing presence | `detector.Detector.poll` | Yes |
| BC-04 | When **Discord itself** is focused, keep showing the last app (and refresh the idle timer) while its process is alive | `detector.Detector.poll` | Yes — very visible |
| BC-05 | Skip any exe under `%SystemRoot%` | `detector.is_ignored` | Yes |
| BC-06 | Skip `config.ignored_exes` + runtime `ignore_list.json`; honor `whitelist_only` | `detector.is_ignored`, D-012 | Yes |
| BC-07 | Mask incognito/private browser windows when `mask_private_browsing` | `detector.is_incognito`, D-013 | Yes — privacy guarantee |
| BC-08 | Never re-send an identical presence payload; ≤1 update per 15s | `presence.PresenceManager`, D-006 | **Yes — hard requirement** |
| BC-09 | Timer start epoch is per-exe-path and resets only when the PID changes | `presence._get_start_time` | Yes |
| BC-10 | Presence header shows the app name via `status_display_type = name`; tagline in `details` | `presence.PresenceManager`, D-007 | Yes |
| BC-11 | Display name: overrides → PE `ProductName`/`FileDescription` (suffix-stripped) → Title-Cased filename stem | `detector.resolve_display_name`, D-010 | Yes |
| BC-12 | Tagline precedence: override → dynamic title parse → user taglines → built-in table → keyword match → empty | `detector.resolve_tagline`, D-011 | Yes |
| BC-13 | Dynamic title parsers: browsers (27 curated platforms), Excel/Word/PowerPoint, Notion, Obsidian, Notepad, IDEs, Spotify, VLC/MPC/MPV | `context.py` | Yes — golden-testable |
| BC-14 | Strip `(4) ` unread badges and `● * •` dirty marks; truncate to ~120 chars | `context._clean_title`, `_truncate` | Yes |
| BC-15 | Reject browser-title candidates containing `@` or `/`; reject `http…` | `context._parse_browser` | Yes — privacy |
| BC-16 | Icon URL: override → cache → SteamGridDB → extract+upload → `default_icon_url` | `icons.get_icon_url` | Yes |
| BC-17 | Extraction prefers `PrivateExtractIconsW` @256px, falls back to `ExtractIconEx` | `icons._extract_icon_image` | Yes |
| BC-18 | Upload host chain (`freeimage`↔`catbox`) with failover; cache the URL even if validation is inconclusive | `icons._upload_png`, D-009 | Yes |
| BC-19 | Trust-list fast path for known CDNs + image extensions (no network probe) | `icons._TRUSTED_IMAGE_HOSTS` | Yes |
| BC-20 | Config hot-reload every 30s without restart, incl. detector re-creation on change | `main.JsonReloader` | Yes |
| BC-21 | `load_config()` merges missing defaults so old configs keep working | `config.load_config` | Yes |
| BC-22 | First-run wizard if `application_id` is invalid/absent | `main.main`, `gui.run_onboarding_wizard` | Yes |
| BC-23 | Single instance; a second launch signals the first to raise Settings | `main.main`, D-018 | Yes (mechanism may change) |
| BC-24 | `--startup`: start dormant (hidden tray, no RPC) and wake when Discord appears | D-005 | Yes |
| BC-25 | `auto_close_with_discord`: dormant/hide when Discord is absent, reconnect when present | `main._poll_loop` | Yes |
| BC-26 | Async GitHub release check; tray shows an update affordance | `updater.check_updates_async` | Yes |
| BC-27 | Rotating log file (2 MB × 3) **and** a live in-GUI log terminal | `main._setup_logging`, `gui.QtLogHandler` | Yes |
| BC-28 | Runtime "ignore current app" and "rename active app" apply **immediately**, without reload | `main._create_qt_tray` | Yes |

### 2.2 Data & config compatibility

| Item | Contract |
|---|---|
| `config.json` | Same keys and semantics (`AGENTS.md` §6). Unknown keys should be **preserved** on rewrite. |
| `icon_cache.json` | `{ "<exe_path_lowercased>": "<url>" }` |
| `ignore_list.json` | `["<exe_name_lowercased>", …]` |
| Data directory | Dev = repo root; frozen = portable if `portable.txt`/`config.json` beside exe, else `%APPDATA%\DiscordAutoRPC` (D-014) |
| Log location/name | `autorpc.log` in the data dir, rotating |
| Autostart | One shortcut/entry, activated with `--startup` (D-005); `watcher.pyw` path is **dead** (B-1/T-008) |

> **Test of the contract:** a user should be able to delete the Python install, drop in the
> Rust exe, keep `config.json`/`icon_cache.json`/`ignore_list.json`, and notice no
> behavioral difference except faster startup.

### 2.3 Known Python defects that must NOT be faithfully ported

From `STATE.md` §5 — fix these during the port rather than replicating them:

- `B-1` two competing autostart mechanisms → port **one** (LD-17).
- `B-3` version string duplicated in 3 places → solve structurally (LD-24).
- `B-4` `icons.py` docstring contradicts the actual default host.
- `B-5` hardcoded freeimage API key in source (LD-13).
- `B-6` built-in tagline table duplicated between `config` and `detector` (LD-28).
- `B-8` unused imports / redundant `CONFIG_PATH` reassignment in `main.py`.
- **New, discovered while writing this doc:** `config.save_config()` writes non-atomically
  (truncate + write). A crash mid-write corrupts the user's config. Rust should write
  temp-then-rename (LD-14).
- ⚠️ **Verify during port:** `presence.py` passes `start_epoch` in **seconds**
  (`int(time.time())`), while the Discord RPC schema specifies **milliseconds**. The Rust
  crate documents milliseconds (`Timestamps::start` — "Unix time (in milliseconds)").
  Either pypresence silently compensates or the Python timer is subtly wrong. Confirm
  empirically before porting, and port whichever is *correct*.

---

## 3. Decision drivers and hard constraints

| Driver | Weight | Notes |
|---|---|---|
| Binary startup latency | High | `PyInstaller --onefile` extracts to `_MEIPASS` on every launch. Rust has no extraction step. ⚠️ Expect a multi-hundred-ms to multi-second improvement; measure, don't assume. |
| Runtime robustness | High | Wide-string handling, explicit error types, no GIL, no interpreter version drift. |
| Distribution size | Medium | Qt binaries are large; a native Rust exe is typically far smaller. Tauri trades this for a WebView2 dependency. |
| Maintenance longevity | Medium | Rust's compile-time guarantees + `cargo test` reduce regression risk; but the owner must be able to maintain Rust. |
| Antivirus/SmartScreen trust | Medium | Unsigned Rust binaries are **not** inherently safer than unsigned Python ones. UPX *increases* AV false positives (LD-22). |
| Time-to-parity | High | The GUI dominates. Any design that shrinks the GUI work is worth serious consideration. |
| License hygiene | High | Must stay MIT-distributable (LD-03, LD-10). |
| Keep Windows-only | Non-negotiable | Both `AGENTS.md` §2.1 and D-001 make this explicit. Do not opportunistically add cross-platform abstractions. |

**Hard constraints**

- Windows 10 and 11, x64. (Confirm whether Windows 10 must still be supported — §11 Q1.)
- No admin/elevation requirement for normal operation.
- No injection/hooking into target processes (anti-cheat safety; also D-001's spirit).
- Users must never lose their configuration across the migration.
- Must remain buildable and releasable from GitHub Actions.

---

## 4. Top-level architecture options

### Option A — Full native Rust, single binary, native GUI

Rewrite everything; one `.exe`; UI in a Rust GUI toolkit.

- **Pros:** smallest/fastest artifact; no runtime dependency; single language; unit-testable core; no interpreter.
- **Cons:** largest UI effort; loss of Qt's mature details (table widgets, file dialogs) unless replaced carefully; the tray+GUI event-loop integration is the fiddliest part.
- **Risk:** Medium-high (UI), Low (engine).

### Option B — Hybrid: Rust core, keep the Python/PyQt6 GUI (PyO3)

Rewrite `detector`/`context`/`icons`/`presence` as a native extension module
(`pyo3` + `maturin`), keep `main.py`/`gui.py`/`config.py` as-is.

- **Pros:** ~40% of the work; the risky/hot code becomes Rust; GUI untouched → zero visual regression; can be done incrementally module-by-module; easy to A/B against the pure-Python implementation.
- **Cons:** still ships Python + PyInstaller + Qt (startup cost and size largely remain); two languages to maintain forever; PyO3 ABI/packaging complexity inside PyInstaller; does **not** achieve the primary "cheap distribution/fast start" goals.
- **Risk:** Low.

### Option C — Tauri v2 shell + Rust engine crate

Tauri 2.12 for the window/tray/updater/dialogs, HTML+CSS+JS for the UI, Rust for the engine.

- **Pros:** Tauri solves tray icon, single-instance, autostart, updater, and file dialogs **natively via official plugins** — i.e. it removes the four riskiest integration problems; HTML/CSS is a natural translation target for `DISCORD_DARK_QSS`; small binary.
- **Cons:** WebView2 runtime dependency (bundled on Win 11; usually present on updated Win 10, but not guaranteed on stripped/locked-down machines); requires accepting a web tech stack; more moving parts in CI.
- **Risk:** Medium.

### Option D — Stay on Python; mitigate with Nuitka / onedir

No Rust. Address startup/size with `--onedir` or Nuitka, and fix `TASKS.md` items.

- **Pros:** zero migration risk; immediate.
- **Cons:** none of the robustness/performance benefits; still ships an interpreter.
- **Note:** this is a legitimate answer to "should we port at all?" and should be an explicit choice, not a default.

### Option E — Two-process hybrid (Rust engine daemon + Rust UI, no Python)

Effectively Option A with the engine isolated in a separate process instead of a crate.
**Not recommended** — it converts an in-process call into an IPC protocol for no benefit.
Listed only to record that it was considered and rejected.

### Decision matrix

Scores 1–5 (5 = best). Weights reflect §3.

| Criterion | Weight | A | B | C | D |
|---|---|---|---|---|---|
| Time to parity | 3 | 2 | **5** | 3 | **5** |
| Startup latency win | 2 | **5** | 1 | 4 | 2 |
| Distribution size win | 2 | **5** | 1 | 4 | 2 |
| Runtime robustness win | 2 | **5** | 4 | 4 | 2 |
| UI risk (lower is better → inverted) | 3 | 2 | **5** | 3 | **5** |
| Integration risk (tray/updater/single-instance) | 3 | 2 | 3 | **5** | **5** |
| Deployment/AV trust | 2 | 4 | 3 | 3 | 4 |
| Long-term maintainability (single stack) | 2 | **5** | 1 | 4 | 4 |
| **Weighted total** | | **53** | 58 | **65** | **58** |

**Read:** Option **C (Tauri)** scores highest, but only because it buys down integration
risk — and it does so by accepting a WebView2 dependency and a JS UI. Option **A** is the
"smallest, fastest, one-language" purist answer at the cost of the most UI work.

**Recommendation: build the engine crate first (identical in A and C), then choose the
shell.** The engine is ~60% of the work, is required by both, and is UI-agnostic. Deferring
the GUI decision costs nothing and lets a 2–3 day spike (spike S-1, §7) decide it with real
evidence. If forced to pick today: **A with `eframe`/`egui`** for zero runtime
dependencies, falling back to C only if the tray+window integration proves painful.

---

## 5. Library & technology decision records

Format: **Decision · Options · Recommendation · Rationale · Risk · Verify.**

---

### LD-01 — Toolchain, edition, MSRV
**Options:** stable Rust; pin an MSRV.
**Recommendation:** Stable toolchain, **edition 2024**, MSRV **1.95**.
**Rationale:** MSRV is driven by the highest requirement among our candidates — `egui`/
`eframe` 0.37 and `sysinfo` 0.39 require 1.95; `tray-icon` 0.26 requires 1.90; `self_update`
and `iced` require 1.88. Pinning 1.95 satisfies all of them with headroom.
**Risk:** MSRV churn in the GUI crates is fast (egui ships ~monthly). Mitigation: pin exact
versions in `Cargo.toml` and let Dependabot/`cargo update` be a deliberate act.
**Verify:** ✅ MSRV numbers read from crates.io version metadata (Appendix B).

---

### LD-02 — Async runtime policy
**Options:** (a) `tokio` everywhere; (b) no async at all — threads + blocking I/O; (c) mixed:
`tokio` only inside `reqwest`.
**Recommendation:** **(b) primarily, with a narrowly-scoped exception.** Use plain OS threads
and blocking I/O; use **`ureq` 3.x** (blocking HTTP) rather than `reqwest`, which avoids
pulling `tokio` in at all.
**Rationale:** The app has exactly one concurrency need — "one poll loop + a few
fire-and-forget network calls + a UI thread". `tokio`'s runtime, work-stealing scheduler and
`Send`/`'static` bounds are pure overhead and complexity here. Removing `tokio` shrinks the
dependency tree and binary meaningfully (⚠️ measure; expect a few MB).
**Risk:** If we later pick Tauri, Tauri **requires** `tokio` internally, so this decision is
moot in Option C. Note that as a reason Option A/C coexistence is clean: the engine can be
runtime-agnostic.
**Verify:** ⚠️ Confirm `ureq` 3.x handles multipart `POST` with a file field (needed for both
upload hosts). If not, use `reqwest` with `blocking` + `rustls`/native TLS.

---

### LD-03 — GUI framework  *(highest-impact decision)*
**Options:**

| Framework | Ver | License | Fit |
|---|---|---|---|
| `eframe`/`egui` | 0.37 | MIT OR Apache-2.0 | Immediate-mode. Fast to write settings UIs, tables, log views. Custom dark theming is easy. Unusual look-and-feel vs. native. |
| `iced` | 0.14 | MIT | Elm-style retained UI. Good widgets, steeper learning curve, more boilerplate. |
| `tao` + `egui`/`wgpu` | tao 0.37 / winit 0.30 | Apache-2.0 | Maximum control, most integration work. This is roughly what Tauri does underneath. |
| `slint` | 1.18 | **GPL-3.0-only** OR royalty-free/commercial | ❌ **Rejected for licensing.** GPL-3.0 in a distributed binary would force the entire project to GPL, breaking the MIT license. |
| `Tauri` + HTML/CSS/JS | 2.12 | Apache-2.0 OR MIT | ✅ License-clean. Best integration story (LD-04/LD-16/LD-17/LD-19). Adds WebView2 dependency. |
| Raw `windows-rs` Win32 dialogs | 0.62 | MIT OR Apache-2.0 | Maximum fidelity to the current native feel; by far the most work. |

**Recommendation:** **`eframe`/`egui`** if we stay in-process-native (Option A), or **Tauri**
if we accept WebView2 (Option C). **Reject `slint` outright** on license grounds.
**Rationale:** The settings window is mostly forms, three sortable tables, a list, a
checkbox row, and a monospace log view — squarely egui's sweet spot. egui also gives us the
custom dark palette trivially, and keeps the single-static-binary property and the fast
startup that motivate the whole port.
**Risk:** egui's text/edit widgets are less polished than Qt's for form-heavy dialogs, and
accessibility (screen readers, keyboard nav) is weak — the current app has no accessibility
story either, so this is not a regression, but note it. egui is also a fast-moving
pre-1.0 dependency (breaking changes on minor bumps).
**Verify:** ⚠️ Spike S-1 must prototype (a) tray icon + settings window coexisting,
(b) a 3-column editable table, (c) an auto-scrolling monospace log view, before committing.

---

### LD-04 — Tray icon
**Options:** `tray-icon` 0.26 (tauri-apps, 35.9M downloads, MIT/Apache-2.0); Tauri's built-in
tray; raw `Shell_NotifyIconW` via `windows-rs`.
**Recommendation:** **`tray-icon` 0.26**, paired with the chosen event loop. Use Tauri's
built-in tray if Option C.
**Rationale:** Actively maintained by the Tauri org, correct on Windows, and — critically —
the current app's D-004 lesson (`pystray`'s private event loop was invisible in the compiled
build) is exactly the class of bug `tray-icon` + a real Win32 message pump avoids.
**Risk:** `tray-icon` does **not** own a message loop; it must be paired with `tao`/`winit`/
`eframe`, and the tray event stream must be pumped on the UI thread. This is the analogue of
`TrayBridge` and must be designed deliberately (LD-05).
**Verify:** ⚠️ Confirm the tray menu supports dynamic label mutation before showing (the
current menu relabels "Rename Active App (…)" and "Ignore <exe>" in `aboutToShow` — BC-28).

---

### LD-05 — Event loop & threading model
**Options:** (a) UI owns the main thread; worker thread for polling, communicating via a
channel (mirrors today's `TrayBridge`); (b) fully async single-threaded; (c) actor framework.
**Recommendation:** **(a).** Main thread owns the Win32 message pump / event loop. A single
dedicated **worker thread** runs the poll loop and pushes typed events into the UI over a
`crossbeam-channel` (or `std::sync::mpsc`) sender. Shared state behind `Arc<Mutex<…>>`/
`Arc<RwLock<…>>` or, better, kept entirely inside the worker with commands sent in.
**Rationale:** This is a direct, proven port of the current design
(`_poll_loop` + `TrayBridge` signals). It preserves the D-004 guarantee. Using channels with
**typed events** instead of a shared `dict` fixes the biggest structural weakness of the
Python version (an untyped, unvalidated mutable state bag touched by two threads).
**Risk:** Any accidental UI mutation from the worker is a data race the compiler will catch
(if we never hand UI handles across threads) or a `panic!`. Design so the worker literally
cannot reach a UI handle — pass only a `Sender<TrayEvent>`.
**Verify:** ⚠️ Spike S-1.

---

### LD-06 — Discord IPC client  *(de-risked — verified)*
**Options:**

| Crate | Ver | License | Notes |
|---|---|---|---|
| `discord-rich-presence` (vionya fork) | **1.1.0** | MIT | 661k downloads, updated 2026-01-26. **Verified** to support `name`, `status_display_type`, `activity_type`, timestamps, assets, buttons. |
| `discord-presence` (jewlexx) | 3.2.0 | MIT | 98k downloads, health-monitoring features, MSRV 1.82. Also viable. |
| `discord-sdk` (Embark) | 0.4.0 | — | Official-API reimplementation; last updated 2024-12. Heavier. |
| Raw named pipe + JSON | — | — | Full control; must reimplement the IPC framing (`OP 0 HANDSHAKE` / `OP 1 FRAME`, 4-byte LE length + LE opcode) and pipe discovery. |

**Recommendation:** **`discord-rich-presence` 1.1.0**, with the engine wrapping it behind our
own trait so it is swappable.
**Rationale:** The decisive requirement is BC-10 (`status_display_type = Name`, D-007).
Verified against the crate source: `Activity::new().name(..).status_display_type(StatusDisplayType::Name).details(..).assets(Assets::new().large_image(..).large_text(..)).timestamps(Timestamps::new().start(ms))`, with
`StatusDisplayType::Name = 0` matching Discord's `Name` display type. That is a 1:1 match for
`presence.py`'s modern path, so **the visible behavior — "Playing <app>" plus a tagline detail
line — is preserved exactly.**
**Risk:** The crate is a fork of a popular original; bus-factor is a single maintainer. The
trait wrapper limits blast radius. Also: the crate does **not** implement rate limiting or
dedupe — that logic is ours and must be ported from `presence.py` (BC-08).
**Verify:** ✅ API and enum values confirmed by reading crate `src/activity.rs` on 2026-10-18.
⚠️ Confirm the `Timestamps::start` unit (documented as milliseconds) against BC-08/§2.3.

---

### LD-07 — Foreground window + process introspection
**Options:** `sysinfo` 0.39 (heavy, MSRV 1.95); `windows-rs` direct
(`GetForegroundWindow` + `GetWindowThreadProcessId` + `OpenProcess` +
`QueryFullProcessImageNameW`); WMI.
**Recommendation:** **`windows-rs` direct.** No process-enumeration crate at all for this path.
**Rationale:** We need exactly two facts (owning PID, full image path) and `windows-rs` is
already a hard dependency for the tray/GDI/icon/PE work. Using
`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, …)` + `QueryFullProcessImageNameW` is
**strictly better than psutil**: it succeeds for elevated target processes where
`psutil.Process(pid).exe()` raises `AccessDenied`, so we will detect fewer apps as "unknown"
in real use. `PROCESS_QUERY_LIMITED_INFORMATION` is the documented least-privilege right and
is safe to use against anti-cheat-protected games (we never inject or read memory).
**Risk:** Handle leaks — every `OpenProcess` needs a `CloseHandle`; prefer the RAII wrappers
`windows-rs` generates (`HANDLE`-owning types) or a small `OwnedHandle` helper. Never use
`GetModuleFileNameEx` (it needs `PROCESS_VM_READ`, which elevated/protected processes deny).
**Verify:** ⚠️ Test against an elevated process (e.g. Task Manager) and a game.

---

### LD-08 — Window title retrieval
**Options:** `GetWindowTextW`; `GetWindowTextLengthW` + `SendMessageTimeoutW(WM_GETTEXT)`;
`GetWindowTextW` after `AttachThreadInput`.
**Recommendation:** **`SendMessageTimeoutW` with a short timeout (e.g. 50–100 ms)**, falling
back to `GetWindowTextW`.
**Rationale:** `GetWindowTextW` on a *foreign* window is documented to send `WM_GETTEXT`
and **can block indefinitely if the target app is hung** — which would freeze the poll loop
(today's Python code is exposed to the same class of issue). `SendMessageTimeoutW` bounds
that. This is a genuine robustness improvement worth calling out.
**Risk:** `SMTO_ABORTIFHUNG` may occasionally return an empty title; we must fall back to a
static tagline rather than showing nothing (BC-12 already ends in "empty string").
**Verify:** ⚠️ Confirm behavior with a deliberately hung test process.

---

### LD-09 — PE version metadata (`ProductName`, `FileDescription`)
**Options:** `windows-rs` `GetFileVersionInfoSizeW` / `GetFileVersionInfoW` / `VerQueryValueW`;
`pelite` 0.10 (last updated 2022 — stale).
**Recommendation:** **`windows-rs`**.
**Rationale:** Avoids a dependency that hasn't shipped in ~4 years. The Python code already
queries `\VarFileInfo\Translation` then `\StringFileInfo\<lang><codepage>\{ProductName,FileDescription}`
— a mechanical port. Also needs `GetFileVersionInfoSizeExW` for robustness against
locked/renamed files. Keep the `_clean_display_name` regex logic **exactly** as-is and
golden-test it (BC-11).
**Risk:** Version resources are inconsistent across vendors; the suffix-stripping heuristic
is fragile but proven in the field. Port the regex verbatim, don't "improve" it.
**Verify:** ⚠️ Compare `resolve_display_name` output for ~30 installed exes between Python and
Rust.

---

### LD-10 — Icon extraction
**Options:** `windows-rs` `PrivateExtractIconsW` + `ExtractIconExW` + GDI (direct port);
`windows-icons` 0.4 (MIT, 17k downloads — low adoption); `win-icon-extractor` 0.3 (**AGPL-3.0
— rejected**); `IShellItemImageFactory` (shell thumbnails, often nicer for UWP/Store apps).
**Recommendation:** **Direct port with `windows-rs`** (`PrivateExtractIconsW` @256, fallback
`ExtractIconExW`), as a deliberate repeat of D-008.
**Rationale:** Keeps the proven behavior, keeps licensing clean (MIT/Apache-only), and the
GDI dance is already written and understood — it becomes `unsafe` code with RAII handles
instead of an untested third-party crate. Consider `IShellItemImageFactory` later as an
*additional* fallback for packaged apps whose icon isn't in the PE (e.g. some WinUI apps) —
note as a possible improvement, not a requirement.
**Risk:** `unsafe` GDI code; `HIICON`/`HBITMAP` leaks; BGRA→RGBA channel order and the
top-down DIB negative-height convention must be preserved exactly (the Python code comments
this precisely and it is easy to get wrong — expect the icon to appear vertically mirrored
or blue-tinted on the first attempt).
**Verify:** ⚠️ Byte-compare extracted icons against the Python output for a sample of exes.

---

### LD-11 — Image encoding & resizing
**Options:** `image` 0.25 (MIT/Apache-2.0, 217M downloads); `png` crate directly;
`fast_image_resize`.
**Recommendation:** **`image` 0.25**, PNG encoder only (`default-features = false`,
`features = ["png"]`), with `image::imageops::resize(…, FilterType::Lanczos3)` to mirror PIL's
`Image.LANCZOS`.
**Rationale:** Single well-maintained crate, no C dependencies, matches the current
`resize(..., Image.LANCZOS)` step 1:1.
**Risk:** Enabling default features pulls in far more codecs than needed (size). Disable them.
**Verify:** ⚠️ Confirm the resize kernel visually matches (Lanczos3 vs PIL LANCZOS).

---

### LD-12 — HTTP client
**See LD-02.** **`ureq` 3.4** (blocking) preferred over `reqwest` 0.13 (async/`tokio`).
**Rationale:** Two upload endpoints + one GitHub API call + one icon-URL probe. That does not
justify an async runtime. Use `rustls` (default) or native TLS — ⚠️ note that the current code
relies on the OS/Python TLS stack, so `native-tls` may be friendlier for corporate proxies.
**Risk:** Multipart upload support must be confirmed (see LD-02 verify).

---

### LD-13 — Upload hosts, failover, and secrets
**Decision:** Keep the **same two hosts** (`freeimage`, `catbox`) and the same failover chain,
the same trust-list fast path, and the same "cache the URL once the upload returns one, validate
secondarily" rule (D-009). Make the host list a **data-driven table** so adding a host is a
one-line change.
**Change from Python:** move the freeimage API key out of inline source into a module constant
with a comment explaining it is a public/anonymous upload key (fixes `B-5`), and document in
the README that extracted icons are uploaded to a **public** third-party host — a privacy
disclosure the current README omits.
**Risk:** Third-party hosts can vanish; `upload_host` remains user-configurable.
**Verify:** ⚠️ Test both hosts' current API contracts at implementation time (they have
changed before).

---

### LD-14 — Configuration: serialization, atomicity, unknowns
**Options:** `serde` + `serde_json`.
**Recommendation:**
1. Define `#[derive(Serialize, Deserialize)] struct Config` with `#[serde(default)]` on every
   field, replacing the ad-hoc `DEFAULT_CONFIG` merge (BC-21) with something the compiler
   enforces.
2. **Atomic writes:** serialize to a temp file in the same directory, then `fs::rename`
   (same-volume rename is atomic on NTFS). Fixes the corruption window found in §2.3.
3. **Preserve unknown keys:** keep a `#[serde(flatten)] extra: serde_json::Map<String, Value>`
   so a newer config written by a future version is not silently stripped by an older build.
4. Keep the exact on-disk key names (skew-cased `application_id`, `debounce_seconds`, …) via
   `#[serde(rename_all = "snake_case")]` — **do not** adopt Rust-idiomatic naming on disk.
5. Keep `load_config()`'s tolerant behavior: corrupt JSON → log + fall back to defaults
   rather than crashing.
**Risk:** `#[serde(default)]` + `flatten` interacts awkwardly with strict typing; test the
round-trip.
**Verify:** ⚠️ Round-trip test: load the Python-written `config.example.json`, save, diff.

---

### LD-15 — Logging, rotation, and the live GUI terminal
**Options:** `tracing` + `tracing-subscriber` + `tracing-appender` (rotation); `log` + `env_logger`.
**Recommendation:** **`tracing`** with three sinks:
1. `tracing-appender::rolling::daily`-style **size-based** rotation — ⚠️ `tracing-appender`'s
   rolling appender is time-based, so implement size-based rotation manually (check file size
   each write, rotate at 2 MB, keep 3) to preserve BC-27 exactly. Simpler alternative: keep
   time-based rotation and accept a small behavior change (record in `DECISIONS.md`).
2. A stdout/stderr sink only in debug builds.
3. A **custom `Layer`** that forwards formatted lines to the UI via a channel — the analogue
   of `gui.QtLogHandler`. Must be non-blocking (`try_send`, drop on full) so logging can never
   stall the poll thread.
Also port the "seed the console with the last 200 lines of the log file on open" behavior.
**Rationale:** Direct structural match to the current design, minus the Python
`logging`-globals-at-import-time smell.
**Risk:** Formatting must match closely enough that the log remains a familiar debugging tool.
**Verify:** ⚠️ Confirm the UI channel can't deadlock when the settings window is closed.

---

### LD-16 — Single instance + wake-up IPC
**Options:** (a) `windows-rs` named mutex + named event (direct port of D-018);
(b) `interprocess` 2.4 (local sockets; BSD-0/Apache); (c) `tauri-plugin-single-instance` if Option C.
**Recommendation:** **(a) named mutex + named event via `windows-rs`.**
**Rationale:** It is a ~30-line direct port of code that already works, requires no new
dependency, and needs no server loop. Keep the **same names**
(`DiscordAutoRPC_SingleInstance_Mutex`, `DiscordAutoRPC_Wakeup_Event`) — which has a real
benefit: if both the Python and Rust builds are installed during the migration, they will
correctly refuse to run simultaneously.
**Risk:** Handle lifetime; and a stale mutex cannot happen (the kernel releases it with the
process). ⚠️ Decide whether a *running Python instance* receiving a Rust instance's wake
signal is harmless — it is, because it's the same event semantics.
**Verify:** ⚠️ Test cross-version: launch Rust, then launch Python → Python must exit.

---

### LD-17 — Autostart mechanism
**Options:** (a) Startup-folder `.lnk` via `IShellLink`/`WScript.Shell` COM (current: `config.set_autostart_enabled`);
(b) `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry value;
(c) Task Scheduler task; (d) `auto-launch` 0.6 (MIT) crate — wraps (a)/(b);
(e) `tauri-plugin-autostart` if Option C.
**Recommendation:** **(b) the `HKCU…\Run` registry value**, written with one `windows-rs`
registry call (`RegSetValueExW`), with **migration logic that removes the legacy
`DiscordAutoRPC.lnk` and `DiscordAutoRPCWatcher.lnk`** from the Startup folder.
**Rationale:**
- It eliminates an entire class of the current bug (`B-1`, `T-008`): one mechanism, trivially
  idempotent, no COM, no `.lnk` binary format, no `powershell.exe` subprocess (the current
  approach shells out to `powershell -Command "$ws = New-Object -ComObject WScript.Shell…"`,
  which is slow and can be blocked by policy).
- Entries appear in **Settings → Apps → Startup**, which is what users actually check.
- ⚠️ Trade-off: the registry path requires the exe path to stay stable; the Startup-folder
  approach is identical in that regard, so no loss.
- ⚠️ If the app is ever MSIX/Store-packaged, the only supported mechanism is the
  `StartupTask` API. Not currently a goal, but record it.
**Risk:** A stale Run value pointing at an old install path. Mitigate by rewriting it on every
enable and cleaning up on uninstall/disable.
**Verify:** ⚠️ Confirm Windows 11 still surfaces HKCU Run entries in Startup settings (it does,
but verify on the target build).

---

### LD-18 — "Is Discord running?" detection
**Options:** (a) enumerate processes and match `discord*.exe` (current: `psutil.process_iter`);
(b) `CreateToolhelp32Snapshot` + `Process32NextW` via `windows-rs`;
(c) probe the Discord IPC named pipe `\\.\pipe\discord-ipc-{0..9}` with `WaitNamedPipeW`/`CreateFileW`;
(d) `sysinfo` 0.39.
**Recommendation:** **(c) pipe probe as the primary signal, with (b) as a fallback/diagnostic.**
**Rationale:** The question the app actually needs answered is *"can I talk to Discord?"*,
not *"is a process named discord.exe alive?"*. Probing the IPC pipe answers the real question,
is O(1), avoids walking the process table every 5 seconds, and cannot false-positive on a
crashed-but-alive Discord. This is a genuine design improvement over the current implementation
and directly supports BC-25.
**Risk:** Discord's pipe index and naming are unofficial/undocumented; they have been stable
for years but could change. Therefore: probe the pipe **and** keep the process-list check as a
secondary heuristic, and treat "connected successfully" as the ultimate truth.
**Verify:** ⚠️ Test with Discord in each of its channels (stable/PTB/Canary/Development) and
with Discord closed-but-zombie.

---

### LD-19 — Update checking and self-update
**Options:** (a) `windows-rs`/`ureq` GET of `api.github.com/repos/.../releases/latest` +
compare versions (current `updater.py`); (b) `self_update` 1.3 (MIT, 12.5M downloads) —
check **and** download/replace; (c) `tauri-plugin-updater` if Option C.
**Recommendation:** **Phase 1: (a) — port `updater.py` exactly** (notify-only, open the release
page). **Phase 2 (optional, later): (b) `self_update`.**
**Rationale:**
- The current contract (BC-26) is "notify". Introducing unattended self-update in the same
  release as a full language rewrite compounds risk enormously — if the updater misfires, users
  cannot recover.
- **Version comparison is currently broken and must be fixed:** `updater.check_for_updates()`
  tests `if tag and tag != __version__.lstrip("v")` — a pure string *inequality*, not a
  version comparison. Consequences of porting it verbatim: it flags an "update" for an
  **older** release, and — because `__version__` is `"0.1.0-beta"` while release tags are
  clean (e.g. `"0.1.0"`) — it **also flags an update when the user is already on the latest
  version**. Port this as a real semver comparison using the `semver` crate, and record the
  behavior change (users who previously saw a spurious update banner will stop seeing it).
- `self_update` supports GitHub Releases and can replace a running exe on Windows via a
  rename/relaunch dance, but "cannot overwrite a running .exe" must be handled explicitly.
**Risk:** `self_update`'s Windows replace path + SmartScreen on the new binary. If we self-update,
the downloaded binary must be **signed**, or every update will be blocked/warned.
**Verify:** ⚠️ Add a test proving `0.2.0 > 0.10.0` etc. (string comparison would get this wrong).

---

### LD-20 — Error handling policy
**Recommendation:** `thiserror` 2.x for library-ish error enums in the engine crate
(`DetectorError`, `IconError`, `PresenceError`, `ConfigError`), `anyhow` 1.x only in the binary
crate / top-level orchestration where context strings are more useful than types.
**Rationale:** Replaces Python's broad `except Exception:` (see `presence.py`'s
`except (InvalidID, BrokenPipeError, Exception)` and `detector.py`'s
`except (…, Exception)`) with explicit variants. Each failure mode currently swallowed should
become either a handled case or a `tracing::warn!` with context.
**Rule:** the poll loop must **never** panic or exit. Every iteration is wrapped so that one
bad app can't kill presence updates (preserving the current resilience).
**Risk:** Over-engineering error types for a 3k-line app. Keep enums small.

---

### LD-21 — Windows manifest, DPI, subsystem, and embedded resources
**Decisions:**
- `#![windows_subsystem = "windows"]` for release builds;
  `#![cfg_attr(debug_assertions, windows_subsystem = "console")]` for dev — you want logs in a
  terminal while developing.
- Embed the app icon and version metadata via **`winresource` 0.1** in `build.rs` (replaces
  PyInstaller's `--icon`).
- **Add an application manifest** the Python build never had:
  - `<dpiAwareness>PerMonitorV2</dpiAwareness>` — the settings window will otherwise be blurry on
    scaled displays (Qt handled this implicitly).
  - `supportedOS` GUIDs for Windows 10/11 (affects version-reporting APIs).
  - `longPathAware` (optional, harmless, helps logging paths).
  - **Do not** request `requireAdministrator` — the app must run unelevated (LD-07 handles
    elevated targets gracefully).
**Rationale:** These are silent quality differences that only show up on real machines, and
they're cheap to get right once.
**Risk:** A malformed manifest makes the exe fail to launch with no console output — a
frustrating failure mode. Verify with `mt.exe`/`sigcheck` if available.

---

### LD-22 — Binary size, packing, and CRT linking
**Decisions:**
- Build with `--release`, `lto = "fat"`, `codegen-units = 1`, `panic = "abort"`,
  `strip = "symbols"` in the release profile.
- **Do not use UPX.** The Python spec sets `upx=True`; UPX-packed binaries are a well-known
  trigger for antivirus heuristics and for `self_update`'s replace step. Given we're chasing
  SmartScreen/VirusTotal trust, dropping UPX is the right trade even at ~2× size.
- Prefer **`+crt-static`** (static MSVC runtime) so the exe has no VC++ Redistributable
  prerequisite. ⚠️ Verify it doesn't break the GUI stack (historically fine for egui/winit).
- ⚠️ **Do not assume the "5 MB Rust GUI app" folklore.** Measure. Expected ranges to validate:
  engine-only crate a few MB; egui app ~10–20 MB; Tauri exe smaller but **plus** a WebView2
  dependency. Compare apples-to-apples against the current PyInstaller artifact.
**Rationale:** Size and cold start are two of the main reasons to do this port at all, so they
should be *measured claims* in the final decision, not vibes.

---

### LD-23 — Data directory & user-state migration
**Decision:** Reproduce `config.get_data_dir()` semantics **exactly** (D-014) — do **not**
"fix" it to `dirs::config_dir()`.
**Rationale:** Changing the location silently orphans every existing user's `config.json`,
`icon_cache.json`, and `ignore_list.json`. Use `dirs` 7 only for `%APPDATA%` resolution.
**Additional requirement:** resolve the data dir **once, lazily, and propagate it explicitly**
(e.g. via a `Paths` struct passed into the engine) instead of re-deriving it at module import
in three places, which is the current design's sharpest edge (`detector._BASE_DIR`,
`icons._CACHE_PATH` captured at import time).
**Risk:** A silent split-brain where the GUI writes one file and the engine reads another.
Mitigate with a single `Paths` instance created in `main` and passed down; add a unit test.

---

### LD-24 — Version single-sourcing
**Decision:** The version lives in **`Cargo.toml`'s `[package] version`** only, and is read at
compile time via `env!("CARGO_PKG_VERSION")` everywhere (tray label, update check, logging
header). Generate the release tag from it in CI.
**Rationale:** Structurally fixes `B-3`. Also: derive the GitHub release tag as `v{VERSION}`,
and have a CI step assert that the tag matches `Cargo.toml` and fail the build if not.

---

### LD-25 — Testing strategy and Python-parity golden tests
**Decisions:**
- `cargo test` for pure logic. Highest-value targets, in order: `context` parsers
  (22 browser platforms + Office + IDE + media), `resolve_display_name` /
  `_clean_display_name`, `resolve_tagline` precedence, `is_ignored` / `is_incognito`,
  config round-trip + defaults merge, presence dedupe/rate-limit (with a mock IPC trait),
  and the semver comparison from LD-19.
- **Golden fixtures generated from the Python implementation** — the single best de-risking
  tool for this port. Write a small Python script that emits
  `(exe_name, window_title) → tagline` for a few hundred curated inputs, commit the JSON, and
  make the Rust test assert byte-equality. This turns "did we port the heuristics correctly?"
  into a mechanical check.
- `insta` snapshot tests for the title parsers.
- Explicitly **no** tests that require Discord to be running, a network, or a real foreground
  window — keep the engine testable by injecting a trait (`ForegroundSource`, `Uploader`,
  `Clock`) so tests don't depend on wall-clock or the desktop.
**Rationale:** The Python version has **zero** tests (`B-7`), so this port is also the moment
the project becomes verifiable. Recording the *current* behavior as fixtures means we prove
parity rather than assume it.

---

### LD-26 — CI/CD, release, and code signing
**Decisions:**
- `windows-latest` runner, `cargo build --release --target x86_64-pc-windows-msvc`,
  `cargo test`, and `cargo fmt --check` + `clippy -D warnings`.
- Release on `v*` tag (unchanged trigger): build the exe, zip it with `config.example.json`,
  `LICENSE`, `README.md`, attach to a **prerelease** GitHub Release (preserves D-019).
- **Code signing is the new open cost.** An unsigned binary that users download via a browser
  will hit SmartScreen. If `self_update` (LD-19 Phase 2) is ever adopted, signing becomes
  **mandatory**. Options: Azure Trusted Signing (cheapest ongoing), an OV certificate, or a
  free-tier approach with `sigstore`-style attestations (which do **not** satisfy SmartScreen).
  ⚠️ This needs a budget decision from the owner — see §11 Q5.
- Publish provenance: `cargo auditable`/SHA-256 checksums in the release notes so users can
  verify the download without a certificate.

---

### LD-27 — Repository layout, crate boundaries, and versioning
**Recommendation:** A Cargo **workspace inside the existing repo** (or a new repo — see §11 Q6):

```
/                     # existing repo root (Python docs remain during migration)
├── Cargo.toml        # [workspace] members = ["crates/*"]
├── rust-toolchain.toml
├── crates/
│   ├── autorpc-engine/   # NO UI deps. detector, context, icons, presence, config, updater
│   │   ├── src/lib.rs    #    typed public API + traits for testability
│   │   └── src/win/      #   win32: foreground, title, pe, icons, mutex/event, registry
│   └── autorpc-app/      # thin: main(), event loop, tray, windows/dialogs, wiring
└── ...
```

**Rationale:**
- The engine crate boundary is what makes the GUI decision reversible (LD-03) and the engine
  unit-testable without a desktop session.
- Keeping Python sources in place during migration lets us run both builds side by side and
  diff behavior, and keeps `git bisect`/history useful. Retention policy: keep `python/` on a
  tag or an `archive/python` branch once Rust reaches parity; do not delete the last Python
  release tag.
- **Versioning:** ship the port as **`0.2.0`** (not `1.0.0`) — the config/UX are compatible but
  the implementation is new, and it keeps the beta framing honest. Reserve `1.0.0` for
  "feature-complete + signed + self-updating".
- **Do not** rename the mutex/event (LD-16) or the data files; do consider renaming the
  `autorpc.log` logger targets from `autorpc.<module>` to `autorpc::<module>` for idiomatic
  `tracing` targets, and note the cosmetic log-format change.

---

### LD-28 — Scope: what counts as "parity"
**Decisions:**
- **Fix, don't port, the duplicated built-in tagline table** (`B-6`): one source of truth for
  built-in taglines, with user overrides layered on top. This changes the *implementation*
  without changing user-visible behavior.
- Drop `whitelist_only`'s hidden-ness: it's in config but absent from the GUI. Decide whether to
  surface it (§11 Q4) rather than porting an invisible setting.
- Keep the on-disk tagline/override schema identical so `config.json` migrates untouched.
- Treat `poll_interval` as GUI-exposed or explicitly documented as config-only (§11 Q4).
- **Preserve the 27-entry browser platform list, the keyword table, and the ignore defaults
  verbatim.** These are the accumulated "product knowledge" of the project; re-deriving them
  would be a regression even if the code got prettier.

---

## 6. File-by-file port map

| Python | Rust destination | Difficulty | Notes |
|---|---|---|---|
| `context.py` (320 L) | `engine::context` | **Easy** | Pure functions + regex. Use the `regex` crate. Biggest single win from golden tests. |
| `detector.py` `resolve_display_name`, `_clean_display_name`, `_CATEGORY_SUFFIX_REGEX` | `engine::naming` | Easy | Port regex verbatim. |
| `detector.py` `resolve_tagline`, `_BUILTIN_TAGLINES`, `_KEYWORD_TAGLINES` | `engine::taglines` | Easy | Fix `B-6` here. |
| `detector.py` `is_ignored`, `is_incognito`, ignore-list I/O | `engine::rules` | Easy | Keep `%SystemRoot%` check. |
| `detector.py` `Detector` state machine | `engine::detector` | Medium | Debounce/idle state machine; needs an injectable clock for tests. |
| `detector.py` `_get_foreground_app` | `engine::win::foreground` | Medium | `unsafe`; LD-07. |
| `context`+`detector` title retrieval | `engine::win::window_text` | Medium | LD-08 timeout version. |
| `icons.py` (447 L) | `engine::icons` + `engine::win::icon_extract` | **Hard** | `unsafe` GDI; LD-10/11. Byte-compare results. |
| `icons.py` uploads | `engine::upload` | Easy | `ureq`; data-driven host table. |
| `presence.py` (192 L) | `engine::presence` | Medium | Dedupe + rate limit + start times; wrap `discord-rich-presence` behind a trait (BC-08/BC-10). |
| `config.py` `DEFAULT_CONFIG`, load/save/validate | `engine::config` | Easy | serde + atomic write + unknown-key preservation (LD-14). |
| `config.py` `get_data_dir` | `engine::paths` | Easy | Must match D-014 exactly (LD-23). |
| `config.py` autostart | `engine::autostart` | Easy | Registry (LD-17) + legacy cleanup. |
| `main.py` logging | `app::logging` | Easy | `tracing` + size rotation + UI layer (LD-15). |
| `main.py` `JsonReloader` (30s) | `engine::config::reload` | Easy | Timer-based; or `notify` to watch the file (⚠️ adds a dep — probably not worth it). |
| `main.py` mutex + wake event | `engine::win::single_instance` | Easy | Same names (LD-16). |
| `main.py` `_is_discord_running` | `engine::discord::detect` | Easy | Pipe probe (LD-18). |
| `main.py` `_poll_loop` state machine | `engine::runtime` (worker thread) | **Medium-hard** | The orchestration + dormant/auto-close logic is the subtlest control flow in the app (BC-24/BC-25). Have it emit typed events. |
| `gui.py` QSS theme | `app` theme constants | Easy (egui) / Easy (CSS) | egui `Visuals`; or a CSS file for Tauri. |
| `gui.py` onboarding wizard | `app::ui::onboarding` | Medium | Form + validation port. |
| `gui.py` quick-rename dialog | `app::ui::rename` | Easy | Two text fields. |
| `gui.py` settings window (5 tabs) | `app::ui::settings` | **Hard** | The bulk of the GUI work: 3 tables + a list + spinners/checkboxes + add/delete rows. |
| `gui.py` live terminal + export/copy/clear/cache-reset | `app::ui::log_view` | Medium | Monospace auto-scrolling view + `rfd` save dialog (LD-03). |
| `main.py` tray menu (7 items, dynamic labels) | `app::tray` | Medium | `tray-icon`; dynamic relabel before show (LD-04). |
| `updater.py` (44 L) | `engine::updater` | Easy | semver fix (LD-19). |
| `watcher.pyw` | **delete** | — | See §8. |

---

## 7. Phased migration plan

Each phase ends at a **usable checkpoint** with a stated exit criterion. Do not proceed on a
failed exit criterion.

### Phase 0 — Decisions & spikes (2–4 days, no production code)
- Resolve the owner questions in §11 (especially GUI, licensing, signing budget, Windows 10).
- **Spike S-1 (critical):** a throwaway ~200-line app that proves the riskiest integration:
  tray icon + a settings window + a worker thread pushing events + a tray "Quit". Do it in
  egui **and** in Tauri if time allows; time-box each to one day.
- **Spike S-2:** icon extraction — extract a 256px icon from one exe via `windows-rs`,
  PNG-encode it, and byte/size-compare against the Python output.
- **Spike S-3:** foreground window + elevated-process exe path + hung-window title timeout.
- **Exit criterion:** a written choice of GUI framework, with the spike code as evidence, and
  a decision entry drafted for `DECISIONS.md`.

### Phase 1 — Workspace + engine skeleton
- Create the workspace and `autorpc-engine` with typed `Config`, `AppInfo`, `Paths`,
  `TrayEvent` types; wire `tracing`; implement `paths` and `config` (incl. atomic write).
- **Exit criterion:** `cargo test` round-trips the existing `config.example.json` byte-for-byte
  (modulo formatting) and unknown keys survive.

### Phase 2 — Pure logic + golden parity
- Port `context`, `naming`, `taglines`, `rules`; generate the Python golden fixtures first.
- **Exit criterion:** all golden fixtures pass; `is_ignored`/`is_incognito` match Python on a
  table of ~50 cases.

### Phase 3 — Win32 + network
- `foreground`, `window_text`, `pe version`, `icon_extract`, `upload`, `discord detect`,
  `single_instance`, `autostart`.
- **Exit criterion:** a headless CLI mode (`autorpc --probe`) that, with no UI, prints the
  resolved app/tagline/icon-URL for the current foreground window — directly comparable
  side-by-side with `python main.py` behavior.

### Phase 4 — Presence + runtime
- `presence` (dedupe/rate-limit/timers behind a trait) and the worker-thread runtime with
  dormant + `auto_close_with_discord` logic.
- **Exit criterion:** the CLI probe actually sets a live presence on a real Discord client,
  and the 15s rate limit + smooth timer are observed; killing/restarting Discord recovers.

### Phase 5 — GUI shell + parity UI
- Tray menu, onboarding wizard, settings (5 tabs), rename dialog, log terminal, update banner.
- **Exit criterion:** §12 checklist fully ticked, side-by-side with the Python build.

### Phase 6 — Release, migration, cleanup
- CI for the Rust build; `v0.2.0` prerelease; README rewrite (build-from-source becomes
  `cargo build --release`); document the upgrade path ("keep your `config.json`"); delete
  `watcher.pyw` + the `.bat` files; archive the Python sources.
- **Exit criterion:** a fresh Windows VM installs the Rust release, completes onboarding, shows
  a presence, autostarts, and survives an upgrade preserving its config.

---

## 8. What NOT to port

| Item | Reason |
|---|---|
| `watcher.pyw` | Already superseded by `--startup` dormant mode (D-005) and is the root cause of the `B-1` double-autostart bug. **Delete it**, don't port it. |
| `enable_autostart.bat` / `disable_autostart.bat` | Shell wrappers around a shortcut-creation mechanism we're replacing with a registry value (LD-17). Delete. |
| `pystray` | Superseded by `tray-icon`; the pystray approach is what caused D-004. |
| `JsonReloader`'s untyped `dict` shared state | Replace with a typed struct. The 30-second reload *behavior* stays; the `dict` does not. |
| `main.py`'s redundant `CONFIG_PATH`/`BASE_DIR` rebindings and unused imports (`B-8`) | Dead code. |
| `icons.py`'s docstring describing catbox as default (`B-4`) | Docs bug; write accurate ones. |
| The duplicated built-in tagline table (`B-6`) | Collapse to one source (LD-28). |
| `config.py`'s non-atomic `save_config` | Replace with temp+rename (LD-14). |
| `updater.py`'s `tag != __version__` "comparison" | Replace with real semver (LD-19). |
| `presence.py`'s `except (…, Exception)` catch-alls | Replace with typed errors (LD-20). |
| The `whitelist_only` feature *as an invisible setting* | Either surface it in the GUI or document it as config-only (§11 Q4). |

---

## 9. Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | GUI parity takes far longer than estimated | High | High | Engine-first ordering; Spike S-1 before committing; consider Option B if schedule is hard. |
| R-2 | `unsafe` GDI icon code produces wrong/corrupt images | Medium | Medium | Spike S-2; byte-compare against Python; mirror the existing DIB/BGRA comments verbatim. |
| R-3 | Tray/event-loop integration fights the GUI framework (the D-004 class of bug) | Medium | High | Spike S-1; `tray-icon` is purpose-built for this; fall back to Tauri which owns the integration. |
| R-4 | Licence contamination (GPL/AGPL) | Low | High | Reject `slint` and `win-icon-extractor`; add `cargo deny`/`cargo licence` to CI to fail on non-MIT/Apache/BSD deps. |
| R-5 | Unsigned binary → SmartScreen/AV friction; worse if UPX is used | Medium | Medium | No UPX; publish checksums; budget for signing (§11 Q5). |
| R-6 | Users lose config/data during migration | Low | High | Keep D-014 semantics exactly; LD-23 single `Paths`; test upgrade-in-place on a VM. |
| R-7 | Discord IPC schema/pipe discovery drift | Low | High | Wrap the RPC crate behind a trait; pin the version; keep `discord-presence` as a fallback candidate. |
| R-8 | `self_update` (if adopted) corrupts installs | Medium | High | Defer to Phase 1 of LD-19 (notify-only), require signing first, test the replace dance on a VM. |
| R-9 | MSRV/pre-1.0 churn in egui breaks the build | Medium | Low | Pin exact versions; upgrade deliberately. |
| R-10 | Owner can't maintain Rust long-term → project stalls half-migrated | Medium | High | Decide before Phase 1; Option B leaves a working product at every step, which is the safety net if Option A stalls. |
| R-11 | Anti-cheat false positives from inspecting game processes | Low | High | Only `GetForegroundWindow` + `PROCESS_QUERY_LIMITED_INFORMATION`; never inject/read memory; document it. |
| R-12 | AV flags the *new* binary as suspicious on first release (low reputation) | Medium | Medium | Ship with signing, checksums, and a VirusTotal-cleared build; keep the Python release available for one cycle. |

---

## 10. Effort estimate

Rough engineer-days for a competent developer who knows Windows APIs but is new to Rust
(or knows Rust but is new to Win32). ⚠️ Estimates only — Spike S-1 should recalibrate them.

| Phase | Scope | Days |
|---|---|---|
| 0 | Decisions + spikes S-1/S-2/S-3 | 2–4 |
| 1 | Workspace, types, config/paths | 2–3 |
| 2 | Pure logic + golden fixture harness | 3–5 |
| 3 | Win32 + upload (the `unsafe` zone) | 4–6 |
| 4 | Presence + runtime state machine | 3–4 |
| 5 | GUI: tray, onboarding, 5-tab settings, log terminal | 8–15 |
| 6 | CI, release, docs, cleanup, VM verification | 3–5 |
| **Total (Option A)** | | **25–42** |
| **Total (Option B, engine only)** | Phase 0–4 + PyO3 packaging instead of 5–6 | **14–22** |
| **Total (Option C)** | Like A but GUI in HTML/CSS/JS; Tauri removes LD-04/16/17/19 integration work | **22–35** |

Add ~1.3–1.5× for a first-time Rust developer, and ~20% for polish (icons, spacing, theming,
DPI, edge cases in the tables).

---

## 11. Open questions needing an owner decision

| # | Question | Why it matters | Default if unanswered |
|---|---|---|---|
| Q1 | Must **Windows 10** still be supported, or is Win 11 only acceptable? | Affects WebView2 assumption (Option C), manifest GUIDs, and testing matrix. | Support both (status quo). |
| Q2 | **Option A (native egui), B (keep Python GUI), or C (Tauri)?** | The dominant cost and risk. | Do Spike S-1, then decide; lean A. |
| Q3 | Is a **WebView2 runtime dependency** acceptable? | Only if Option C. Windows 11 ships it; stripped Win 10 may not. | No. |
| Q4 | Should `whitelist_only` and `poll_interval` become **visible in the GUI**? | Decides whether parity means "same GUI" or "same GUI + surfaced settings". | Port as-is (stay hidden), note as `TASKS.md` follow-up. |
| Q5 | Is there a **budget for code signing** (Azure Trusted Signing / OV cert)? | Determines whether self-update (LD-19 Phase 2) is viable and how much SmartScreen friction users see. | No budget → notify-only updates + published checksums. |
| Q6 | **Same repo** (workspace alongside Python) or a **new repo**? | Affects history, CI, issue tracker, and the migration's reversibility. | Same repo, workspace, Python archived at parity. |
| Q7 | Is **`0.2.0`** the right version for the port, or does it deserve `1.0.0`? | Sets user expectations; `1.0.0` implies stability commitments. | `0.2.0`. |
| Q8 | How long must the **Python release stay supported** after the Rust release? | Determines whether we can delete Python sources and whether we maintain two builds. | One release cycle, Python kept as a known-good fallback. |
| Q9 | Do you want **tests added at all** (LD-25), given the project has none today? | A port without tests can't prove parity; tests also slow initial delivery. | Yes — golden fixtures are non-negotiable for the title parsers. |
| Q10 | Should the **README/`AGENTS.md`/`DECISIONS.md`/`STATE.md`/`TASKS.md` system** be restructured for a Rust repo (new conventions, new decisions numbered D-020+)? | The docs are the project's memory; the port changes conventions. | Yes — after Phase 1, add Rust conventions to `AGENTS.md` and start a new decision-entry block. |

---

## 12. v1.0 acceptance criteria

The Rust build is at parity when, side by side with the Python build on the **same machine**:

**Engine**
- [ ] Every item in §2.1 (BC-01…BC-28) is demonstrably reproduced.
- [ ] `config.json`, `icon_cache.json`, `ignore_list.json` are interchangeable between builds.
- [ ] Golden fixtures from §LD-25 pass (`context`, naming, taglines, rules).
- [ ] The 15s rate limit and smooth second-by-second timer are observed live (BC-08/BC-09).
- [ ] Discord focused → the previously confirmed app is still shown (BC-04).
- [ ] An elevated process and a hung window are both handled without stalling the poll loop.

**GUI**
- [ ] Tray menu items and their dynamic relabeling match the current menu.
- [ ] Onboarding wizard, rename dialog, and all 5 settings tabs are functionally equivalent.
- [ ] Live log terminal streams, copies, exports, clears, and resets the icon cache.
- [ ] The dark theme reads as the same product (Discord palette).
- [ ] No blur on a 150%-scaled display (LD-21).

**Distribution**
- [ ] One exe, no console window, no VC++ Redist prerequisite, correct embedded icon/version.
- [ ] Cold start is measurably faster than the PyInstaller onefile build (report the number).
- [ ] Single-instance behavior works, **including** cross-version (Python running + Rust launch).
- [ ] Autostart works via exactly one mechanism; legacy Startup shortcuts are cleaned up.
- [ ] `v0.2.0` prerelease published by CI from a git tag; checksums in the release notes.

**Migration**
- [ ] A user upgrading from Python to Rust keeps their config, cache, and ignore list.
- [ ] `watcher.pyw` and the `.bat` files are gone; `B-1…B-8` are closed or explicitly re-scoped.

---

## Appendix A — dependency license matrix

| Crate | Version | License | Verdict for an MIT project |
|---|---|---|---|
| `discord-rich-presence` | 1.1.0 | MIT | ✅ |
| `discord-presence` | 3.2.0 | MIT | ✅ (alternative) |
| `windows` | 0.62.2 | MIT OR Apache-2.0 | ✅ |
| `tray-icon` | 0.26.1 | MIT OR Apache-2.0 | ✅ |
| `eframe` / `egui` | 0.37.0 | MIT OR Apache-2.0 | ✅ |
| `iced` | 0.14.0 | MIT | ✅ |
| `tao` | 0.37.1 | Apache-2.0 | ✅ |
| `winit` | 0.30.13 | Apache-2.0 | ✅ |
| `tauri` | 2.12.4 | Apache-2.0 OR MIT | ✅ (⚠️ WebView2 runtime dep) |
| **`slint`** | 1.18.1 | **GPL-3.0-only** OR Slint royalty-free/commercial | ❌ **Reject** — would force the distributed binary to GPL-3.0 |
| `self_update` | 1.3.1 | MIT | ✅ |
| `ureq` | 3.4.2 | MIT OR Apache-2.0 | ✅ |
| `reqwest` | 0.13.5 | MIT OR Apache-2.0 | ✅ (pulls `tokio`) |
| `image` | 0.25.10 | MIT OR Apache-2.0 | ✅ |
| `serde` / `serde_json` | 1.0.x | MIT OR Apache-2.0 | ✅ |
| `tracing-appender` | 0.2.5 | MIT | ✅ |
| `interprocess` | 2.4.6 | 0BSD OR Apache-2.0 | ✅ (optional) |
| `single-instance` | 0.3.3 | MIT | ✅ (⚠️ unmaintained since 2021 — prefer named mutex) |
| `auto-launch` | 0.6.0 | MIT | ✅ (optional) |
| `rfd` | 0.17.2 | MIT | ✅ |
| `opener` | 0.9.0 | MIT OR Apache-2.0 | ✅ |
| `sysinfo` | 0.39.6 | MIT | ✅ (⚠️ heavy; probably unnecessary) |
| `dirs` | 7.0.0 | MIT OR Apache-2.0 | ✅ |
| `clap` | 4.6.7 | MIT OR Apache-2.0 | ✅ |
| `zip` | 9.0.5 | MIT | ✅ (CI packaging) |
| `winresource` | 0.1.34 | MIT | ✅ |
| `windows-icons` | 0.4.0 | MIT | ⚠️ Low adoption (17k dl) — prefer direct `windows-rs` |
| **`win-icon-extractor`** | 0.3.0 | **AGPL-3.0-only** | ❌ **Reject** |
| `notify-rust` | 4.18.2 | — | N/A (no desktop notifications needed) |

**Recommendation:** add `cargo-deny` with an allow-list of `MIT`, `Apache-2.0`,
`MIT OR Apache-2.0`, `BSD-3-Clause`, `0BSD`, `Unicode-3.0` so this class of mistake fails CI.

---

## Appendix B — verified crate data

Read from crates.io on **2026-10-18**. "Updated" is the crate's last publish date.

| Crate | Latest | Updated | Downloads | MSRV | Edition |
|---|---|---|---|---|---|
| `discord-rich-presence` | 1.1.0 | 2026-01-26 | 661,724 | — | 2018 |
| `discord-presence` | 3.2.0 | 2026-01-20 | 98,364 | 1.82.0 | 2021 |
| `discord-sdk` | 0.4.0 | 2024-12-17 | 134,161 | — | — |
| `tray-icon` | 0.26.1 | 2026-10-07 | 35,895,848 | 1.90 | 2021 |
| `windows` | 0.62.2 | 2025-10-06 | 366,882,084 | 1.82 | 2021 |
| `egui` / `eframe` | 0.37.0 | 2026-10-15 | 20,904,393 (eframe) | 1.95 | 2024 |
| `iced` | 0.14.0 | 2025-12-07 | 3,015,180 | 1.88 | 2024 |
| `slint` | 1.18.1 | 2026-09-21 | 2,063,115 | 1.92 | 2024 |
| `tauri` | 2.12.4 | 2026-10-14 | 37,245,012 | 1.90 | 2024 |
| `tao` | 0.37.1 | 2026-09-26 | 39,538,248 | 1.85 | 2021 |
| `winit` | 0.30.13 (0.31.0-beta.3) | 2026-09-04 | 58,933,695 | 1.70.0 | 2021 |
| `self_update` | 1.3.1 | 2026-10-17 | 12,556,825 | 1.88 | 2024 |
| `reqwest` | 0.13.5 | 2026-09-08 | 810,685,983 | 1.85.0 | 2021 |
| `ureq` | 3.4.2 | 2026-09-13 | 232,422,597 | 1.85 | 2024 |
| `tokio` | 1.53.3 | 2026-10-13 | 1,076,818,523 | — | — |
| `image` | 0.25.10 | 2026-03-10 | 217,423,150 | 1.88.0 | 2021 |
| `serde` | 1.0.229 | — | 1,047M+ | 1.56 | 2021 |
| `serde_json` | 1.0.154 | 2026-10-11 | 1,450,577,531 | — | — |
| `sysinfo` | 0.39.6 | 2026-07-09 | 224,158,526 | 1.95 | 2024 |
| `interprocess` | 2.4.6 | 2026-10-16 | 16,133,077 | 1.75 | 2021 |
| `tracing-appender` | 0.2.5 | 2026-04-17 | 130,776,617 | 1.63.0 | 2018 |
| `dirs` | 7.0.0 | 2026-09-05 | 367,470,059 | — | — |
| `clap` | 4.6.7 | 2026-09-14 | 1,237,756,994 | 1.85 | 2024 |
| `rfd` | 0.17.2 | 2026-01-12 | 36,407,485 | — | 2021 |
| `opener` | 0.9.0 | 2026-09-29 | 38,506,243 | 1.77 | 2021 |
| `auto-launch` | 0.6.0 | 2026-01-10 | 6,914,275 | — | 2021 |
| `single-instance` | 0.3.3 | 2021-12-16 | 958,468 | — | — |
| `winresource` | 0.1.34 | 2026-10-12 | 5,700,560 | — | 2021 |
| `windows-icons` | 0.4.0 | 2026-08-06 | 17,099 | — | 2024 |
| `win-icon-extractor` | 0.3.0 | 2026-09-29 | 905 | 1.70 | 2021 |
| `pelite` | 0.10.0 | 2022-11-04 | 927,309 | — | — |
| `zip` | 9.0.5 | 2026-10-17 | 304,788,390 | 1.88 | 2024 |
| `windows-version` | 0.100.0 | 2026-09-03 | 27,957,914 | — | — |

**Notes**
- `tokio` is listed only to quantify the cost of LD-02's "avoid an async runtime" choice.
- `windows` 0.62.2 has been the newest stable since 2025-10-06 — roughly a year without a
  release. ⚠️ Check `windows-rs`'s repo for a pending 0.63 before pinning, and note that these
  crates use a large feature-flag surface (`Win32_Foundation`, `Win32_UI_WindowsAndMessaging`,
  `Win32_UI_Shell`, `Win32_Graphics_Gdi`, `Win32_System_Threading`,
  `Win32_System_ProcessStatus`, `Win32_Storage_FileSystem`).

---

## Appendix C — Win32 API surface required

Every OS call the Rust version needs, and where it comes from today.

| Purpose | Win32 API | Python today |
|---|---|---|
| Foreground window | `GetForegroundWindow` | `win32gui.GetForegroundWindow` |
| Window → PID | `GetWindowThreadProcessId` | `win32process.GetWindowThreadProcessId` |
| PID → image path | `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `QueryFullProcessImageNameW` | `psutil.Process(pid).exe()` |
| Window title (timeout-safe) | `GetWindowTextLengthW` + `SendMessageTimeoutW(WM_GETTEXT)` | `win32gui.GetWindowText` |
| PE version info | `GetFileVersionInfoSizeW`, `GetFileVersionInfoW`, `VerQueryValueW` | `win32api.GetFileVersionInfo` |
| Icon @256 | `PrivateExtractIconsW`, `DestroyIcon` | same, via `ctypes` |
| Icon fallback | `ExtractIconExW` | `win32gui.ExtractIconEx` |
| Icon → bitmap | `GetIconInfo`, `CreateCompatibleDC`, `CreateDIBSection`, `SelectObject`, `DrawIconEx`, `GetBitmapBits`, `DeleteObject`, `ReleaseDC` | same, via `win32ui`/`ctypes` |
| Process handle cleanup | `CloseHandle` | implicit |
| Single instance | `CreateMutexW`, `GetLastError`, `OpenEventW`, `SetEvent`, `CreateEventW`, `WaitForSingleObject`, `CloseHandle` | `win32event`, `win32api` |
| Discord pipe probe | `CreateFileW` / `WaitNamedPipeW` on `\\.\pipe\discord-ipc-{0..9}` | (not used — Python enumerates processes) |
| Discord process fallback | `CreateToolhelp32Snapshot`, `Process32FirstW`, `Process32NextW` | `psutil.process_iter` |
| Autostart | `RegOpenKeyExW`, `RegSetValueExW`, `RegDeleteValueW` | PowerShell + `WScript.Shell` COM |
| Legacy shortcut cleanup | `SHFileOperationW`/`DeleteFileW` on the Startup folder | `Path.unlink()` |
| Open log / URLs | `ShellExecuteW` (or the `opener` crate) | `os.startfile`, `webbrowser.open` |
| Modal file dialog (log export) | `IFileSaveDialog` (or `rfd`) | `QFileDialog` |
| Kill old process on update | — | N/A |

**Thread discipline (the D-004 rule, restated for Rust):** all window/message-pump and
tray-icon calls must happen on the thread that created them. Keep them on the main thread;
the worker thread communicates only through `Sender<TrayEvent>`.

---

*End of research. No code was modified. Next action: answer §11 Q1–Q6, then schedule Spike S-1.*
