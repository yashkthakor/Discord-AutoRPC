# GUI Handoff — React + Tauri rewrite of the Qt6 interface

**Audience:** the supervising agent (Claude) that owns this project's quality bar.
**Author of this doc:** the agent that built/reviewed the existing codebase.
**Status:** specification for handoff. **No code has been written.** The implementing
engineer/agent works *under* this document; it does not get to reinterpret it silently.

---

## 0. Your role, and how to use this document

You are the **supervisor**. You do not write production code. You:

1. **Approve or reject at gates** (§11). Nothing proceeds to the next gate without your sign-off.
2. **Enforce the contract** in §6 (IPC/config surface) and §10 (parity checklist).
3. **Own scope discipline** (§2). Feature creep is a rejection reason.
4. **Ask the owner** the questions you cannot answer yourself (§13).
5. **Demand evidence**, never accept "it works" — ask for the artifact (screenshot, log,
   test output, recording).

You must **read §4 before approving anything**, because §4 is the list of things that are
easy to silently lose in a UI rewrite. Losing one of them is a user-visible regression even
if the new UI looks nicer.

**Two rules you should enforce constantly:**

- **RULE-1 — Parity before polish.** A prettier UI that drops a checkbox is a *failure*, not
  a partial success. Every row of §4.7 must be accounted for as either **implemented**,
  **deliberately changed (with a `DECISIONS.md` entry)**, or **deliberately dropped (with an
  owner sign-off)**.
- **RULE-2 — No silent behavior changes.** The current app has *inconsistent* save semantics
  (§4.12, ID `SEM-*`). The rewrite may unify them, but only as an explicit, documented decision
  approved by the owner — not as an accident of whoever wrote the form first.

---

## 0.1 G0 decisions — **authoritative amendments**

> **These are owner-approved decisions issued after this handoff was written.** Where §0.1
> conflicts with any later section, **§0.1 wins**. Each amendment references its entry in
> `DECISIONS.md`; the G5 audit must show those references (§11).
>
> **G0 status:** closed for the items below. **Two questions still block G1: Q4 and Q5 (§13).**

