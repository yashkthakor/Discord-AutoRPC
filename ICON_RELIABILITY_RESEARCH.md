# Icon reliability — research and proposal

> **Status:** accepted by the owner and implemented (2026-10-18, `bd2543e`, decision `D-058`).
> The answers to §7 are recorded there. `S4` (trusted-host revalidation) and `S5`/`E1`
> (packaged-app icons via the Explorer route) remain gated on measurement and the `T9` probe.
> **Owner request:** *"when the app detects that the icon isn't visible or it's falling back to the
> default icons, it instead tries at least 3 times to fetch the icon from the current mechanism, and
> only after that if it fails, it reverts to the default. also implement a system in the settings of
> the app where the user can individually clear the icon cache for an app."*
>
> **Scope:** (1) recovering from a failed icon fetch without showing the default for the rest of the
> session; (2) clearing **one** app's icon without throwing away the whole `icon_cache.json`.
> **Tracking:** `TASKS.md` `T-030` (blocked on the questions in §7).

---

## 1. How the pipeline works today

`icons.get_icon_url(exe_path, display_name, config)` (`icons.py:385`) resolves in this order:

1. **Override** — `overrides[<exe>].icon_url`, validated (`icons.py:399`, `_validate_icon_url`
   `icons.py:338`).
2. **Cache** — `icon_cache.json[<exe lower>]`, validated (`icons.py:406`).
3. **SteamGridDB** — only with a key; validated, then cached (`icons.py:412`).
4. **Extract + upload** — `_extract_icon_image` (`icons.py:66`) → PNG → `_upload_png`
   (`icons.py:258`, configured host first then the other one, 20 s timeout each) → cached
   immediately and validated after (`icons.py:434`).
5. **Default** — `config.default_icon_url` (`icons.py:445`). **Not cached**: the next call re-enters
   the whole pipeline.

Call sites: `main.py:265` (tray build, every loop iteration — `time.sleep(poll_interval)` at
`main.py:276`) and `engine_stdio.py:366` (`_tick`, every cycle). **Resolution therefore runs on every
poll — 5 s by default — for whatever app is focused, not only when the app changes.**

### Findings that change the shape of the request

| # | Finding | Evidence |
|---|---|---|
| F1 | **"3 retries" already happen accidentally — unbounded.** A failing app is re-extracted and re-uploaded every poll. The problem is not too few attempts, it is *invisible, unlimited* attempts (public-host abuse) with no backoff and no negative cache. | `main.py:265`, `engine_stdio.py:366`; no attempt state anywhere in `icons.py` |
| F2 | **Failures are invisible at INFO.** Upload failures log at DEBUG (`icons.py:223`, `247`); the fallback line names the app but not the reason (`icons.py:446`). Nothing counts attempts. | the log only ever says `Using default icon for …` |
| F3 | **A dead cached URL never self-heals.** `_validate_icon_url` trusts any `_TRUSTED_IMAGE_HOSTS` host + image extension with **no probe** (`icons.py:348`), so a catbox/freeimage URL that has since been deleted is returned forever. The global reset is the only fix today — the most likely cause of "sometimes the icon just disappears". | `icons.py:326`, `338` |
| F4 | **A slow fetch can shift the Discord timer.** The presence start epoch is stamped inside `update()` (`presence.py:151`), i.e. *after* icon resolution. A retry ladder that takes 40 s would start Discord's counter 40 s late, disagreeing with the pane's own "Detected at". | `presence.py:96`, `151` |
| F5 | **An icon upgrade after a fallback does land.** The dedupe key includes `icon_url` (`presence.py:138`) and a rate-limited call does not update `_last_sent_key` (`presence.py:144`), so the next tick after the 15 s window re-sends. No `force` bypass is needed (`D-057` rejected one). | `presence.py:138`, `148` |
| F6 | **Untrusted override hosts are probed every tick.** Any override `icon_url` not in `_TRUSTED_IMAGE_HOSTS` gets a ranged GET every 5 s, forever. | `icons.py:353` |
| F7 | **The cache file has two writers and is written non-atomically.** The engine does `open(..., "w")` (`icons.py:48`); the shell counts then `remove_file`s it (`commands.rs:274`) and reads it raw (`commands.rs:328`). | — |
| F8 | **The UI memoizes icon URLs for the window's lifetime**, so any "clear/refresh" must invalidate that memo or the old URL keeps rendering. | `desktop/src/lib/icons.ts:13` |

