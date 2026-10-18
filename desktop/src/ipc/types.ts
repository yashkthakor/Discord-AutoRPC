/**
 * The IPC contract (GUI_HANDOFF_TAURI_REACT.md §6).
 *
 * These types are the seam between the React frontend and whatever implements the
 * backend. Nothing in `src/` may import a Tauri API directly — go through
 * `src/ipc/client.ts`, which falls back to the mock backend outside Tauri.
 */

/** Appearance preference (A4 / D-023). Persisted in `ui_prefs.json`, never `config.json`. */
export type Appearance = "system" | "light" | "dark";

/** Sidebar sections (A11 / D-030). Order is normative. */
export type SectionId = "status" | "general" | "apps" | "taglines" | "ignored" | "logs";

export const SECTIONS: ReadonlyArray<{ id: SectionId; label: string }> = [
  { id: "status", label: "Status" },
  { id: "general", label: "General" },
  { id: "apps", label: "App Names" },
  { id: "taglines", label: "Taglines" },
  { id: "ignored", label: "Ignored Apps" },
  { id: "logs", label: "Logs" },
];

export type EngineStatus = "offline" | "waiting" | "active" | "paused";

export type DiscordStatus = "connected" | "connecting" | "offline" | "not-running";

/**
 * Where the engine's icon resolution stands for the app on screen (T-030).
 *
 * `ok` — a URL is in hand (override, cache or a fresh upload). `pending` — the ladder is
 * between attempts. `parked` — the three attempts failed and the default icon shows until
 * `retryAtMs`, when the engine tries again.
 */
export interface IconStatus {
  state: "ok" | "pending" | "parked";
  /** Failures in the current attempt sequence (0–3). */
  attempts: number;
  /** When the next attempt happens, ms since epoch; null when none is scheduled. */
  retryAtMs: number | null;
  /** Why the last attempt failed, already human-readable; null when nothing failed. */
  reason: string | null;
}

/** One row of `icon_cache.json`, as the App Names pane lists it (T-030). */
export interface IconCacheEntry {
  /** The exe path as cached — full path, lowercase. */
  path: string;
  url: string;
}

/** The app currently in the foreground, as the engine sees it. */
export interface AppInfo {
  /** Normalized key: lowercase, `.exe` suffix. Never display this raw without a fallback. */
  exe: string;
  path: string;
  pid: number;
  displayName: string;
  /** Resolved tagline, or null when there is none (Status pane shows the automatic value). */
  tagline: string | null;
  iconUrl: string | null;
  /** The engine's icon retry ladder; absent on older engines and on the mock (T-030). */
  icon?: IconStatus | null;
  /** Milliseconds since epoch. The engine must send ms, not seconds (see T-022). */
  startedAtMs: number | null;
  ignored: boolean;
}

/** Everything the UI knows about the engine. Pushed, never polled (PERF/§7). */
export interface EngineState {
  version: string;
  engine: EngineStatus;
  discord: DiscordStatus;
  /** False when no valid Application ID is configured. */
  configured: boolean;
  /** Set when an update is available; shown in the tray header. */
  updateTag: string | null;
  app: AppInfo | null;
  /** Recently detected exe keys, most recent first. Feeds the add-form suggestions. */
  recentApps: string[];
  /** Real OS autostart state, not a config value (G-3). */
  autostartEnabled: boolean;
  /** The engine's `icon_cache.json`, for the App Names pane (T-030). Empty until it answers. */
  iconCache: IconCacheEntry[];
}

export interface Override {
  name: string;
  tagline?: string;
  icon_url?: string;
}

/**
 * `config.json`, mirroring `config.py::DEFAULT_CONFIG`.
 * Unknown keys must be preserved on write — the index signature is load-bearing.
 */
export interface Config {
  application_id: string;
  poll_interval: number;
  debounce_seconds: number;
  idle_timeout_seconds: number;
  default_icon_url: string;
  auto_close_with_discord: boolean;
  mask_private_browsing: boolean;
  whitelist_only: boolean;
  whitelist: string[];
  ignored_exes: string[];
  taglines: Record<string, string>;
  overrides: Record<string, Override>;
  steamgriddb_api_key: string;
  upload_host: "freeimage" | "catbox";
  enable_dynamic_taglines: boolean;
  [key: string]: unknown;
}

/** `ui_prefs.json` (A5 / D-024). */
export interface Prefs {
  appearance: Appearance;
}

export type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR";

export interface LogLine {
  id: number;
  ts: number;
  level: LogLevel;
  logger: string;
  message: string;
  /**
   * Set only for lines read back out of `autorpc.log`, which stores a clock time but no
   * date. When present the view shows it verbatim instead of formatting `ts`.
   */
  displayTime?: string;
}

/**
 * The unified ignore listing (A18 / D-037 / D-047).
 *
 * `managed` is `config.ignored_exes` — the file the Ignored Apps pane and the tray both
 * write. `legacy` is anything left in `ignore_list.json` that the startup migration could
 * not fold in, shown rather than hidden. `defaults` is the shipped seed set, used to tag
 * rows, not to hide them.
 */
export interface IgnoredListing {
  managed: string[];
  legacy: string[];
  defaults: string[];
}

export interface BuiltIns {
  taglines: Record<string, string>;
}

export interface UpdateInfo {
  current: string;
  latest: string | null;
  url: string | null;
}

export interface ConnectionTest {
  ok: boolean;
  /** Human-readable outcome; already localized by the backend. */
  detail: string;
  appName?: string;
}

/** Command names. Use these instead of bare strings so a typo is a compile error. */
export const cmd = {
  ready: "ready",
  getState: "get_state",
  getConfig: "get_config",
  setConfig: "set_config",
  getPrefs: "get_prefs",
  setPrefs: "set_prefs",
  setWindowTheme: "set_window_theme",
  testConnection: "test_connection",
  getAutostart: "get_autostart",
  setAutostart: "set_autostart",
  pause: "pause",
  resume: "resume",
  renameApp: "rename_app",
  removeOverride: "remove_override",
  ignoreApp: "ignore_app",
  unignoreApp: "unignore_app",
  getIgnored: "get_ignored",
  getBuiltIns: "get_built_ins",
  seedLogs: "seed_logs",
  clearIconCache: "clear_icon_cache",
  getIconCache: "get_icon_cache",
  resetConfig: "reset_config",
  exportConfig: "export_config",
  exportLogs: "export_logs",
  openUrl: "open_url",
  openLog: "open_log",
  openLogFolder: "open_log_folder",
  openOnboarding: "open_onboarding",
  openRename: "open_rename",
  openSettings: "open_settings",
  closeWindow: "close_window",
  minimizeWindow: "minimize_window",
  toggleMaximize: "toggle_maximize",
  copyText: "copy_text",
  checkUpdates: "check_updates",
  appIconUrl: "app_icon_url",
} as const;

/** Event names pushed by the backend (§6.3). */
export const evt = {
  state: "state",
  log: "log",
  toast: "toast",
  configChanged: "config-changed",
  uiPrefsChanged: "ui-prefs-changed",
  /** Resize of the main window, so the custom chrome can show maximize or restore (D-055). */
  windowState: "window-state",
} as const;

/** Payload of `evt.windowState`. */
export interface WindowChrome {
  maximized: boolean;
}