| # | Decision | Amends / supersedes | Log |
|---|---|---|---|
| `A1` | Adopt the **macOS System Settings layout and component language inside a native Windows frame**. Native decorations retained. **No fake traffic lights, no custom titlebar in v1.** | refines §5.1, confirms §5.6 | `D-020` |
| `A2` | **No emoji anywhere**, and no glyph characters used as icons (`✓`, `⭐`): UI, copy strings, tray labels, toasts. | §5.8 + every emoji string quoted in §4 | `D-021` |
| `A3` | **No vibrancy, glass, or gradients in v1.** `backdrop-filter` rejected — it cannot blur the desktop behind the window, so it would be fake. Solid surfaces only. Mica optional later. | reverses §5.6's Mica recommendation | `D-022` |
| `A4` | **Light / Dark / System** appearance control, user-facing, in General. Default **System**, follows the OS live. **Reverses the §2 deferral and the §8.1 "dark-only is the brand" line.** | §2, §8.1 | `D-023` |
| `A5` | Appearance persists in **`ui_prefs.json`** in the data dir — **not** `config.json` (§6.1 stays frozen so the Python build is unaffected). Backend-written (`SEC-2`). Missing file ⇒ System. | §6.1, §7 | `D-024` |
| `A6` | The native frame follows the in-app choice via the window's `set_theme` (Light / Dark / None). | new | `D-025` |
| `A7` | **Token architecture:** every colour is a CSS variable; light on `:root`, dark under `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, and dark again under `:root[data-theme="dark"]`. Accent deliberately darker than stock Apple blue for contrast. | replaces §8.1 | `D-026` |
| `A8` | **No flash in either theme:** window starts hidden → backend paints the resolved theme colour → entry module sets `data-theme` **synchronously** before React renders → no inline script (`SEC-1`) → show after first paint. Theme switch is instant, with no colour transition. | refines `SH-4` / `PERF-2` | `D-027` |
| `A9` | **Type / icons / shape:** Inter bundled locally (no remote fonts; SF Pro is not licensed for non-Apple platforms), Cascadia Mono for logs; 20/15/13/12 scale, weights 400/500/600; one icon set at one stroke weight; 4px grid, 10px card / 6px control radii, 1px hairlines, shadows only on popovers and dialogs. Window min 820×560 with restored state, title **"Settings"**, ~680px centred content column. | §8.2, §8.3 | `D-028` |
| `A10` | **Tray icon legible on light *and* dark taskbars** (taskbar theme is independent of app theme). Multi-resolution `.ico`, normal + paused. | `TR-1`, `TR-2` | `D-029` |
| `A11` | Navigation is a **6-pane sidebar: Status, General, App Names, Taglines, Ignored Apps, Logs.** `Ctrl+1…6` and `Esc`. **The command palette and `Ctrl+K` are dropped.** | `SS-1`, `SS-3`, §5.9 | `D-030` |
| `A12` | **Autosave. There is no Save button.** Resolves `SEM-3` and `SEM-8`; drops `SS-2`. | `SS-2`, §4.12 | `D-031` |
| `A13` | **Control vocabulary:** `role="switch"` switches instead of checkboxes, number fields with steppers, segmented controls, grouped inset lists (label left, control right, description under the label). | §8.3 | `D-032` |
| `A14` | **Feedback:** a quiet **bottom-centre toast pill** with an Undo action (`aria-live="polite"`), inline validation, and dialogs **only** for destructive actions. Replaces all 8 `QMessageBox` calls. | `FB-1`…`FB-4` | `D-033` |
| `A15` | **Status is a full landing pane** (app icon, display name, resolved tagline, ticking timer, connection state + indicator, Pause/Resume, Rename, Ignore). The "why this tagline?" disclosure is **deferred**. | §5.3, answers Q9 | `D-034` |
| `A16` | **General pane composition**, including Appearance and an Advanced group (`poll_interval`, `whitelist_only`, `upload_host` + privacy disclosure, SteamGridDB key) and a destructive Reset with "export config first". | `G-8`…`G-12`, Q5 | `D-035` *(provisional — see Q5)* |
| `A17` | **List panes:** inset list with a filter field above and a `+` / `−` bar below; add via a small popover; delete via `−` and the `Delete` key, with an undo toast. **Normalization preserved verbatim** (lowercase + `.exe`). Recent-app suggestions and empty states. Taglines additionally: live preview, a 128-char counter that warns near the limit, built-ins as a read-only group, and the precedence one-liner. | `O-1`…`O-3`, `T-2`…`T-7` | `D-036` |
| `A18` | **The two ignore lists must be merged into one source of truth**, with migration of existing `ignore_list.json` entries. Built-in defaults and the `%SystemRoot%` skip are shown as a read-only group. **Must be resolved before G1.** | `I-5`, answers Q6, closes `RSK-6` | `D-037` |
| `A19` | **Logs pane (Console style):** search with highlight, minimum-level segmented control (Debug/Info/Warning/Error), follow toggle with "Jump to latest", Copy (visible lines), Export… (backend write via a native save dialog), Clear View (labelled so it is clear the file is not deleted), Reset Icon Cache (confirm + show count). `PERF-1` unchanged. The detection digest is **deferred**. | `L-2`…`L-6`, `L-11` | `D-038` |
| `A20` | **Onboarding is a 3-step Setup Assistant** in its own window: Welcome → Create the app in the Developer Portal → Paste the App ID + the two defaults-on toggles + **Verify connection**. Back/Continue. | `OB-13`, `OB-12` | `D-039` |
| `A21` | **Quick rename is a small standalone window** (native tray menus cannot anchor a popover) **and** the same component as a sheet on the Status pane. Not a blocking modal. | `R-1` | `D-040` |
| `A22` | **Tray uses the native menu**, plain-text labels, no emoji, with all `TR-1`…`TR-16` states and dynamic relabelling preserved. | `TR-1`…`TR-16`, resolves `RSK-1` | `D-041` |
| `A23` | **Gate additions** for G1 (both-theme token sheet + contrast table + wireframes), G2 (both-theme screenshots at three DPI scales, no flash, live System follow, persistence, taskbar legibility) and G5 (per-changed-ID → `DECISIONS.md` references). | §11 | `D-042` |

> **ID collision fixed:** the §12 risk register previously used `R-1`…`R-12`, colliding with
> §4.9's `R-1` (quick rename). Risk IDs are now **`RSK-1`…`RSK-12`**. The G0 note's reference to
> "`I-5`/`R-6`" means §4 `I-5` and **`RSK-6`** (two ignore lists).

---

## 1. Context: what exists today and what we're replacing

**Discord AutoRPC** (Windows-only, `0.1.0-beta`, MIT) watches the foreground window and
broadcasts the active app to Discord as a Rich Presence — extracted 256×256 icon, a
contextual tagline, and a live timer.

The **presence engine** — foreground detection (`detector.py`), window-title semantic parsing
(`context.py`), icon extraction/upload (`icons.py`), Discord RPC (`presence.py`), config
(`config.py`), updates (`updater.py`) — is **out of scope** for this handoff. It stays as-is
or gets swapped independently **behind the IPC seam** defined in §6.

**In scope:** everything the user *sees or clicks*.

| Today | Source of truth | Lines |
|---|---|---|
| Settings / onboarding / rename UI | `gui.py` (PyQt6) | 998 |
| Tray icon + context menu + lifecycle wiring | `main.py` | ~513 |
| Live log plumbing | `gui.py` (`QtLogHandler`) + `main.py` (`_setup_logging`) | ~60 |

PyQt6 is being replaced because of concrete architectural limits, not aesthetics:

| Qt6/PyQt6 limitation | Consequence today | What the replacement needs to do |
|---|---|---|
| Widget toolkit = desktop-native rendering; theming is a string stylesheet | `DISCORD_DARK_QSS` is 150 lines of CSS-like string with no design tokens, no composition, no animation | Real styling system: tokens → primitives → components |
| Tables/list widgets are imperative, no data model | Overrides/taglines/ignored lists are hand-rolled `setRowCount`/`setItem` loops with no sorting, filtering, or virtualization | Declarative, sortable, filterable, virtualized tables |
| Layout is manual box stacking | Fixed window sizes (`540×510`, `480×310`, `750×600`); doesn't adapt, doesn't remember size | Responsive, resizable, state-restoring windows |
| No animation/transition primitives | Everything snaps; no feedback on state change | Motion budget (§8.4) for state transitions only |
| Modal `exec()` blocks the whole app | `QMessageBox` after nearly every action; wizard and rename are app-blocking modals | Non-blocking feedback (toasts), modals only for destructive confirm |
| Text rendering is a fixed QSS font stack | No control over hierarchy, no variable fonts, weak DPI handling | Typographic scale + DPI-aware rendering (WebView2) |
| No accessibility layer | Screen readers see an unlabeled widget soup | Semantic HTML + ARIA via accessible primitives |
| Emoji used as icons (`⚙️ 🏷️ 🚫 📋 ❌ ⏸ ▶ ⭐ 💾 🧹 🔄 🌐 ✓`) | Renders differently per Windows font version; not themable, not scalable | A real icon set + consistent sizing |
| No way to preview/diagnose | Users can't see *what* is currently being broadcast from the UI | Live "Now Broadcasting" surface (§5.3) |

**The point of the rewrite is not "React is nicer."** It's that the current UI cannot express
the states the product actually has (live presence, connection status, detection diagnostics)
and cannot be made to feel responsive without fighting the toolkit.

---

## 2. Scope

### In scope
- Onboarding / first-run setup
- Settings window: 5 sections (General, App Names & Overrides, Taglines, Ignored Apps, Live Logs & Diagnostics)
- Quick rename of the active app
- Tray icon, tooltip, and context menu (all states)
- Update-available affordance
- Global feedback system (toasts, inline validation, destructive confirms)
- Live log streaming, filtering, copy, export, clear, cache reset
- Window/menu state restoration, keyboard shortcuts, accessibility
- The IPC contract between UI and engine (§6)

### Out of scope (do not touch, do not "improve")
- Detection/debounce/idle logic, tagline heuristics, icon extraction/upload, RPC semantics
- Windows-only assumption (no cross-platform abstraction)
- `watcher.pyw` and the `.bat` scripts — these are **legacy and should be deleted**, not
  reimplemented (they are the root cause of the double-autostart bug)
- The presence engine's language/runtime choice (see §3)

### Explicitly deferred (approve later, not now)
- Multi-language/localization (but keep strings extractable — §9.4)
- **~~Theme light mode~~ → now IN SCOPE: Light / Dark / System is required** (`A4` / `D-023`)
- Plugin/extension surface
- Presence history/statistics
- **Mica / vibrancy / glass window backdrops** (`A3` / `D-022`) — solid surfaces only in v1
- A custom titlebar / frameless window (`A1` / `D-020`)
- The "why this tagline?" disclosure on the Status pane (`A15` / `D-034`)

---

## 3. One decision you must lock before gate G1: where the engine lives

Tauri's backend is Rust. The engine today is Python. Three honest options:

| | Option A — Tauri shell + **Python engine as sidecar** | Option B — Tauri + **Rust engine** | Option C — WebView without Tauri |
|---|---|---|---|
| GUI | React/Tauri | React/Tauri | React (pywebview/WebView2) |
| Engine | Existing Python, unchanged | Full rewrite of `detector`/`context`/`icons`/`presence`/`config` | Existing Python |
| Seam | Rust ↔ Python over **stdio JSON-lines** (or authenticated localhost WS) | Rust in-process | Python ↔ JS directly |
| Time to a modern UI | **Fastest** | Slowest | Fast |
| Tray / single-instance / updater / autostart | Tauri plugins handle it | Tauri plugins handle it | Hand-rolled (weak tray story) |
| Ship size | Python + WebView2 (large, but no Qt) | Smallest | Python + WebView2 |
| Risk | **Low** — engine already works and is the tested part | High — engine is the tested part and you're rewriting it | Medium |
| Leaves frontend reusable later | ✅ yes | ✅ yes | ❌ no |

**Recommendation to put in front of the owner:** **Option A first.** It gets the modern UI
with the smallest blast radius, keeps the known-good engine, and — critically — the React
frontend and the IPC contract survive a later move to Option B untouched. Option B is a
separate, later decision that does not block this project.

**Why this matters to you as supervisor:** the choice determines whether the IPC seam is
*in-process* (cheap, synchronous, typed by the compiler) or *cross-process* (needs framing,
timeouts, lifecycle ownership, and crash handling). The **contract in §6 is written to be
identical in both**, so you can approve it now regardless — but you should require the owner
to answer §13 Q1 before G1, because Option A adds a hard requirement: *the UI must survive the
engine process dying and must be able to restart it* (§12, `RSK-2`).

⚠️ **Verified dependency facts** (crates.io, 2026-10-18; all `Apache-2.0 OR MIT` unless noted):
`tauri 2.12.4`, `tauri-plugin-single-instance 2.5.4`, `tauri-plugin-autostart 2.7.0`,
`tauri-plugin-updater 2.14.0`, `tauri-plugin-dialog 2.8.3`, `tauri-plugin-opener 2.7.2`,
`tauri-plugin-log 2.10.1`, `tauri-plugin-window-state 2.5.0`, `tauri-plugin-clipboard-manager 2.5.0`,
`tauri-plugin-shell 2.5.0`, `tauri-plugin-fs 2.7.1`, `muda 0.21.2` (menus),
`window-vibrancy 0.8.1`, `dirs 7.0.0`. Tauri's MSRV is **1.90**; `tauri-plugin-decorum` is
stale (2024) — do not depend on it.

---

## 4. Complete functionality inventory (the parity list)

> **This is your acceptance checklist.** Every item must be verified at gate G5.
> Columns: **ID** · what it does today · **MUST/MODERNIZE/DROP** · notes for the rewrite.

### 4.1 Application shell & lifecycle

| ID | Today (Qt) | Verdict | Notes for the rewrite |
|---|---|---|---|
| `SH-1` | Single `QApplication`, global stylesheet, app icon set once | MUST | One React app. Windows: the Settings window, a first-run onboarding window (`A20`), and a small quick-rename window (`A21`). **No tray popup window** — the tray menu is native (`A22`) |
| `SH-2` | Settings window is a **singleton** — re-opening raises/activates the existing one | MUST | Reopening from the tray must focus the existing window, not spawn a duplicate. Tauri `WebviewWindow::get_webview_window` + `set_focus` |
| `SH-3` | Window opens at `750×600`, **not** resizable-persistent; position never restored | MODERNIZE | Resizable, min-size `820×560`, restore size/position across launches via `tauri-plugin-window-state` |
| `SH-4` | No loading state — window appears fully painted | MUST | Must never flash. Start hidden, set the window background to the **resolved theme colour** (`A8` / `D-027`) before showing, and show only after first paint. **Both themes** are covered by `THEME-3` |
| `SH-5` | Second launch signals the first instance to open Settings (named mutex + event) | MUST | `tauri-plugin-single-instance`; callback must focus Settings (and un-hide the tray if dormant) |
| `SH-6` | Tray hidden while dormant (Discord closed + `auto_close_with_discord`); shown on Discord return | MUST | Tray visibility is engine-driven; the UI must not assume the tray is always present |
| `SH-7` | Tooltip text changes: `Discord AutoRPC` / `… — Waiting for Discord...` / `… — Discord not running` | MODERNIZE | Keep the states; the tooltip is the only always-visible status surface. Consider richer tooltip text incl. current app name (⚠️ native tray tooltips are length-limited and can't be styled) |
| `SH-8` | No app-level error surface — failures go to the log file | MODERNIZE | Add a non-blocking error toast + a persistent "engine offline" state (§12 `RSK-2`) |
| `SH-9` | Closing Settings leaves the app running in the tray (no quit-on-close) | MUST | Closing the window must **not** exit the process. Verify explicitly — this is a classic Tauri mistake |

### 4.2 Onboarding / first-run wizard (`gui.OnboardingWizardDialog`)

Shown when `application_id` is missing or fails validation. Modal today; returns config or
cancels (and the app then exits).

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `OB-1` | Fixed `540×510` modal dialog | MODERNIZE | Dedicated first-run **window** (not a modal over nothing), resizable, single-column, max-width ~600px |
| `OB-2` | Header card: title "🚀 Welcome to Discord AutoRPC" + subtitle "Connect Discord AutoRPC to your Discord client in 3 quick steps." | MUST | Keep the copy intent but **strip the emoji entirely** — no emoji anywhere (`A2` / `D-021`) |
| `OB-3` | **Step 1** label + `🌐 Open Discord Developer Portal` primary button → `https://discord.com/developers/applications` | MUST | Same URL. Add: copy-a-suggested-app-name affordance, and open in the default browser via `tauri-plugin-opener` (never inside the webview) |
| `OB-4` | **Step 2** label + explanation text about clicking "New Application" | MUST | Keep the instruction, but make it scannable (numbered sub-steps, not a paragraph) |
| `OB-5` | **Step 3** label + App ID input (placeholder `Paste your 17–20 digit Application ID here...`) | MUST | Add: auto-trim whitespace, strip a pasted full URL, numeric-only filtering, paste detection |
| `OB-6` | **Live validation** on every keystroke: green `✓ Valid Discord Application ID` or red error text | MUST | Keep live validation but **debounce ~250ms** and show the error only after first blur or 2+ chars typed (current version flashes errors while typing) |
| `OB-7` | Validation rules (exact strings, from `config.validate_app_id`): empty → `Application ID cannot be empty.`; `YOUR_DISCORD_APPLICATION_ID_HERE`/`0` → `Please enter your actual Discord Application ID.`; non-digits → `Application ID must contain numbers only.`; length ∉ [17,21] → `Discord Application IDs are 17–20 digits long (got N digits).` | MUST | **⚠️ Inconsistency to resolve with the owner:** the check accepts length **17–21** but the message says **17–20**. Pick one and make both agree (§13 Q3) |
| `OB-8` | Checkbox `Launch Discord AutoRPC automatically on Windows login (Recommended)` — **default checked** | MUST | → `tauri-plugin-autostart`. Note: this is the *only* place autostart is enabled during onboarding |
| `OB-9` | Checkbox `Auto-sync with Discord (hide when closed, run when opened)` — **default checked** | MUST | Maps to `auto_close_with_discord` |
| `OB-10` | `Cancel` → app exits entirely | MODERNIZE | Exiting on cancel is abrupt. Options to put to the owner: keep (documented) or offer "Continue without connecting" (§13 Q4) |
| `OB-11` | `✓ Save & Launch AutoRPC` (success style) → validates, writes config, enables autostart if checked, closes | MUST | Same behavior — but **add a verification step**: attempt an actual RPC handshake and report success/failure before finishing. Today a wrong-but-valid App ID completes onboarding and fails silently forever (§5.2, `OB-12`) |
| `OB-12` | *(does not exist)* | MODERNIZE | **Verify connection** step: "Connected to Discord as *<app name>*" or "Discord isn't running — we'll connect when it starts." This is the single highest-value new behavior in onboarding |
| `OB-13` | No back/step navigation — one scrollable page | MODERNIZE | **`A20` / `D-039`:** a real 3-step **Setup Assistant** with Back/Continue (Welcome → Create app → Paste + toggles + Verify connection). Do not hide the portal button behind a step the user can't complete |
| `OB-14` | No way to re-run onboarding later | MODERNIZE | Add "Re-run setup" in Settings → General (useful when a user switches Discord apps) |