---

## 2. Failure taxonomy — what "can't fetch the icon" actually is

| Class | Cause | Behaviour today | Self-heals? |
|---|---|---|---|
| **A. Transient upload failure** | host hiccup, brief network drop | default this tick, retried next tick | yes, ≤ ~20 s (F5) |
| **B. Persistent upload failure** | host blocked or rate-limited (firewall, freeimage's shared key — `B-5`), offline | default forever, **re-uploads every 5 s** | no |
| **C. No icon resource** | UWP/packaged apps, icons that live in a DLL, launchers, protected processes | default forever, **re-extracts every 5 s** | never (hard failure) |
| **D. Dead cached URL** | the host deleted the file after the entry was written | dead URL returned forever (F3) | only via the global reset |
| **E. Dead override URL** | a user-supplied URL broke | falls through to cache/extract (good), but probes every tick (F6) | per call |

### What the retained log actually shows (measured 2026-10-18)

| App | Fallbacks | Mechanism lines found | Interpretation |
|---|---|---|---|
| `WhatsApp.Root` (`…\WindowsApps\…WhatsAppDesktop…\WhatsApp.exe`) | **117** (114 on 2026-10-12, 3 today) | 117 × `No icon found in …` | **class C, ongoing** — a packaged/MSIX app whose exe has no icon resource. Retries cannot fix it, nothing is cached for it, so the per-app clear cannot either. |
| `Antigravity IDE` | **68**, all inside a 13-minute window on 2026-10-12 (12:05–12:18), never again | **none at all** | cause unattributed — the retained log has *no* line for it (F2: upload failures are DEBUG-only, and that window predates some of the current code). Exactly the blind spot S1 removes. |
| `Notion` / `Zen` | 5 / 3 | extraction/upload successes nearby | ordinary A/B blips that self-healed (F5). |

`icon_cache.json` currently holds **17 entries**. There are no rotated log backups, so this is the
entire retained history.

Two conclusions follow: (1) the user-visible symptom on *this* machine is dominated by **C**, which
neither retries nor cache clearing can fix — it needs an override icon or a new extraction route
for packaged apps (option E1 in §3); (2) every class needs S1 first, because the current log cannot
even explain one of the two measured cases.

---

## 3. Proposal A — staged, bounded retries

**Semantics** (per exe, in memory, per process lifetime):

- **3 attempts** per app: attempt 1 inline; attempts 2 and 3 on the following ticks, with minimum
  gaps of 1 s and 3 s.
- A tick budgets **≤ ~6 s total** for icon work — retry attempts use a shorter per-host timeout
  (~4 s instead of 20 s). Extraction is local and fast when it works. The rest of the ladder runs
  on later ticks, so detection cadence never slips by more than that.
- Failures are classified:
  - **hard** — extraction found nothing, or the path is unreadable → 3 quick attempts, then park
    the exe for 30 minutes; one WARNING: `No icon resource in <exe> — default icon until <time>`.
  - **soft** — network / host failures → 3 attempts, then a cooldown ladder
    **60 s → 5 min → 30 min** (capped). Reset by a process restart, or by the user's refresh.
- Re-focusing an app does **not** reset the ladder (otherwise alt-tabbing becomes a retry storm).
- Every failed attempt logs at WARNING with the stage, host and error; the park logs at INFO.

**Where:** a small module-level state machine in `icons.py` (`_attempts: dict[str, _Attempt]`,
in-memory, never persisted), so both entry points inherit it with **zero loop changes** — they
already call `get_icon_url` every tick. Public surface:

```python
def get_icon_url(exe_path, display_name, config) -> str   # unchanged signature; default when parked
def icon_state(exe_path: str) -> str                     # "ok" | "pending" | "parked" | "default"
def clear_icon_cache(exe_paths: Sequence[str] | None = None) -> int   # None = everything
def cached_icons() -> list[dict]                         # [{"exe": "zen.exe", "url": "…"}]
```

**Option E1 — packaged (MSIX/Store) apps.** Measured above: WhatsApp Desktop's exe carries no icon
resource, so `PrivateExtractIconsW` *and* `ExtractIconEx` both come up empty — no amount of
retrying helps. The icon exists (as a PNG in the package's `Assets\` folder) and Explorer displays
it. Options, cheapest first: **(a)** keep pointing users at an override `icon_url` (works today);
**(b)** ask the shell for the icon the way Explorer does — `IShellItemImageFactory::GetImage` on the
exe path, or `SHGetFileInfo` with `SHGFI_ICON` — which resolves packaged-app icons through package
registration; **(c)** read the package logo from `…\WindowsApps\…\Assets\` — fragile: that directory
is ACL-restricted and package paths are version-stamped. Recommendation: a 30-line probe of **(b)**
against WhatsApp *before* designing anything; it is the only option that needs no user action.
**Out of scope for the retry request, but it is the measured dominant failure on this machine.**

**Honest note:** compared with today, an app stuck in class B/C goes from ~720 attempts/hour to
≤ 3 + 3/hour — that is a *reduction* in attempts, while making the three fast attempts real,
ordered and visible. If "keep retrying every tick like today" is preferred over a park, the rungs
can be short instead (20 s / 60 s / 5 min) — see §7 Q2.

**Timer fix (S1, worth doing regardless):** stamp `presence.start_epoch(exe, pid)` the moment the
detector confirms the app, *before* icon resolution, in both entry points (`main.py:264` region,
`engine_stdio.py:366` region). The pane's "Detected at" and Discord's counter then agree even while
a ladder is running.

---

## 4. Proposal B — per-app icon cache management

**Engine (`icons.py`)**

- `clear_icon_cache(exe_paths=None)` — selective clear; the existing global call sites (`gui.py:920`,
  the shell) keep working.
- `cached_icons()` — rows for the settings list (`exe`, `url`).
- `icon_cache.json` stays `{exe: url}` **strings** in v1 — no format change, no migration (T5).

**Protocol (`engine_stdio.py` ↔ `sidecar.rs`, per `D-057`)**

- shell → engine: `{"cmd": "clear_icon_cache", "exePaths": ["zen.exe"]}` (`null`/absent = all).
- engine → shell: `{"type": "icon_cache", "entries": [{"exe": "zen.exe", "url": "…"}]}` answering
  `{"cmd": "get_icon_cache"}`, plus the usual `log` / `toast` feedback.
- `_handle` only records the request (`self._pending_icon_clear`); the **loop thread** applies it at
  the top of `_tick` — the same "record intent, the loop owns state" rule the other commands follow
  (`engine_stdio.py:259`).
- Why the engine and not Rust: `icon_cache.json` is written by the engine on every new icon (F7).
  Routing clears through the engine keeps the one-writer-per-file rule and avoids a
  delete-while-writing race. When the engine is not running (mock/offline), the shell keeps its
  current direct-file path for "clear all" and reports the limitation for per-app clears.

**Shell (`commands.rs`)**

- `clear_icon_cache(exe_keys: Option<Vec<String>>)` — forwards to the sidecar when connected, else
  falls back to the file path; returns the count.
- `icon_cache_listing()` — new, for the settings list.
- `app_icon_url` (`commands.rs:311`) unchanged.

**Frontend (`desktop/src`)**

- `src/lib/icons.ts`: add `invalidateAppIcon(exe)` (`cache.delete`) — F8.
- **Status pane** card: a **Refresh icon** action beside Pause / Rename / Ignore — the direct fix
  for the reported symptom (current app, one click).
- **Logs pane**: the existing "Reset icon cache" button (`LogsPane.tsx:206`) opens a management
  dialog instead of resetting immediately — a searchable list of cached apps, per-row **Clear**,
  and **Clear all**. Destructive, so it stays an alert dialog (`A1` / `D-028`).
- **App Names pane** (optional): "Clear icon" on each row that has an override.
- **Tray** (optional): "Refresh icon for current app", mirroring Rename/Ignore (`D-054`).

**Qt build (`gui.py`)** — `_reset_icon_cache` (`gui.py:919`) is global-only and lives in the Logs
tab. Per `AGENTS.md` new UI work belongs in `desktop/`, but the Qt build is what users run today;
extending it to "clear the selected app's icon" is ~30 lines (a combo built from `cached_icons()` +
`clear_icon_cache([selected])`). **Decision needed — §7 Q1.**

---

## 5. Tradeoffs to measure

| # | Tradeoff | How to measure | Decision threshold |
|---|---|---|---|
| **T1** | **Host load / retry volume.** The current code is already heavy on failure (F1); the ladder must guarantee 3 real attempts without being *more* aggressive than today. | Count `_upload_png` attempts per app per hour with a blackholed host (harness against `_upload_png`); watch freeimage's shared-key responses for 429/5xx (`B-5`). | ≤ 3 attempts + 3/hour per stuck app; no 429 bursts. |
| **T2** | **Poll-loop latency.** A ~6 s icon budget vs a 5 s `poll_interval` means a sustained failure can stretch the loop — app-switch detection and the Discord-lifecycle check ride on it. | Time `get_icon_url` per tick with a dead host and with a warm cache; compare the loop's real cadence via `App confirmed` timestamps in the log. | Failure adds ≤ ~1 tick; the normal path (cache hit, trusted host) stays < 5 ms. If a tick can exceed the interval, shrink the budget to ~3 s and let the ladder span more ticks. |
| **T3** | **Recovery time vs host load.** Today a transient outage recovers in ≤ 20 s; a parked app waits for the rung. | Simulate a 10 s outage, restore, measure time to the real icon with the ladder active. | ≤ 60 s acceptable; else make the first rung 20–30 s. |
| **T4** | **Does Discord re-render a changed `large_image` mid-activity?** If not, "publish default, upgrade later" stays invisible until the next app switch, and attempt 1 must finish *before* the first publish. | Live test: publish with the default, update with a real icon 10 s later, watch the profile card. | If Discord only refreshes on activity change, keep attempt 1 inline (bounded ≤ ~3 s) and treat upgrades as best-effort. |
| **T5** | **Cache metadata.** A per-app list is nicer with `cached_at` / `source`, but turning values into objects **breaks older builds** — `_validate_icon_url` would call `urlparse()` on a dict (`icons.py:345`) and crash the poll loop. | Not measurable; decide on need: does the settings list require timestamps to be useful? | v1: no format change (exe + url only). If timestamps are wanted, put them in a sidecar `icon_cache_meta.json`. |
| **T6** | **Write races.** The engine writes non-atomically (`icons.py:48`); the shell deletes and reads the same file (`commands.rs:274`, `328`). Protocol-routed clears remove the race for clears, not for engine writes. | Corrupt-file repro: force a write during a delete; validate the JSON on every read for a day (add a JSON-error log line). | Make `_save_cache` atomic (temp + rename, the shell's own pattern) as part of S3. |
| **T7** | **Trusted-host liveness (F3/D).** Manual clearing may be enough — or entries may die often enough to justify automatic revalidation. | Probe the current `icon_cache.json` entries now, then periodically; track the death rate. | If > ~10 % of entries die per month, add lazy revalidation (at most once per app per session, budgeted); otherwise keep it manual. |
| **T8** | **Untrusted-host probing (F6).** Memoizing the verdict changes when a *fixed* override URL starts working. | Count how often a non-trusted `icon_url` is in use; measure the probe cost per tick. | If rare: memoize with the retry ladder (the ladder always re-probes after failures). |
| **T9** | **Packaged-app icons (E1).** Whether the Explorer-style route (`IShellItemImageFactory::GetImage` / `SHGetFileInfo(SHGFI_ICON)`) returns WhatsApp's icon at all on Win10/11. | 20–30-line probe against `…\WindowsApps\…\WhatsApp.exe` and one UWP app; compare with what Explorer shows. | If it works, class-C apps get real icons (and their per-5-second GDI churn disappears). If not, document override `icon_url` as the answer and park the idea. |

---

## 6. Rollout (each step independently shippable)

| Step | Content | Risk |
|---|---|---|
| **S1** | Observability + timer stamp: WARNING logs with stage and reason, `start_epoch` stamped at detection, atomic `_save_cache`, memoized validation verdicts (F2/F4/F6/F7). | None user-visible; the log becomes honest. |
| **S2** | The retry ladder in `icons.py`, plus an optional `iconState` field in the `app` event so the Status pane can say *why* the default is showing. | Behaviour change for stuck apps (fewer attempts, occasional park). |
| **S3** | Per-app clear: `icons` API → protocol pair → shell commands → Status card + App Names section + memo invalidation (`T-030`). | Additive changes to the frozen IPC contract (`types.ts`). |
| **S4** | Trusted-host revalidation — **only if T7 shows entries dying.** | Adds probes; gate on the measurement. |
| **S5 (option)** | Packaged-app icons via the Explorer route (E1) — gated on the T9 probe. | New COM/GDI paths; must not slow the tick loop. |

**Landed 2026-10-18 in `bd2543e`:** S1, S2 and S3. The appendix measurements below sized the failure
classes; the ladder values are the owner's choice (§7). S4 and S5 stay gated.

---

## 7. Owner answers (2026-10-18)

1. **Qt build:** `desktop/` only. The Tauri shell is the product direction; `gui.py` is maintenance
   only (`AGENTS.md`), so no per-app UI there. It still gets the engine-side improvements because it
   shares `icons.py`, and its global reset keeps working because `clear_icon_cache()` stayed
   call-compatible.
2. **Retry budget:** as proposed — 3 attempts, then the escalating park 60 s → 5 min → 30 min.
3. **Where the per-app UI lives:** **both** — a **Refresh icon** action in the Status card *and* an
   **Icon cache** section in App Names (not the Logs dialog this draft proposed). The Logs pane
   keeps its existing global reset.
4. **Cache metadata:** keep `icon_cache.json` as `{exe: url}` strings. No format change.
5. **Surface the failure state:** yes — the `app` event carries
   `icon: {state, attempts, retryAtMs, reason}` and the Status pane's Details card renders it.

---

## Appendix — measurement recipe against the current log

```powershell
# Which apps fall back to the default, and how often:
Select-String -Path autorpc.log -Pattern "Using default icon for" |
  ForEach-Object { ($_.Line -split "Using default icon for ")[1] } |
  Group-Object | Sort-Object Count -Descending

# Mechanism failures (currently DEBUG — present in the file, not in the GUI terminal):
Select-String -Path autorpc.log -Pattern "upload failed|Icon URL content-type|No icon found|Icon extraction failed|SteamGridDB lookup failed"
```

Run both before S2. **Results recorded 2026-10-18** (the retained log starts 2026-10-12; no rotated
backups exist):

- fallbacks — `WhatsApp.Root` **117**, `Antigravity IDE` **68** (one 13-minute window on
  2026-10-12), `Notion` **5**, `Zen` **3**
- mechanism lines — 117 × `No icon found in …WhatsAppDesktop…`; **no upload-failure lines at all**
- `icon_cache.json` — 17 entries

Re-run these after S1 lands; the S1 lines are what the ladder values should be chosen from.
