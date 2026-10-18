# COMPONENT_MAP.md — §4 ID → component mapping (RULE-1 ritual)

> **Required by `GUI_HANDOFF_TAURI_REACT.md` §11.** Before writing code for a section, the
> implementer posts the mapping from the §4 requirement IDs it covers to the components that
> implement it. If an ID has no home, stop and ask.
>
> **Scope of this map:** Phase 1 (this pass) — the Tauri shell, the design system, all six
> Settings panes, onboarding, and the tray. Phase 2 items are marked `P2` and are tracked in
> `TASKS.md`. Every ID below is accounted for; nothing is silently dropped.
>
> **Paths are relative to `desktop/`.**

## Legend

| Mark | Meaning |
|---|---|
| `P1` | implemented in this pass |
| `P2` | deferred to the next pass, with the task id that owns it |
| `DROP` | deliberately dropped at G0 — cited decision |

---

## 0. Shell & lifecycle — `SH-*`

| ID | Implementing component | Status |
|---|---|---|
| `SH-1` | `src/mount.tsx` (one bundle, three entry points: `index.html` / `onboarding.html` / `rename.html` — `D-049`), `src-tauri/src/windows.rs` | `P1` |
| `SH-2` | `src-tauri/src/windows.rs::open_settings` (singleton focus, never duplicate) | `P1` |
| `SH-3` | `src-tauri/src/windows.rs::open_settings` (980×700, min 820×560) + `tauri-plugin-window-state`, restored **size / position / maximized only** — `decorated`, `visible` and `fullscreen` are the app's to decide (`D-055`) | `P1` |
| `SH-4` | hidden start → `src/lib/boot.ts` → `invoke("ready")` → `src-tauri/src/windows.rs::apply_theme` + `show_with_theme` (see `D-046`) | `P1` |
| `SH-5` | `tauri-plugin-single-instance` callback in `src-tauri/src/main.rs` → `windows::open_settings` | `P1` |
| `SH-6` | hidden window while broadcasting is paused (tray stays up) — **not built**: the sidecar exists now (`D-057`), the hiding itself is its own task | `P2` — `T-027` |
| `SH-7` | `src-tauri/src/tray.rs::sync` (tooltip + menu text follow engine state) | `P1` |
| `SH-8` | `src/panes/StatusPane.tsx` offline/unconfigured states + `toast(…, { kind: "error" })` | `P1` |
| `SH-9` | windows are owned by `windows.rs`; closing Settings **hides** it and the process stays in the tray (`main.rs` close guard + `ExitRequested` guard, `D-054`), so `TR-13` is the only full exit | `P1` |
| `SH-10` | **frameless chrome** (owner directive 2026-10-18, `D-055` — supersedes `A1`'s "native Windows frame"): `src/shell/TitleBar.tsx` + `src/components/WindowControls.tsx`, drag regions in `Sidebar` and `StatusHeader`, and `windows.rs::strip_caption`, because tao keeps `WS_CAPTION` even with `decorations(false)` and re-applies it on every flag change | `P1` |

## 1. Onboarding — `OB-*` → `src/windows/Onboarding.tsx`

| ID | Implementing piece | Status |
|---|---|---|
| `OB-1` | `Onboarding` entry point (`onboarding.html`), single centred column, max-width 600 | `P1` |
| `OB-2` | `Onboarding` step 1 header copy — emoji stripped (`D-021`) | `P1` |
| `OB-3` | step 1 `Button variant="primary"` → `invoke("open_url", portal)` | `P1` |
| `OB-4` | step 1 numbered sub-steps (`<ol class="steps">`) | `P1` |
| `OB-5` | step 3 `TextField` with `normalizeAppId()` (trim, strip URL, digits-only) | `P1` |
| `OB-6` | `useDebounced(…, 250)` — the error appears only once the debounced value is >1 char | `P1` |
| `OB-7` | `src/lib/validation.ts::validateAppId` — matches `config.validate_app_id`, **17–21** (`D-048`) | `P1` |
| `OB-8` | `Switch` → `invoke("set_autostart")` (`tauri-plugin-autostart`) | `P1` |
| `OB-9` | `Switch` → `config.auto_close_with_discord` | `P1` |
| `OB-10` | `Button variant="quiet"` labelled **"Set up later"** → closes the window, app stays running unconfigured (`Q4` answered) | `P1` |
| `OB-11` | step 3 finish → `invoke("set_config")` then `invoke("test_connection")` | `P1` |
| `OB-12` | step 3 `StatusPill` result row + "Not connected yet" empty state (Discord not running / rejected ID) | `P1` |
| `OB-13` | 3-step dot stepper with Back/Continue (`onboard__steps` in `src/windows/Onboarding.tsx`) | `P1` |
| `OB-14` | `GeneralPane` → Discord group → "Re-run setup" button | `P1` |

## 2. Settings shell — `SS-*`

| ID | Implementing component | Status |
|---|---|---|
| `SS-1` | `src/shell/Sidebar.tsx` + `src/shell/SettingsWindow.tsx` (6 panes) | `P1` |
| `SS-2` | **not implemented** — autosave, no Save button (`D-031`) | `DROP` |
| `SS-3` | `useSectionShortcuts()` (Ctrl+1…6) + `useEscape()`; no palette (`D-030`) | `P1` |
| `SS-4` | `src/shell/StatusHeader.tsx` (persistent live status strip) — doubles as the window's toolbar: it carries the drag region and `WindowControls`, so Settings has one bar and not two (`D-055`) | `P1` |
| `SS-5` | the window title lives in `src-tauri/src/windows.rs` (`tauri.conf.json` declares no windows, `D-049`); it is what the taskbar shows, while the visible caption belongs to the frontend (`D-055`) | `P1` |

## 3. General pane — `G-*` → `src/panes/GeneralPane.tsx`

| ID | Implementing piece | Status |
|---|---|---|
| `G-1` | Discord group: `AppIdField` (inline validation, shared with onboarding) + "Test connection" | `P1` |
| `G-2` | Behaviour group: `Switch` ← `auto_close_with_discord` | `P1` |
| `G-3` | Behaviour group: `Switch` bound to `invoke("get_autostart")` (real OS state) | `P1` |
| `G-4` | Behaviour group: `Switch` ← `mask_private_browsing`, never defaulted off | `P1` |
| `G-5` | Behaviour group: `Switch` ← `enable_dynamic_taglines` + hint and example | `P1` |
| `G-6` | Timing group: `NumberField` 2–60 s + trade-off note | `P1` |
| `G-7` | Timing group: `NumberField` 10–600 s + note | `P1` |
| `G-8` | Advanced group: `NumberField` 1–60 s ← `poll_interval` (`Q5` answered: visible) | `P1` |
| `G-9` | Advanced group: `Switch` ← `whitelist_only` + `InsetList` for `whitelist` + warning | `P1` |
| `G-10` | Advanced group: `Select` ← `upload_host` + privacy disclosure text | `P1` |
| `G-11` | Advanced group: masked `TextField` ← `steamgriddb_api_key`. **"Test key" is `P2`** — the check is an HTTP call that belongs on the engine side (`D-051`) | `P1`/`P2` |
| `G-12` | Reset group: danger `Button` → `ConfirmDialog` with "Export config first" | `P1` |

## 4. App Names & Overrides — `O-*` → `src/panes/AppNamesPane.tsx`

| ID | Implementing piece | Status |
|---|---|---|
| `O-1` | pane description line | `P1` |
| `O-2` | `InsetList` (filter above, `+`/`−` bar below, popover add, `Delete` key, undo toast) | `P1` |
| `O-3` | `OverridesAddForm` inside `Popover`; exe suggestions from `state.recentApps` | `P1` |
| `O-4` | `src/lib/validation.ts::normalizeExeKey` (lowercase + `.exe`) — contract, not style | `P1` |
| `O-5` | `InsetList` remove + `ConfirmDialog` on multi-delete; single delete undoable via toast | `P1` |
| `O-6` | autosave — each row commits through `updateConfig({ overrides })` / `invoke("rename_app")`, returning the written map | `P1` |
| `O-7` | `RowPreview` showing resolved icon + display name | `P1` |
| `O-8` | `OverridesAddForm` icon-URL field, validated (`https:`, ≤255 chars) | `P1` |
| `O-9` | unknown-exe warning (`warn` kind, non-blocking) | `P1` |

## 5. Taglines — `T-*` → `src/panes/TaglinesPane.tsx`

| ID | Implementing piece | Status |
|---|---|---|
| `T-1` | pane description line | `P1` |
| `T-2` | `InsetList` (same pattern as `O-2`) | `P1` |
| `T-3` | `TaglinePreviewChip` inside the add popover | `P1` |
| `T-4` | `normalizeExeKey` (shared) | `P1` |
| `T-5` | `InsetList` remove + undo toast | `P1` |
| `T-6` | `Built-in taglines` group fed by `invoke("get_built_ins")`, which answers from the engine's `builtins` line cached in `sidecar.rs` — the table stays single-sourced in `detector.py::_BUILTIN_TAGLINES` (`D-057`) | `P1` |
| `T-7` | `PrecedenceNote` one-liner above the list | `P1` |
| `T-8` | character counter, warns past 128 | `P1` |

## 6. Ignored Apps — `I-*` → `src/panes/IgnoredAppsPane.tsx`

| ID | Implementing piece | Status |
|---|---|---|
| `I-1` | pane description line | `P1` |
| `I-2` | `InsetList` with filter + per-row remove | `P1` |
| `I-3` | `normalizeExeKey` + dedupe | `P1` |
| `I-4` | `InsetList` remove → `invoke("unignore_app")` | `P1` |
| `I-5` | `src-tauri/src/ignore_store.rs` — **one store**: `config.ignored_exes`, written by the tray and the pane, with any `ignore_list.json` leftovers folded in on startup (see `D-047`) | `P1` |
| `I-6` | the shipped twelve are tagged *shipped default* in the same editable list, and `%SystemRoot%` is stated in prose as the only non-removable rule (`D-047` corrects the original "read-only group" wording) | `P1` |
| `I-7` | `SystemRootNote` hint line | `P1` |
| `I-8` | `StatusPane` → "Ignore this app" button writing the same store | `P1` |

## 7. Logs — `L-*` → `src/panes/LogsPane.tsx`

| ID | Implementing piece | Status |
|---|---|---|
| `L-1` | pane header + description | `P1` |
| `L-2` | `FollowToggle` with auto-pause on manual scroll + "Jump to latest" | `P1` |
| `L-3` | `Button` "Copy" (visible lines) → clipboard, toast | `P1` |
| `L-4` | `Button` "Export…" → `invoke("export_logs")`; the backend copies into `<data dir>\exports\` and the toast names the path. Native save dialog is `P2` — `T-024` (`D-051`) | `P1`/`P2` |
| `L-5` | `Button` "Clear View" (labelled view-only) | `P1` |
| `L-6` | `Button` "Reset Icon Cache" → `ConfirmDialog` + count | `P1` |
| `L-7` | 200-line seed via `invoke("seed_logs")` + live `log` events | `P1` |
| `L-8` | `LogLine` structured fields (ts, level, logger, message) | `P1` |
| `L-9` | `SegmentedControl` minimum level (Debug/Info/Warning/Error) with counts | `P1` |
| `L-10` | `SearchInput` + `<mark>` highlighting + match count, Enter/Shift+Enter stepping | `P1` |
| `L-11` | **not built** — detection digest (`D-038`) | `DROP` |
| `L-12` | `Button` "Open folder" → `invoke("open_log_folder")` | `P1` |

## 8. Quick rename — `R-*` → `src/windows/QuickRename.tsx` + `src/components/RenameForm.tsx`

| ID | Implementing piece | Status |
|---|---|---|
| `R-1` | standalone window (`rename.html`) **and** `Sheet` on the Status pane, sharing `RenameForm` | `P1` |
| `R-2` | `RenameForm` header copy | `P1` |
| `R-3` | display-name `TextField` + live `Playing <name>` preview | `P1` |
| `R-4` | tagline `TextField`, placeholder "Leave blank to keep automatic" | `P1` |
| `R-5` | `Button variant="secondary"` Cancel | `P1` |
| `R-6` | inline validation ("Display Name cannot be empty") | `P1` |
| `R-7` | `invoke("rename_app")` → writes override, applies live, toast | `P1` |
| `R-8` | recent-app picker in `RenameForm` | `P1` |

## 9. Tray — `TR-*` → `src-tauri/src/tray.rs`

| ID | Implementing piece | Status |
|---|---|---|
| `TR-1` | the bundled app icon (`icons/icon.ico`, multi-res), with `icons/icon.png` and a solid fallback if the icon cannot be decoded (`D-029`) | `P1` |
| `TR-2` | grey pause variant **generated at runtime** by desaturating the app icon (`tray.rs::desaturate`), swapped on state change — `D-052` | `P1` |
| `TR-3` | `TrayIconBuilder::tooltip` / `TrayIcon::set_tooltip` states | `P1` |
| `TR-4` | disabled version header item. The "Update to vX" item is `P2` — `T-024` (`D-051`): it appears only when a real check has something to say | `P1`/`P2` |
| `TR-5`/`TR-7`/`TR-11` | `PredefinedMenuItem::separator()` | `P1` |
| `TR-6` | Settings item → `windows::open_settings` | `P1` |
| `TR-8` | rename item, relabelled pre-open, disabled when no app | `P1` |
| `TR-9` | Pause/Resume item, plain text, clears presence | `P1` |
| `TR-10` | Ignore item → writes the unified store (`D-047`) | `P1` |
| `TR-12` | Open log → `tauri-plugin-opener` | `P1` |
| `TR-13` | Quit — the only full exit | `P1` |
| `TR-14` | left-click opens Settings (kept; `Q7` still open) | `P1` |
| `TR-15` | `set_enabled(false)` on rename/ignore when nothing detected | `P1` |
| `TR-16` | read-only tooltip line with current app | `P1` |

## 10. Feedback — `FB-*`

| ID | Implementing piece | Status |
|---|---|---|
| `FB-1` | `src/components/Toast.tsx` — bottom-centre pill, Undo, `aria-live="polite"` (`D-033`) | `P1` |
| `FB-2` | no `Dialog.exec` equivalents; `Dialog` is non-blocking React state | `P1` |
| `FB-3` | undo tokens on single-row deletes and "ignore app" | `P1` |
| `FB-4` | `src/shell/ErrorBoundary.tsx` | `P1` |

## 11. Save semantics — `SEM-*`

| ID | Implementing piece | Status |
|---|---|---|
| `SEM-1` | `Onboarding` finishes with `set_config` + verification | `P1` |
| `SEM-2` | `rename_app` applies live | `P1` |
| `SEM-3` | replaced by autosave — `src/state/config.ts::updateConfig()` (optimistic + rollback) is the single commit helper | `P1` |
| `SEM-4` | tray ignore and pane write the same store (`ignore_store.rs`) | `P1` |
| `SEM-5` | autostart toggle writes then re-reads the OS state | `P1` |
| `SEM-6` | every mutation emits `config-changed`, and every config write is followed by `reload_config` so the engine rebuilds its detector from the new file (`D-057`) | `P1` |
| `SEM-7` | `config-changed` handler merged into the store without clobbering focused fields | `P1` |
| `SEM-8` | per-field validation; an invalid App ID never blocks another field | `P1` |

## 12. Cross-cutting requirements

| Requirement | Where |
|---|---|
| `UI-1` no emoji/glyph icons | enforced by review; `lucide-react` icons only |
| `UI-2` no glass/gradients | `src/styles/tokens.css` (solid values only) |
| `UI-3` native decorations | **superseded by `D-055`** (owner directive): all three windows are `decorations(false)` with frontend-drawn chrome, and `windows.rs::strip_caption` removes the Win32 caption tao keeps |
| `FONT-1` bundled fonts | `@fontsource-variable/inter`, `@fontsource/cascadia-code` |
| `THEME-1…6` | `src/lib/theme.ts`, `src-tauri/src/prefs.rs`, `tokens.css`, `windows.rs` |
| `A11Y-1…4` | focus rings, `role="switch"`, `aria-label` on icon buttons, `aria-live` |
| `PERF-1` log throughput | `src/state/logs.ts` (ring buffer + rAF-batched notify); measurement is `P2` — `T-023` |
| `SEC-1`/`SEC-2` | `tauri.conf.json` CSP (`script-src 'self'`, no inline script); the frontend imports **no** Tauri API and the capability set is `core:default` only; clipboard, filesystem, prefs and exports are backend commands (`D-049`) |
| `DPI-1` | responsive layout, matrix verification is `P2` — `T-023` |

---

## Deferred (explicit, with owner)

| ID / item | Why | Owner |
|---|---|---|
| `L-11` detection digest | `D-038` — deferred at G0 | owner |
| "why this tagline?" disclosure | `A15` — deferred at G0 | owner |
| Mica / vibrancy | `D-022` — optional later | owner |
| `SH-6` dormant tray hiding | the sidecar is real now (`D-057`); the hiding itself is its own task | `T-027` |
| Native save dialog for Export / Export logs | keeps the plugin surface minimal until the engine seam is real; exports land in `<data dir>\exports\` and the toast names the path | `T-024` (`D-051`) |
| Tray "update available" item (`TR-4`) | needs a real update check; the version header is already there | `T-024` (`D-051`) |
| Built-in tagline list (`T-6`) | **delivered** by `D-057`: the engine serves the table over the protocol, so it stays single-sourced in `detector.py` | `D-057` |
| SteamGridDB "Test key" (`G-11`) | an HTTP call that belongs on the engine side; the seam exists (`D-057`), the command does not | `T-029` |
| Icon extraction / upload / presence itself | **delivered** by `D-057`: the engine owns GDI, uploads and the Discord IPC connection, driven by `sidecar.rs` | `D-057` |
| `config.json` defaults mirrored in Rust | Phase-1 duplication, tracked so it cannot rot silently | `T-025` (`D-053`) |
| Verify `rename.html` / `onboarding.html` on a real build | routing is by entry point now, not by hash | `T-023` |