### 4.3 Settings window — shell & navigation

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `SS-1` | `QTabWidget` with 5 tabs, labels: `⚙️ General`, `🏷️ App Names & Overrides`, `💬 Taglines`, `🚫 Ignored Apps`, `🖥️ Live Terminal & Logs` | MODERNIZE | **`A11` / `D-030`:** replace tabs with a 6-pane sidebar — **Status, General, App Names, Taglines, Ignored Apps, Logs** — icon + label with an active indicator. Labels are plain text; the emoji in today's tab labels is banned (`A2` / `D-021`) |
| `SS-2` | Bottom bar: `Close` + `💾 Save All Changes` (primary) | **DROPPED** | **`A12` / `D-031`:** autosave replaces the Save button entirely. `Close` remains, and closing never exits the app (`SH-9` / `REL-2`) |
| `SS-3` | No search, no command palette, no keyboard shortcuts | MODERNIZE | **`A11` / `D-030`:** `Ctrl+1…6` (sections) and `Esc` (dialogs/popovers) only. **The command palette and `Ctrl+K` are dropped**; `Ctrl+S` is obsolete under autosave (`A12`) |
| `SS-4` | No indication of what the app is currently doing | MODERNIZE | Persistent status header (§5.3): current app, icon, tagline, timer, Discord connection, pause state |
| `SS-5` | Window title `Discord AutoRPC — Settings & Live Terminal` | MODERNIZE | Shorten to `Settings — Discord AutoRPC`; put live status in the window, not the title |

### 4.4 Settings → General tab (`_build_general_tab`)

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `G-1` | Label `Discord Application ID:` + text input (unvalidated until Save) | MODERNIZE | Validate inline (same rules as `OB-7`), show a green "Valid" state, and offer a "Test connection" button |
| `G-2` | Checkbox `Close Discord AutoRPC automatically when Discord exits` ← `auto_close_with_discord` | MUST | |
| `G-3` | Checkbox `Launch Discord AutoRPC automatically on Windows login` ← `is_autostart_enabled()` / `set_autostart_enabled()` | MUST | State must be read from the real OS state (registry), not from config — otherwise it desyncs when the user disables it in Windows Settings |
| `G-4` | Checkbox `Mask / suppress presence in Incognito & Private browser windows` ← `mask_private_browsing` | MUST | Privacy feature. **Do not** bury, hide, or default it off |
| `G-5` | Checkbox `Enable Smart Dynamic Details (sheet names, web platforms, active files)` ← `enable_dynamic_taglines` | MUST | Add a short "what this does" hint + example, since the label alone is opaque |
| `G-6` | Card containing `App switch debounce delay (seconds):` spinner, range **2–60**, default 10 | MUST | Keep range. Add units clarity + tooltip explaining the tradeoff |
| `G-7` | Card containing `Idle timeout before clearing presence (seconds):` spinner, range **10–600**, default 60 | MUST | Keep range |
| `G-8` | *(not present)* `poll_interval` exists in config but has **no UI** | MODERNIZE | Decide: expose it (advanced section) or document as config-only. §13 Q5 |
| `G-9` | *(not present)* `whitelist_only` + `whitelist` exist in config but have **no UI** | MODERNIZE | Decide: expose (advanced) or document. §13 Q5. Note: enabling this today can silently make the app broadcast *nothing* |
| `G-10` | *(not present)* `upload_host` (`freeimage`/`catbox`) has no UI | MODERNIZE | Advanced: a host selector. Also needs a **privacy disclosure** — icons are uploaded to a public third-party host |
| `G-11` | *(not present)* `steamgriddb_api_key` has no UI | MODERNIZE | **`A16` / `D-035`:** Advanced group — masked key field + "test key" *(provisional: the Advanced group's visibility is Q5, still open)* |
| `G-12` | *(not present)* No way to reset all settings / restore defaults | MODERNIZE | Destructive action → confirm dialog + "export config first" escape hatch |

### 4.5 Settings → App Names & Overrides (`_build_overrides_tab`)

Edits the `overrides` map: `exe_name → {name, tagline?}`.

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `O-1` | Description: `Customize display names and custom taglines for specific programs:` | MUST | Keep intent |
| `O-2` | Table, 3 columns: **Executable**, **Display Name**, **Custom Tagline**; auto-sized col 0/1, stretched col 2; row selection; populated **sorted by exe name** | MODERNIZE | **`A17` / `D-036`:** an **inset list** with a filter field above and a `+` / `−` bar below; adding opens a small **popover**; deleting works from `−` and the `Delete` key with an undo toast. Recent-app suggestions and a real empty state |
| `O-3` | Add row inputs: `exe (e.g. photocraft.exe)` (160px), `Display Name (e.g. PhotoCraft)` (180px), `Tagline (optional)` | MODERNIZE | Inline "add" row that validates as you type; suggest exe names from recently-detected apps (the engine knows them) — huge usability win |
| `O-4` | `Add / Update` button: requires **both** exe and name; lowercases exe; **appends `.exe` if missing**; stores `{name}` plus `tagline` only if non-empty; clears inputs | MUST | Preserve normalization exactly (lowercase + `.exe` suffix) or config keys will mismatch |
| `O-5` | `Delete` (danger style) removes the selected row's entry | MUST | Add a confirm for multi-delete; single delete should be undoable (§5.7) |
| `O-6` | Changes are **local to the window** until `Save All Changes` | MODERNIZE | Unify save semantics (§4.7 `SEM-*`) |
| `O-7` | *(not present)* No icon preview | MODERNIZE | Show the resolved icon + the resolved display name side by side so users can see the effect of an override. The engine already has `get_icon_url` |
| `O-8` | *(not present)* No way to override the `icon_url` in the GUI, although the engine supports `overrides[exe].icon_url` | MODERNIZE | Add an optional icon-URL field with validation (must be `https:`, must be ≤255 chars — Discord's asset URL limit) |
| `O-9` | *(not present)* Creating an override for an exe that doesn't exist is allowed silently | MODERNIZE | Warn on unknown exe, don't block (users pre-configure games) |

### 4.6 Settings → Taglines (`_build_taglines_tab`)

Edits the `taglines` map: `exe_name → string`.

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `T-1` | Description: `Contextual taglines appear on the 2nd line of your Discord profile:` | MUST | |
| `T-2` | Table, 2 columns: **Executable**, **Tagline** | MODERNIZE | Same table upgrades as `O-2` |
| `T-3` | Add row: `e.g. notion.exe` (160px), `e.g. Working on a document` | MODERNIZE | Add a live Discord-style **preview chip** so users see how it reads |
| `T-4` | `Add / Update`: requires both; lowercases; appends `.exe`; clears inputs | MUST | Same normalization as `O-4` |
| `T-5` | `Delete` removes the selected exe's tagline | MUST | |
| `T-6` | *(not present)* Built-in tagline table (58 entries in `detector._BUILTIN_TAGLINES`) is **invisible** in the UI | MODERNIZE | **`A17` / `D-036`:** built-ins become a **read-only group** in the pane, so users can see and override them. Plus a live preview, a 128-char counter, and the precedence one-liner |
| `T-7` | *(not present)* No indication of precedence | MODERNIZE | Add a one-line explainer: *override → dynamic title → your tagline → built-in → keyword guess* |
| `T-8` | *(not present)* No character-limit awareness | MODERNIZE | Discord truncates; show a counter and warn past ~128 chars (§9.6) |

### 4.7 Settings → Ignored Apps (`_build_ignored_tab`)

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `I-1` | Description: `Applications that will be silently ignored (never shown on Discord):` | MUST | |
| `I-2` | A flat `QListWidget` of exe names, populated sorted | MODERNIZE | List with the same treatment as tables (filter, per-row remove) |
| `I-3` | Input `Executable name (e.g. secret_app.exe)` + `Add to Ignore List` (appends `.exe` if missing, lowercases, dedupes) | MUST | Keep normalization |
| `I-4` | `Remove` (danger) removes the selected row from `config.ignored_exes` | MUST | |
| `I-5` | **⚠️ This list is `config.ignored_exes` — a DIFFERENT list from `ignore_list.json`, which the tray menu writes to** | MUST / CLARIFY | **`A18` / `D-037`:** merge into **one source of truth** with migration of existing `ignore_list.json` entries; the tray and this pane must read/write the same store. Must be resolved **before G1** (`RSK-6`). The #1 correctness trap in the current GUI |
| `I-6` | *(not present)* No visibility into the ~12 **built-in default ignores** (`explorer.exe`, `SearchHost.exe`, …) | MODERNIZE | Show defaults as a separate read-only group so users understand why the desktop never appears |
| `I-7` | *(not present)* No visibility into the automatic `%SystemRoot%` skip | MODERNIZE | Add a hint line; it explains a lot of "why isn't this app showing" |
| `I-8` | *(not present)* `🚫 Ignore current app` (tray) and this tab can diverge | MUST | See `I-5`. Add a "detected now → ignore" shortcut from the **Status pane** (§5.3) |

### 4.8 Settings → Live Terminal & Logs (`_build_terminal_tab`)

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `L-1` | Header `Real-Time Process & Detection Logs:` | MUST | |
| `L-2` | Checkbox `Auto-scroll` (**checked**) | MODERNIZE | **`A19` / `D-038`:** a **follow toggle** that auto-pauses when the user scrolls up and offers **"Jump to latest"** |
| `L-3` | Button `📋 Copy Logs` → whole console text to clipboard → modal `Copied` / `Terminal logs copied to clipboard!` | MODERNIZE | Copy should copy the **filtered/visible** view; feedback via toast, not a modal |
| `L-4` | Button `💾 Export Log File...` → native save dialog, default name `autorpc_logs.txt`, writes plain text → modal `Saved` / `Log successfully saved to <path>` or `Error` / `Failed to save log file: <exc>` | MODERNIZE | Keep native save dialog (`tauri-plugin-dialog`). Use `error`-type toast on failure. **Do the write in the backend**, not via a broadly-scoped fs permission (§9.5) |
| `L-5` | Button `🧹 Clear` → clears the on-screen console only (does not touch the log file) | MUST | Keep exactly this behavior and label it clearly ("Clear view") so users don't think they deleted the log |
| `L-6` | Button `🔄 Reset Icon Cache` → clears `icon_cache.json`, modal `Icon Cache Reset` / `Successfully cleared N cached icons.` + `Next app detections will fetch/upload fresh icons.` | MUST | Keep; add a confirm (it causes a burst of re-uploads) and show the count |
| `L-7` | Read-only monospace console, seeded with the **last 200 lines** of `autorpc.log` on open, then appended live | MUST | Keep the 200-line seed. Must handle high throughput without jank (§10 `PERF-1`) |
| `L-8` | Live appends come from a `logging.Handler` on the root logger at DEBUG, formatted `[%(asctime)s] %(levelname)-7s %(name)s - %(message)s` with time `%H:%M:%S` | MODERNIZE | Keep the format for familiarity but **parse into structured fields** (timestamp, level, module, message) so the UI can color, filter, and search |
| `L-9` | *(not present)* No level filtering | MODERNIZE | Level chips (DEBUG/INFO/WARN/ERROR) with counts |
| `L-10` | *(not present)* No text search / no highlight | MODERNIZE | Search box with match highlighting + match count; `Enter`/`Shift+Enter` to step through |
| `L-11` | *(not present)* No way to see detection decisions over time | MODERNIZE | **`A19` / `D-038`:** a **detection digest** (last N app switches with the resolved tagline and icon source). **Deferred — do not build in v1** |
| `L-12` | *(not present)* No log-file rotation info or "open log folder" | MODERNIZE | `Open log` exists in the tray (opens the file). Add "open containing folder" |

### 4.9 Quick rename of the active app (`gui.QuickRenameDialog`)

Reached from the tray: `🏷️ Rename Active App (<current display name>)…`. Writes an override
and **applies it immediately** (pushes a new presence without a full reload).

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `R-1` | Fixed `480×310` **modal** dialog, title `Rename Active App — <exe>` | MODERNIZE | **`A21` / `D-040`:** a small **standalone window** (native tray menus cannot anchor a popover — see `RSK-1`) **and** the same component as a **sheet on the Status pane**. Not a blocking modal |
| `R-2` | Header `🏷️ Rename '<exe>'` + `Customize how this application and status appear on your Discord profile.` | MUST | |
| `R-3` | Label `Custom Display Name (shown as 'Playing ...'):` + input prefilled with the current display name, placeholder `e.g. PhotoCraft or Photoshop` | MUST | Add live preview of the `Playing <name>` header |
| `R-4` | Label `Custom Tagline (optional details line):` + input prefilled with the current tagline, placeholder `Leave blank to keep automatic dynamic detail` | MUST | **Critical semantic:** an empty tagline means *"fall back to automatic/dynamic"*, not *"show nothing"* (see `R-7`) |
| `R-5` | `Cancel` | MUST | |
| `R-6` | `💾 Save & Apply Instantly` → warns `Invalid Name` / `Display Name cannot be empty.` if blank | MUST | Inline validation instead of the alert |
| `R-7` | On save: writes `overrides[<exe lower>] = {name, tagline}` **including an empty-string tagline**, saves config, then fires a callback that updates the in-memory app and **immediately re-pushes presence**; then shows modal `Name Saved` / `Successfully updated '<exe>' to display as '<name>' on Discord!` | MUST | Preserve "apply instantly" (no restart, no waiting for the 30s config reload). The empty-string→override-with-empty-tagline behavior must be preserved or consciously changed; note the engine treats `""` as "not set" and falls through to dynamic parsing |
| `R-8` | *(not present)* No way to rename a non-foreground app | MODERNIZE | Allow picking from recently detected apps |

### 4.10 Tray icon & context menu (`main._create_qt_tray`)

⚠️ **Architectural warning for the implementer:** the current menu is a **Qt `QMenu` styled
with `DISCORD_DARK_QSS`**. Tauri/muda menus are **native Win32 menus and cannot be styled**.
On Windows 11 they pick up the OS's modern look automatically (rounded, dark-mode aware);
on Windows 10 they look like classic menus. **Do not** promise a pixel-identical styled tray
menu. The tray decision was **closed at G0** — see §12 `RSK-1`: native menu, plain text (`A22` / `D-041`).

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `TR-1` | Tray icon from `assets/icon.png`; falls back to a generated 64×64 PNG (blurple circle + play triangle) | MUST | **`A10` / `D-029`:** ship a **multi-resolution `.ico`** (16/20/24/32/48) that is legible on **light *and* dark taskbars** — the taskbar theme is independent of the app theme. The single-PNG approach is a known blur source |
| `TR-2` | Icon swaps to a **grey pause variant** when paused | MUST | Both states needed at every size, verified on light and dark taskbars (`A10` / `D-029`) |
| `TR-3` | Tooltip `Discord AutoRPC` / `… — Waiting for Discord...` / `… — Discord not running` | MUST | |
| `TR-4` | **Item 1:** `Discord AutoRPC v<version>`, disabled; becomes `⭐ Update to v<tag>` and enabled when an update is found → opens the release URL | MODERNIZE | Keep two states; on Windows a disabled first item reads as a header. Consider a styled "header + action" pair, or an inline banner in Settings |
| `TR-5` | **Item 2:** separator | MUST | |
| `TR-6` | **Item 3:** `⚙️ Settings` → open/focus Settings | MUST | |
| `TR-7` | **Item 4:** separator | MUST | |
| `TR-8` | **Item 5:** `🏷️ Rename Active App (<display name>)…`, **disabled** when no app is detected (then reads `🏷️ Rename Active App…`) | MUST | Dynamic relabel before the menu is shown. Verify the chosen menu library supports mutating labels pre-open |
| `TR-9` | **Item 6:** `⏸ Pause` ⇄ `▶ Resume`; pausing clears presence and swaps the icon | MUST | Also drives the **Status pane's** paused state. Labels are plain text — no emoji (`A2`) |
| `TR-10` | **Item 7:** `🚫 Ignore <exe_name>` / `🚫 Ignore current app`; writes to `ignore_list.json` and recreates the detector | MUST | **`A18` / `D-037`:** the tray writes the **single unified ignore list** — the one the Ignored Apps pane also shows. Labels are plain text (`A2`) |
| `TR-11` | **Item 8:** separator | MUST | |
| `TR-12` | **Item 9:** `📋 Open log` → opens `autorpc.log` with the default app (`os.startfile`, fallback `notepad`) | MUST | Via `tauri-plugin-opener` |
| `TR-13` | **Item 10:** `❌ Quit` → sets quit, closes RPC, hides tray, exits the app | MUST | Must be the *only* way to fully exit. Confirm behavior with the user (some apps confirm on quit) |
| `TR-14` | Double-click **or single click** on the icon opens Settings | MUST | ⚠️ Single-click-opens-a-window is unusual on Windows 11 and can feel like a bug when the user was aiming for the context menu. Verify with the owner (§13 Q7) |
| `TR-15` | Items 5 & 7 are disabled when nothing is detected | MUST | Requires the UI to receive live "current app" state |
| `TR-16` | *(not present)* No "Now playing" info in the menu | MODERNIZE | Add a read-only header line showing the current app, or make the tooltip richer |

### 4.11 Feedback, dialogs, and toasts (cross-cutting)

| ID | Today | Verdict | Notes |
|---|---|---|---|
| `FB-1` | **8 modal `QMessageBox` calls**: copied, export ok, export error, saved, invalid app id, icon cache reset, name saved, invalid name | MODERNIZE | **`A14` / `D-033`:** replace all 8 with a quiet **bottom-centre toast pill** carrying an Undo action (`aria-live="polite"`), **inline** validation errors, and dialogs **only** for destructive actions (reset icon cache, reset settings, multi-delete) |
| `FB-2` | Modals are app-blocking (`exec()`) | MODERNIZE | Nothing user-facing should block the engine or the log stream |
| `FB-3` | No undo anywhere | MODERNIZE | Single-row deletes and "ignore app" should be undoable via toast action |
| `FB-4` | No global error boundary | MODERNIZE | A React error boundary + a friendly recovery screen; never a blank window |

### 4.12 Persistence semantics (`SEM-*`) — **read this twice**

The current app has **four different save behaviors**. This is the most likely source of
regressions and user confusion in the rewrite.

| ID | Surface | Current behavior |
|---|---|---|
| `SEM-1` | Onboarding | Validates → writes `config.json` **immediately** → optionally enables autostart |
| `SEM-2` | Quick Rename | Writes `config.json` **immediately** and **applies live** |
| `SEM-3` | Settings window | Buffers **all** edits in memory (overrides/taglines/ignored/spinners/checkboxes) and writes only on `Save All Changes`; **the window closes on save** |
| `SEM-4` | Tray "Ignore current app" | Writes `ignore_list.json` **immediately** (a different file — see `I-5`; unified by `A18` / `D-037`) |
| `SEM-5` | Settings `Save All Changes` also calls `set_autostart_enabled(...)` **unconditionally** with the checkbox state | 
| `SEM-6` | After Settings save, the engine is told to rebuild its detector (`state["_detector"] = None`) so changes apply without restart |
| `SEM-7` | Config is *also* hot-reloaded by the engine every 30s | 
| `SEM-8` | `Save All Changes` **validates the App ID and refuses to save anything else** if it's invalid | ⚠️ So a user who only wanted to add a tagline gets blocked by an unrelated field |

**RESOLVED — `A12` / `D-031`: autosave. There is no Save button.**

Commit points: **toggles write immediately**, **steppers are debounced**, **text fields write on
blur or `Enter`**. The window no longer closes after saving, because there is no save action.

| ID | Under autosave |
|---|---|
| `SEM-1` | Unchanged — onboarding still writes at the end of step 3, and now verifies the connection (`OB-12`) |
| `SEM-2` | Unchanged — rename still applies instantly; it is now the same mechanism every control uses |
| `SEM-3` | **Replaced.** No in-memory buffer and no `Save All Changes`; each control commits independently |
| `SEM-4` | Follows the **unified ignore list** (`A18` / `D-037`) — the tray and the pane write the same store |
| `SEM-5` | The autostart toggle writes when toggled and reads back the **real OS state** (`G-3`) |
| `SEM-6` | Unchanged in intent — the engine is notified on every mutation, immediately |
| `SEM-7` | Unchanged — the engine's 30 s config hot-reload still exists; the UI must tolerate a `config-changed` event without clobbering a field being edited |
| `SEM-8` | **Decomposed.** An invalid field never writes and **never blocks any other field**; errors are inline and scoped to that field |

Every mutation is **atomic** (temp + rename) and **optimistic with rollback** on backend error,
followed by a toast (`A14`).

---

## 5. Making it *feel* modern — the concrete direction

Modern here means **fast, legible, live, and quiet** — not "more animation." Each item below
is a change you should be able to point at in a screenshot or a recording.

### 5.1 Sidebar navigation instead of tabs *(`A11` / `D-030`)*
Icon + label rail, active indicator, optional count badges, and `Ctrl+1…6`. Final pane order:
**Status, General, App Names, Taglines, Ignored Apps, Logs.** Pane labels are plain text — the
emoji in today's tab labels is banned (`A2`).

### 5.2 Kill modal fatigue
Success is a toast. Errors are inline. Only destruction is modal. Result: the user never
hunts for a dismiss button to find out that something worked.

### 5.3 A live "Now Broadcasting" surface *(new — the biggest single upgrade)* — **`A15` / `D-034`: shipped as the "Status" landing pane**
Nothing in the current UI shows what the app is actually doing. Put a compact card at the top
of every section (or a fixed header) with:
- the current app's **icon**, **display name**, and **resolved tagline**
- **elapsed time** ticking once per second
- Discord **connection state** (Connected / Waiting for Discord / Discord not running) and **pause** state
- inline actions: **Pause/Resume**, **Rename**, **Ignore this app**
- ~~a "why this tagline?" disclosure showing which rule won (override → dynamic → user tagline → built-in → keyword)~~ — **deferred (`A15`); do not build in v1**

**`A15`:** this is realized as the **Status pane** — the default landing surface and the first
sidebar item — not as a card repeated across every pane.

This turns the app from "configure and hope" into "observe and adjust," and it's the reason a
live webview is the right tool for this job.

### 5.4 Lists that behave like modern lists *(`A17` / `D-036` — replaces "table" everywhere)*
The three list panes are **grouped inset lists**, not data grids: a filter field above, rows
below, a `+` / `−` bar underneath. Filtering, keyboard navigation, inline edit-or-popover,
per-row actions, real empty states (*"No overrides yet — apps use automatic names. Add one to
customize."*), and undo on delete. Replace the "select a row, then find the Delete button"
pattern.

Sorting and virtualization apply **only to App Names** and only if the owner keeps a table shape
for it — that is a G1 question, not an assumption.

### 5.5 A diagnostic log view that earns its space *(`A19` / `D-038`)*
A **minimum-level segmented control**, search with highlighting, follow/pause with "Jump to
latest", copy-or-export-what-you-see, and a capped ring buffer with a "N lines dropped"
indicator. Log lines are structured, not string-concatenated, so filtering and colouring are
reliable. The detection digest is deferred.

### 5.6 Native Windows frame, macOS System Settings interior *(`A1`, `A3` — supersedes the original Mica recommendation)*
- **Adopt the macOS System Settings layout and component language** — sidebar + grouped inset
  lists + label-left/control-right rows — **inside a native Windows frame** (`D-020`).
- **Keep native window decorations. No custom titlebar in v1.** A custom titlebar costs snap
  layouts, maximize behaviour, DPI correctness, and accessibility. **No fake traffic lights.**
- **No vibrancy, glass, or gradients.** CSS `backdrop-filter` cannot blur the desktop *behind*
  the window, so any "glass" would be fake. Solid surfaces only (`D-022`).
- **Mica is optional later**, not v1 — and if adopted it must degrade to a solid surface on
  Windows 10 and in both themes.
- **Rounded corners** come free on Win 11; ensure the Win 10 frame doesn't look broken.
- **Snap layouts / maximize** must work.

### 5.7 Undo instead of confirm
For non-destructive removals (a tagline, an override, an ignored app), do it immediately and
offer **Undo** in the toast. Save confirmations for resets and multi-deletes.

### 5.8 A real icon set and a typographic scale *(`A2`, `A9`)*
**Emoji and glyph-as-icon characters are banned everywhere** — UI, copy strings, tray labels,
and toasts. This explicitly includes `✓` and `⭐`. Use one icon library (Lucide or Phosphor) at
one size and one stroke weight, `currentColor`, with `aria-label` on icon-only buttons
(`D-021`, `D-028`). Type scale is fixed at 20 / 15 / 13 / 12 with weights 400 / 500 / 600;
secondary text uses `text.secondary` from the theme tokens (§8.1).

### 5.9 ~~A command palette (`Ctrl+K`)~~ — **DROPPED (`A11` / `D-030`)**
Not built in v1. Navigation is the sidebar plus `Ctrl+1…6`; the Status pane covers
pause / rename / ignore. Revisit only if the owner asks for it later.

### 5.10 Restraint
- Motion: 120–200ms, `ease-out`, **state transitions only** (open/close, list insert/remove,
  toast). Respect `prefers-reduced-motion`. No entrance animations on a settings form.
- **One accent colour, one token** (`accent`, §8.1). Brand blurple (`#5865F2`) is a one-line
  swap if the owner prefers it, but the text variants must then be re-checked for contrast.
  No gradients, no glass, no coloured sidebar tiles (`A3`).
- No skeleton loaders on a local, sub-50ms data path — they'd be slower than the data.

---

## 6. Contracts you must approve before G1

### 6.1 Config schema (unchanged, on disk)

`config.json` keys and semantics must not change (see `AGENTS.md` §6). Unknown keys must be
**preserved** on write. `icon_cache.json` = `{ "<exe_path_lower>": "<url>" }`.
Data dir resolution stays exactly as `config.get_data_dir()` defines it (dev = repo root;
frozen = portable if `portable.txt`/config beside the exe, else `%APPDATA%\DiscordAutoRPC`).

**Non-negotiable:** a user must be able to keep their existing files and see no difference.

**Two amendments from G0:**

1. **`ignore_list.json` is retired as a separate store** (`A18` / `D-037`). Existing entries are
   migrated into the single unified ignore list. The migration must be idempotent and must not
   lose entries if the app is closed mid-migration.
2. **`ui_prefs.json` is a new file** in the same data dir (`A5` / `D-024`), written **only** by a
   backend command (`SEC-2`). It holds UI state that must not leak into `config.json`:

```jsonc
{
  "appearance": "system"   // "system" | "light" | "dark"; missing key or file ⇒ "system"
}
```

`config.json` stays frozen so the Python build remains unaffected and the two builds can share
a data dir during migration.

### 6.2 Engine → UI commands (UI invokes; backend returns)

Approve these names/shapes as the interface. Every one needs an explicit failure shape.

| Command | Returns |
|---|---|
| `get_snapshot` | version, config, autostart state, engine status, current app, Discord state, pause state, update state |
| `get_config` / `save_config` | config object; validation errors |
| `validate_app_id` | `{valid, message}` |
| `get_autostart` / `set_autostart` | real OS state (not config) |
| `list_overrides` / `upsert_override` / `delete_override` | rows |
| `list_taglines` / `upsert_tagline` / `delete_tagline` | rows |
| `list_ignored` / `add_ignored` / `remove_ignored` | rows (decide the single source of truth first — `I-5`) |
| `get_builtin_taglines` / `get_default_ignores` | read-only reference data for the UI |
| `get_current_app` | `{exe, displayName, tagline, taglineSource, iconUrl, sinceEpochMs}` |
| `test_connection` | `{ok, appName?, error?}` |
| `rename_active_app` | applies immediately, returns new state |
| `ignore_active_app` | |
| `set_paused` | |
| `get_logs_tail` (n) | structured lines |
| `export_logs` (content or filter) | writes the file in the backend, returns the path |
| `clear_view` / `clear_icon_cache` | cleared count |
| `check_for_updates` / `open_url` / `open_log_file` / `open_log_folder` | |
| **`get_ui_prefs` / `set_ui_prefs`** | appearance preference (`A5`); writes `ui_prefs.json` atomically |
| **`set_window_theme`** | applies the native frame theme: `light` / `dark` / `none` (System) — `A6` |
| `restart_engine` | for Option A (`RSK-2`) |

### 6.3 Engine → UI events (backend pushes)

| Event | Payload | Drives |
|---|---|---|
| `status-changed` | Discord state, connected bool, paused bool, dormant bool | Status card, tray tooltip |
| `app-changed` | current `AppInfo` + resolved tagline + icon | Status card, tray menu labels, diagnostics |
| `config-changed` | config (external reload / another window) | Forms must not clobber unsaved edits |
| `log-line` | structured line | Log view (**batched**, see §10 `PERF-1`) |
| `update-available` | version, url | Tray item + banner |
| `engine-error` | message, recoverable bool | Error toast / engine-offline state |
| `toast` | `{type, message, actionLabel?, actionId?}` | Undo + engine-initiated feedback |
| **`ui-prefs-changed`** | `{appearance}` | Keeps a second window (e.g. quick rename) in sync with the Appearance control (`A5`) |

**Review point:** the UI must **not** poll for state. Everything above is push. Polling is a
rejection reason.

#### 6.2.1 As implemented — `desktop/src/ipc/types.ts` is the frozen contract

The tables above are the *proposal* that `G0` approved in shape. The implemented surface folds
several CRUD triplets into **one** `set_config`/`rename_app` pair that returns the whole file it
wrote, because `config.json` is one document and per-field commands would fight each other over it.
Names marked ✔ are unchanged from the table above.

| Table row | As implemented | Why |
|---|---|---|
| `get_snapshot` | `get_state` | One `EngineState` payload; config is fetched separately so a config write cannot churn the status view. |
| `get_config` ✔ / `save_config` | `get_config` / **`set_config {patch}`** | Autosave sends a patch, not the whole document (`SEM-3`), and the return value is the file as written (unknown keys included). |
| `validate_app_id` | in the frontend (`src/lib/validation.ts`) | It is a pure string rule; a round trip per keystroke would need a debounce for no benefit. Rust re-checks on write (`config_file::is_valid_app_id`). |
| `get_autostart` ✔ / `set_autostart` ✔ | ✔ (with read-back) | The OS is the source of truth, so `set` returns what Windows actually reports, not what was asked for. |
| `list_overrides` / `upsert_override` / `delete_override` | `set_config {overrides}` / **`rename_app`** / `remove_override` | Rows are edited as a map through `set_config`; `rename_app` exists because the tray and the rename window need the instant-apply path (`R-7`). |
| `list_taglines` / `upsert_tagline` / `delete_tagline` | `set_config {taglines}` | Same document, same reason. |
| `list_ignored` / `add_ignored` / `remove_ignored` | `get_ignored` / `ignore_app` / `unignore_app` | ✔ in shape, and now writing **one** store (`D-047`). |
| `get_builtin_taglines` / `get_default_ignores` | `get_built_ins` | Empty until the engine serves the table (`D-051`); the ignore defaults arrive inside `get_ignored`. |
| `get_current_app` | part of `get_state` | It only changes with state, and it changes with `state` events. |
| `test_connection` ✔ | ✔ | Answers with `{ok, detail, appName}` — `detail` is the reason a failed handshake gives, so the UI never invents copy (`ERR-2`). |
| `rename_active_app` / `ignore_active_app` / `set_paused` | `rename_app` / `ignore_app` / `pause` + `resume` | Two explicit verbs beat a boolean parameter at the call site. |
| `get_logs_tail` | `seed_logs` | Matches the "seed the ring buffer once" model (`L-7`). |
| `export_logs` ✔ / `clear_icon_cache` ✔ / `check_for_updates` ✔ / `open_url` ✔ / `open_log_file` / `open_log_folder` | ✔ + `export_config`, `open_log`, `open_log_folder`, `ui_log`, `copy_text`, `app_icon_url`, `reset_config`, `close_window`, `open_settings`, `open_onboarding`, `open_rename` | Adds: window control (all windows are Rust-owned — `D-049`), clipboard and icon URL, and `ui_log` so a frontend failure is visible in the same log as everything else. |
| `get_ui_prefs` / `set_ui_prefs` | `get_prefs` / **`set_prefs {appearance}`** | ✔ in shape, one field wide. |
| `set_window_theme` ✔ | ✔ | Called per window; `system` passes `None` so the OS keeps deciding (`D-046`). |
| `restart_engine` | — | Needs an engine to restart (`T-022`). |
| *(new)* window chrome | `minimize_window`, `toggle_maximize`, `close_window`, plus the **`window-state`** event (`{maximized}`) | Added by `D-055`: the windows are frameless, so the controls are commands rather than JS plugin calls (which keeps `client.ts` the only `@tauri-apps/api` importer), and the maximize glyph can only come from Rust, which is the side that knows the OS state. |

Events: `status-changed` + `app-changed` are one **`state`** event carrying the whole
`EngineState`, `log-line` is **`log`**, `update-available` and `engine-error` do not exist yet
(`D-051`); `config-changed` and `ui-prefs-changed` are ✔ as proposed. **`toast`** is wired end to
end but only the mock backend emits it today — the shell has no engine-initiated feedback to
relay until `T-022`. **`window-state`** is new (`D-055`): the main window's maximized flag after
every resize, so the custom chrome can show maximize or restore.

---

## 7. State model (what to require in the design doc at G1)

- **Rust/engine owns the truth.** Config, current app, log history, connection state.
- **UI owns only ephemeral state:** which section is open, filters, drafts being edited, toast queue.
- **`ui_prefs.json` is backend-owned** (`A5` / `D-024`): the appearance preference is read at boot,
  written through `set_ui_prefs`, and echoed back via `ui-prefs-changed` so a second window
  (quick rename) stays in sync. **Never in `localStorage`.**
- **Autosave, therefore no drafts** (`A12` / `D-031`). There is no implicit "saved" state to
  model. A `config-changed` event fires whenever the engine hot-reloads, and must **not** clobber
  a field the user is currently editing.
- **Every mutation is optimistic with rollback** on backend error, followed by a toast.
- **No business logic in components** — modules for the IPC client, the config store, and
  formatting/validation helpers, so they're unit-testable.

---

## 8. Design system specification

### 8.1 Tokens — two themes *(`A4`–`A7`; replaces the dark-only palette)*

**Rules**
1. **Every colour is a CSS variable. Components never hard-code a colour** (`D-026`).
2. Cascade, exactly:
   - light tokens on `:root`
   - dark tokens under `@media (prefers-color-scheme: dark)`, **guarded** with `:root:not([data-theme="light"])`
   - dark tokens again under `:root[data-theme="dark"]`
3. The resolved theme is applied by setting `data-theme` on the document element. `System`
   removes the attribute and lets the media query win, so an OS change is followed **live**.
4. `accent` is a **single token**. Blurple (`#5865F2`) is a one-line swap if the owner prefers
   it — but the text variants must then be re-checked (`accent.text`).

| Token | Light | Dark |
|---|---|---|
| `bg.window` | `#F5F5F7` | `#1E1E1E` |
| `bg.sidebar` | `#EAEAEC` | `#262628` |
| `bg.group` (inset cards) | `#FFFFFF` | `#2C2C2E` |
| `bg.input` | `#F0F0F2` | `#1C1C1E` |
| `bg.hover` | `#EFEFF2` | `#333335` |
| `bg.sunken` (log) | `#F0F0F2` | `#141414` |
| `separator` | `#DCDCE0` | `#38383A` |
| `text.primary` | `#1D1D1F` | `#F5F5F7` |
| `text.secondary` | `#636366` | `#A1A1A6` |
| `accent` (fills, white text) | `#0071E3` | `#0A6FE0` |
| `accent.text` | `#0066CC` | `#409CFF` |
| `danger.fill` (white text) | `#D70015` | `#D93A31` |
| `danger.text` | `#D70015` | `#FF6961` |
| `success.text` | `#1E7B34` | `#32D74B` |

**Why the accent is not stock Apple blue:** `#007AFF` / `#0A84FF` measure only 4.02 / 3.65
against white text, so they fail AA for the primary button. The fills above are deliberately
darker to clear 4.5:1.

**Measured contrast ratios** (owner-supplied; verify any pair not listed at G1 — for example
`text.secondary` on the light `bg.hover`):

| Pair | Light | Dark |
|---|---|---|
| `text.primary` on `bg.window` | 15.46 | 15.31 |
| `text.primary` on `bg.group` | 16.83 | 12.80 |
| `text.secondary` on `bg.group` | 5.99 | 5.42 |
| `text.secondary` on `bg.window` | 5.50 | 6.48 |
| `text.secondary` on `bg.sidebar` | 4.98 | 5.87 |
| `text.secondary` on `bg.input` | 5.26 | 6.61 |
| `text.secondary` on `bg.hover` | *not measured* | 4.90 |
| `text.secondary` on `bg.sunken` | 5.26 | 7.16 |
| white on `accent` | 4.70 | 4.81 |
| white on `danger.fill` | 5.38 | 4.57 |
| `accent.text` on `bg.group` | 5.57 | 4.92 |
| `danger.text` on `bg.group` | 5.38 | 4.94 |
| `success.text` on `bg.group` | 5.33 | 7.27 |

**Never convey state by colour alone** — pair every colour signal with an icon or text
(`A11Y-3`).

### 8.2 Type, spacing, shape *(`A9` / `D-028`)*
- **Font:** **Inter, bundled locally** — CSP forbids remote fonts, and SF Pro is not licensed
  for non-Apple platforms. Fallback chain: Inter → Segoe UI Variable → `system-ui`.
- **Scale:** 20 title / 15 section / 13 body / 12 caption. Weights **400, 500, 600 only.**
- **Log font:** Cascadia Mono → Consolas, 12px.
- **Icons:** Lucide (or Phosphor), one stroke weight (~1.5), 16px in the sidebar, `currentColor`,
  `aria-label` on icon-only buttons. No emoji, no glyph characters (`A2`).
- **Shape:** 4px grid; **10px** radius on cards, **6px** on controls; 1px hairline separators;
  shadows **only** on popovers and dialogs.
- **Window:** resizable, min **820×560**, size/position restored. Title is **"Settings"**.
  Content column ~**680px**, centred.

### 8.3 Components to inventory at G1 *(`A13` control vocabulary)*
Button (variants: primary / secondary / danger / quiet), Input, **NumberField** (with stepper),
**Switch** (`role="switch"`), SegmentedControl, Select, Card, **GroupedInsetList** (label left,
control right, description under the label), SidebarNav, **InsetList** (filter + `+`/`−` bar),
Popover, Sheet, EmptyState, Toast, AlertDialog, Tooltip, StatusPill, KeyValue, LogView,
LogToolbar, LevelSegmentedControl, SearchInput, RowActions, IconButton.

**Not in v1:** `CommandPalette`, `Table` (the list panes are inset lists per `A17`, not data
grids — if a table is still wanted for App Names, that is a G1 question, not an assumption),
`Checkbox` (superseded by `Switch`), `Tabs`.

### 8.4 Motion budget
120–200ms `ease-out` on: popover/sheet/dialog open-close, toast in-out, list row insert/remove.
Nothing else — **no section-switch crossfade, no entrance animations on a settings form, and no
colour transition when the theme changes** (`A8`: the switch is instant). Honor
`prefers-reduced-motion`.

---

## 9. Cross-cutting requirements

| ID | Requirement |
|---|---|
| `A11Y-1` | Every control keyboard-reachable; visible focus ring using `accent`; `Esc` closes popovers/dialogs; `Enter` submits the focused form; arrow keys navigate lists and segmented controls |
| `A11Y-2` | Real semantics: correct roles/`aria` on the **inset lists** (not `<table>` — see `A17`), `aria-label` on icon-only buttons, `aria-live="polite"` for toasts and the **Status pane**, labels tied to inputs |
| `A11Y-3` | Contrast ≥ 4.5:1 for text (see §8.1); never convey state by color alone (pair with icon/text) |
| `A11Y-4` | Respect `prefers-reduced-motion` and the OS font-scaling setting |
| `I18N-1` | No hardcoded user-facing strings in components — all through a string module, even if only English ships |
| `DPI-1` | Correct on 100/125/150/200% scaling; tray icon crisp at every size (multi-res `.ico`) |
| `UI-1` | **No emoji and no glyph-as-icon characters anywhere** — UI, copy strings, tray labels, toasts (`A2` / `D-021`). This is a rejection reason |
| `UI-2` | **No vibrancy, glass, or gradients**, and no fake transparency (`A3` / `D-022`). Solid surfaces only |
| `UI-3` | **Native window decorations retained**; no custom titlebar, no fake traffic lights (`A1` / `D-020`). Snap layouts and maximize must work |
| `FONT-1` | All fonts are **bundled locally**; no remote font loading (CSP + offline correctness) (`A9`) |
| `THEME-1` | Appearance is `System / Light / Dark`, default **System**; System follows the OS **live**, including while Settings is open |
| `THEME-2` | The appearance preference **persists across restart** and is stored only in `ui_prefs.json`, never `config.json` |
| `THEME-3` | **No flash of the wrong theme on open**, in either theme: hidden start → backend paints → `data-theme` set synchronously before React renders → show after first paint. No inline script (`A8` / `SEC-1`) |
| `THEME-4` | The **native frame theme follows** the in-app choice (`set_theme`) |
| `THEME-5` | **Theme switch is instant**, with no colour transition; both themes meet the contrast table in §8.1 |
| `THEME-6` | The **tray icon is legible on light and dark taskbars** regardless of the app theme (`A10`) |
| `SEC-1` | Strict CSP; no remote content loaded in the webview; no inline scripts |
| `SEC-2` | **No broad filesystem permission for the frontend.** All file I/O (config, cache, log export, open-file) happens in backend commands. Granting `fs` scope to the UI is a rejection reason |
| `SEC-3` | Validate every IPC input in the backend: exe names (pattern + lowercase + `.exe`), taglines (length), and **`icon_url` must be `https:` and ≤255 chars** before it is sent to Discord |
| `SEC-4` | Never render user-supplied strings as HTML (the icon URL and window titles are user-influenced) |
| `SEC-5` | Tauri capabilities explicitly enumerated per window; no wildcard scopes |
| `PERF-1` | The log view must sustain a high line rate (assume hundreds/sec during a detection storm) without dropping frames or growing memory: batched event delivery (Tauri `Channel`/batched emits), a capped ring buffer (e.g. 5,000 lines), virtualized rendering, and a "N lines dropped" indicator |
| `PERF-2` | Settings window interactive in <300ms; no white flash on open; no skeleton where data is instant |
| `PERF-3` | Idle CPU must stay negligible — the UI must not poll |
| `REL-1` | The UI must survive an engine crash/restart (Option A): show "engine offline", offer Restart, and resync state |
| `REL-2` | Closing Settings never exits the process; only tray Quit does |
| `REL-3` | Config writes are atomic (temp + rename) — a crash mid-write must not corrupt `config.json` |

---

## 10. Verification procedure (run this yourself at G5)

Do not trust a demo. Run these on a **clean Windows 10 and a clean Windows 11 VM**:

1. **First run** with no `config.json` → onboarding appears; paste a real App ID → success path;
   paste garbage → each of the four validation messages appears correctly; cancel → documented behavior.
2. **Config portability** — copy a `config.json`, `icon_cache.json`, and `ignore_list.json`
   produced by the *current Python build* into the new app's data dir → every setting, override,
   tagline, and ignore survives and is visible in the UI.
3. **Every control in §4.7** exercised at least once, and cross-checked against the same action
   in the Python build side by side.
4. **Live state** — start/close Discord; launch a game; focus Discord itself (the last app must
   persist); go idle past the timeout; pause/resume. The **Status pane** and the tray tooltip must
   both reflect reality within one poll interval.
5. **Ignore correctness** — ignore from the tray, then open Settings → Ignored Apps. **If the
   app is missing from that list, `I-5` is unresolved.**
6. **Rename** — rename the active app from the tray, confirm the Discord profile updates
   *without a restart*, confirm a blank tagline falls back to the automatic tagline.
7. **Logs** — generate a burst (rapid app switching), confirm no jank, filter to ERROR, search,
   copy the filtered view, export to a file, clear the view, then open the file.
8. **Scale** — repeat 100%, 150%, 200%. Nothing clipped, no blurry tray icon, no truncated labels.
9. **Lifecycle** — quit from the tray → process gone; close Settings → still in tray; launch a
   second instance → Settings focuses; kill the engine (Option A) → UI shows offline + recovers.
10. **Autostart** — toggle on/off, verify the real OS mechanism, reboot, verify dormant-start
    then wake-on-Discord.
11. **Accessibility** — complete onboarding and add a tagline using **keyboard only**; run a
    screen reader over Settings.
12. **Tray** — right-click menu in every state (no app detected / paused / update available /
    dormant).

---

## 11. Review gates

| Gate | Deliverable you approve | You reject if… |
|---|---|---|
| **G0 — Direction** | **CLOSED at G0.** Owner issued decisions `A1`–`A23` (see §0.1); this doc is annotated and every amendment is logged in `DECISIONS.md`. | — *(historical: direction is "we'll figure it out as we go.")* |
| **G1 — Architecture & design** | Component inventory (§8.3), state model (§7), IPC contract (§6) frozen, **token sheet for both themes with the §8.1 contrast table**, wireframes of **all surfaces in both themes** including empty, loading, and error states, and the resolved **unified ignore list** design (`A18`). | Any §4 item is unaccounted for; only one theme designed; no empty/error/loading states; IPC has no failure shapes; polling proposed; `I-5` unresolved. |
| **G2 — Shell** | Working window: sidebar nav, **Status pane with live data**, toasts, dialogs, window state restore, **no-flash open in either theme**. **Screenshots of every pane in light and dark at 100/150/200%.** System mode follows a live OS change; the Appearance choice survives a restart; the tray icon is verified on light **and** dark taskbars. | Static/mocked shell; hardcoded data; no keyboard support; flash of the wrong theme; only dark verified; a theme that doesn't follow the OS live. |
| **G3 — CRUD sections** | General, Overrides, Taglines, Ignored Apps fully functional against real config, with validation, empty states, undo, and normalization parity (`O-4`/`T-4`/`I-3`). | Normalization differs (case/`.exe` suffix); `I-5` still unresolved; modals used for success feedback. |
| **G4 — Live surfaces** | Logs (search/level/follow/copy/export/clear/cache reset) with performance evidence; tray in all states; update affordance; ignore/rename from the tray and the **Status pane**; lifecycle (close≠quit, single instance, dormant). | Log view drops frames or unbounded memory; tray menu lacks a state; close exits the app. |
| **G5 — Parity audit** | The §4.7 table filled in with evidence per row + the §10 procedure executed on Win10 and Win11 **in both themes**. **Every changed ID must carry its `DECISIONS.md` reference: `SS-1`, `SS-2`, `SS-3`, `R-1`, `OB-13`, the `SEM-*` autosave decision, and the §2 / §8.1 reversals.** | Any `MUST` row unverified; any `MODERNIZE` without a decision entry; any silent behaviour change; a changed ID with no `DECISIONS.md` reference. |
| **G6 — Ship** | Signed release, migration notes ("keep your config.json"), Python/Qt build documented as the fallback, `STATE.md`/`DECISIONS.md`/`TASKS.md` updated. | No upgrade/rollback story; docs not updated. |

**Standing instruction to give the implementer:** *"Before writing code for any section, post
the mapping from the §4 IDs it covers to the components that implement it. If an ID has no
home, stop and ask."* That single ritual prevents the most common failure mode of a UI rewrite:
the checkbox that quietly disappears.

---

## 12. Risk register (implementation-specific)

> **IDs renamed `R-*` → `RSK-*`** to remove the collision with §4.9's `R-1` (quick rename).
> Status column added at G0.

| ID | Status | Risk | Why it bites | Mitigation you enforce |
|---|---|---|---|---|
| `RSK-1` | **Closed at G0** | **Tray menu styling expectations** | The Qt menu is dark-themed; native Tauri/muda menus are OS-rendered and **cannot** be styled. | **`A22` / `D-041`: native menu, plain text.** The alternative (custom borderless webview popup) is rejected for v1. Do not allow a mid-project switch; if someone proposes it, that is a G1 scope change requiring owner sign-off. |
| `RSK-2` | Open | **Engine lifecycle (Option A)** | The UI assumes an engine that can die, be slow to start, or fail to spawn. | Define: who starts it, how the UI resyncs after restart, timeouts on every command, and an "engine offline" UI state. Test by killing the engine. |
| `RSK-3` | Open | **Close-vs-exit confusion** | A Tauri app exits when its last window closes unless configured otherwise. | Explicit test in §10.9. Tray Quit is the only exit. |
| `RSK-4` | Open | **Log throughput** | Live DEBUG streaming can flood the webview and jank the UI. | Batching + ring buffer + virtualization (`PERF-1`). Require a throughput measurement. |
| `RSK-5` | Open | **WebView2 dependency** | Modern Windows has it; stripped images may not. | Detect and show a clear "WebView2 required" message; consider the Tauri bootstrapper. **Q2 is still unanswered — settle before G1.** |
| `RSK-6` | **Closed at G0** | **Two ignore lists** (`I-5`) | Users "ignore" an app from the tray and it never shows in Settings; or they remove it in Settings and it reappears. | **`A18` / `D-037`: merge into one source of truth with migration.** The *design* must still be approved at G1, but the direction is settled. |
| `RSK-7` | **Closed at G0** | **Save semantics drift** (`SEM-3`/`SEM-8`) | Users lose edits or get blocked by unrelated validation. | **`A12` / `D-031`: autosave, no Save button, per-field error isolation.** Test explicitly: an invalid App ID **must not** block a tagline edit. |
| `RSK-8` | Open | **Window sizing / DPI** | Fixed-size Qt windows translated to fixed-size webviews break at 200%. | `minWidth/minHeight` (820×560), responsive layout, DPI matrix in §10.8, screenshots at three scales (G2). |
| `RSK-9` | Open | **Security scope creep** | A dev "just needs" `fs:allow-write` to export logs and grants it globally. | `SEC-2` is a hard rejection reason. Log export and `ui_prefs.json` are backend commands. |
| `RSK-10` | **Closed at G0** | **Emoji/icon inconsistency** | Emoji render per Windows font version; users on older builds see tofu. | **`A2` / `D-021`: emoji and glyph icons banned.** One icon library, one size, verified on Win10 + Win11 (`UI-1`). |
| `RSK-11` | Open | **Unsigned binary / SmartScreen** | Users get a scary prompt on a new download. | Budget decision (Q8). Publish checksums at minimum; signing before any auto-update. |
| `RSK-12` | Open | **Scope drift into the engine** | "While we're in here, let's also rewrite detection in Rust." | §2 out-of-scope list is a rejection reason. |
| `RSK-13` | **New at G0** | **Theme flash / half-themed UI** | The classic failure of a two-theme webview app: a white flash on open, or a component that hard-codes a colour and only looks right in one theme. | `THEME-3`, `FONT-1`, §8.1 rule 1 (no hard-coded colours). Audit components in **both** themes at G2; a hard-coded colour is a rejection reason. |
| `RSK-14` | **New at G0** | **Autosave writes too eagerly** | Autosave + a debounced stepper can spam writes, and a partially typed value could be committed. | Debounce steppers; commit text on blur/`Enter` only; atomic writes; rollback on failure. Test rapid typing in the App ID field and a held stepper arrow. |

---

## 13. Questions to put to the owner

| # | Status | Question | Why you need it |
|---|---|---|---|
| **Q1** | **ANSWERED — `D-043`** | **Engine location:** Tauri + Python sidecar (Option A), or Rust engine (Option B)? | **Option A.** Tauri shell + the existing Python engine as a stdio JSON-lines sidecar. The frontend is written against the IPC contract only, so a later move to a full Rust engine cannot force a UI rewrite. Phase-1 shell runs a mock until `T-022` adds `--engine-stdio`. |
| **Q2** | **OPEN** | Is a **WebView2** runtime requirement acceptable on the machines you support? | Gates the entire Tauri choice (`RSK-5`). **This dev machine has it** (`155.0.4283.62`, seen under `HKLM\SOFTWARE\WOW6432Node\...\{F3017226-...}`), so the runtime question is about *end users*, not about whether the shell can run here. |
| **Q3** | **ANSWERED — `D-048`** | App ID length: the check allows **17–21** digits but the error says **17–20**. Which is correct? | **17–21**, in the check *and* the copy. Implemented in `desktop/src/lib/validation.ts` and `config_file::is_valid_app_id`; the Python string is left alone (`B-12`). |
| **Q4** | **ANSWERED — `D-044`** | Onboarding **Cancel** currently exits the app. Keep that, or offer "continue without connecting"? | **"Continue without connecting"** — the button reads **Set up later**, the app keeps running unconfigured, and the tray stays functional. |
| **Q5** | **ANSWERED — `D-045`** | Should `poll_interval`, `whitelist_only`, `upload_host`, and `steamgriddb_api_key` become **visible UI** (advanced section) or stay config-only? | **Visible**, in an **Advanced** group at the end of General. `D-035` is confirmed, its provisional note resolved. |
| **Q6** | **ANSWERED — `A18` / `D-037`, refined by `D-047`** | **One ignore list or two?** (`config.ignored_exes` vs `ignore_list.json`) | Merged. The verified model: **`config.ignored_exes` is the one store** (it already holds the shipped twelve and is what the Python pane wrote); the tray folds `ignore_list.json` into it on startup and anything left over is shown, never hidden. |
| **Q7** | **OPEN** | Should a **single click** on the tray icon open Settings, or only double-click? | Current behavior is single-click; it can feel accidental on Win11. **Phase 1 keeps single-click** (`TR-14`). |
| **Q8** | **OPEN** | Is there a **budget for code signing**? | SmartScreen friction and whether self-update is ever viable (`RSK-11`, `T-017`). |
| **Q9** | **ANSWERED — `A15` / `D-034`** | Does a live status surface (live presence + diagnostics) match the product vision? | Yes — shipped as the **Status** landing pane. The "why this tagline?" disclosure is deferred. |
| **Q10** | **ANSWERED — `A3` / `D-022`** | Which **native Windows visual**: Mica/acrylic on Win11, or a flat surface everywhere? | **Solid surfaces only in v1**; no vibrancy, glass, or gradients. Mica is optional later. |

> **All G1 entry requirements are now answered (Q1, Q3, Q4, Q5).** Q2, Q7, and Q8 remain open and
> do not block the design package.

---

## 14. Definition of done

- [ ] Every `MUST` row in §4.7 is implemented and verified with evidence.
- [ ] Every `MODERNIZE` row is either implemented or has an entry in `DECISIONS.md`.
- [ ] Every `DROP` is explicitly signed off by the owner.
- [ ] **All `A1`–`A23` amendments (§0.1) are implemented or explicitly deferred, each with its
      `DECISIONS.md` entry cited at G5.**
- [ ] §10 executed on Windows 10 **and** Windows 11, **in both light and dark**.
- [ ] **No emoji or glyph-as-icon characters anywhere** (`UI-1`); **no glass, gradients, or fake
      transparency** (`UI-2`); **native window decorations retained** (`UI-3`).
- [ ] **Appearance (`System`/`Light`/`Dark`) follows the OS live, persists across restart in
      `ui_prefs.json`, keeps the native frame in sync, and never flashes the wrong theme**
      (`THEME-1`…`THEME-5`).
- [ ] §6 IPC contract frozen and implemented with error shapes on every command.
- [ ] No success path uses a blocking modal; no component polls; no frontend filesystem access.
- [ ] **No Save button exists**; an invalid field never blocks another field's save (`A12`).
- [ ] Keyboard-only completion of onboarding + tagline creation; screen-reader pass on Settings.
- [ ] Log view sustains its target rate with bounded memory (measurement attached).
- [ ] A Python-build `config.json` + caches migrate invisibly.
- [ ] `AGENTS.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md` updated for the new architecture, and
      the retired Qt/Python GUI recorded as superseded (with the reason, for future sessions).
- [ ] Migration + rollback notes shipped to users: *"Your settings carry over unchanged. The
      previous build remains available."*

---

*End of handoff. No code has been modified. The **§0.1 G0 decisions are authoritative** and
supersede any conflicting text above. Next action: answer **Q4** and **Q5** (§13), then approve
or reject the G1 architecture package — which must include the both-theme token sheet, the
wireframes in both themes, and the unified ignore-list design.*
