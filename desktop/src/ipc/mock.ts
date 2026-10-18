/**
 * Mock backend — development and demo only.
 *
 * It exists so the UI can be built and reviewed (`npm run dev` in a browser, or
 * `tauri dev` before the Python sidecar exists) without a Discord client, an
 * Application ID, or the engine. It is never used inside a packaged app: the real
 * backend answers every command there.
 *
 * Everything here is obviously fake: app names, log lines, icons.
 */

import type {
  Appearance,
  AppInfo,
  Config,
  EngineState,
  IconCacheEntry,
  IconStatus,
  IgnoredListing,
  LogLine,
  Prefs,
} from "./types";
import { cmd, evt } from "./types";

type Handler = (payload: unknown) => void;

const handlers = new Map<string, Set<Handler>>();

function emit(event: string, payload: unknown): void {
  handlers.get(event)?.forEach((h) => h(payload));
}

let logId = 1;
let toastId = 1;

const PREFS_KEY = "autorpc.mock.prefs";

const DEFAULT_CONFIG: Config = {
  application_id: "1234567890123456789",
  poll_interval: 5,
  debounce_seconds: 10,
  idle_timeout_seconds: 60,
  default_icon_url: "https://cdn.discordapp.com/embed/avatars/0.png",
  auto_close_with_discord: true,
  mask_private_browsing: true,
  whitelist_only: false,
  whitelist: [],
  ignored_exes: ["legacy_old_app.exe"],
  taglines: {
    "notion.exe": "Writing something serious",
    "code.exe": "Shipping code",
  },
  overrides: {
    "photoshop.exe": { name: "Photoshop", tagline: "Retouching pixels" },
  },
  steamgriddb_api_key: "",
  upload_host: "freeimage",
  enable_dynamic_taglines: true,
};

const RECENT = [
  "spotify.exe",
  "code.exe",
  "chrome.exe",
  "notion.exe",
  "explorer.exe",
  "photoshop.exe",
  "discord.exe",
];

const DEMO_APPS: Array<Omit<AppInfo, "startedAtMs">> = [
  {
    exe: "code.exe",
    path: "C:\\Program Files\\Microsoft VS Code\\Code.exe",
    pid: 8124,
    displayName: "Visual Studio Code",
    tagline: "Shipping code",
    iconUrl: null,
    ignored: false,
  },
  {
    exe: "chrome.exe",
    path: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    pid: 4412,
    displayName: "Google Chrome",
    tagline: "Browsing YouTube",
    iconUrl: null,
    icon: { state: "parked", attempts: 3, retryAtMs: Date.now() + 20 * 60_000, reason: "no icon resource to extract" },
    ignored: false,
  },
  {
    exe: "spotify.exe",
    path: "C:\\Users\\Yash\\AppData\\Roaming\\Spotify\\Spotify.exe",
    pid: 9911,
    displayName: "Spotify",
    tagline: "Listening to something",
    iconUrl: null,
    ignored: false,
  },
];

const LOG_SAMPLES: Array<[LogLine["level"], string, string]> = [
  ["DEBUG", "autorpc.detector", "poll: foreground changed -> chrome.exe"],
  ["DEBUG", "autorpc.detector", "poll: foreground changed -> code.exe"],
  ["INFO", "autorpc.icons", "Extracted 256x256 icon from code.exe"],
  ["INFO", "autorpc.icons", "Uploaded icon to freeimage.host"],
  ["INFO", "autorpc.presence", "Presence updated: Visual Studio Code"],
  ["WARNING", "autorpc.icons", "Catbox upload failed (HTTP 503); retrying with freeimage"],
  ["INFO", "autorpc.detector", "Debounce: ignoring transient switch to explorer.exe"],
  ["ERROR", "autorpc.presence", "Discord IPC closed unexpectedly; reconnect scheduled in 15s"],
];

/** The mock's `icon_cache.json` — same shape and lowercase path keys the engine writes (T-030). */
let iconCache: IconCacheEntry[] = [
  {
    path: "c:\\program files\\google\\chrome\\application\\chrome.exe",
    url: "https://cdn.discordapp.com/embed/avatars/1.png",
  },
  {
    path: "c:\\program files\\microsoft vs code\\code.exe",
    url: "https://cdn.discordapp.com/embed/avatars/2.png",
  },
  {
    path: "c:\\users\\yash\\appdata\\roaming\\spotify\\spotify.exe",
    url: "https://cdn.discordapp.com/embed/avatars/3.png",
  },
];

let state: EngineState = {
  version: "0.2.0-mock",
  engine: "active",
  discord: "connected",
  configured: true,
  updateTag: null,
  app: null,
  recentApps: RECENT,
  autostartEnabled: true,
  iconCache: [...iconCache],
};

let config: Config = structuredClone(DEFAULT_CONFIG);
let managed = ["discord.exe"];
const defaults = [
  "explorer.exe",
  "searchhost.exe",
  "startmenuexperiencehost.exe",
  "shellexperiencehost.exe",
  "textinputhost.exe",
  "applicationframehost.exe",
  "lockapp.exe",
  "taskmgr.exe",
  "dwm.exe",
  "sihost.exe",
  "fontdrvhost.exe",
  "ctfmon.exe",
];

let demoIndex = 0;

function readPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Prefs>;
      if (parsed.appearance === "light" || parsed.appearance === "dark" || parsed.appearance === "system") {
        return { appearance: parsed.appearance };
      }
    }
  } catch {
    /* ignore */
  }
  return { appearance: "system" };
}

function writePrefs(prefs: Prefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

function pushState(patch: Partial<EngineState>): void {
  state = { ...state, ...patch };
  emit(evt.state, state);
}

/** What the Status pane shows right after a mock icon clear (T-030). */
function retryingIcon(): IconStatus {
  return { state: "pending", attempts: 1, retryAtMs: Date.now() + 5000, reason: null };
}

function emitLog(level: LogLine["level"], logger: string, message: string): void {
  emit(evt.log, { id: logId++, ts: Date.now(), level, logger, message } satisfies LogLine);
}

function ignoredListing(): IgnoredListing {
  return { managed: [...managed], legacy: [...config.ignored_exes], defaults: [...defaults] };
}

/** Start the demo timers. Safe to call more than once. */
let timersStarted = false;
function startTimers(): void {
  if (timersStarted) return;
  timersStarted = true;

  const setApp = (index: number) => {
    const base = DEMO_APPS[index % DEMO_APPS.length];
    const app: AppInfo = { ...base, startedAtMs: Date.now(), ignored: managed.includes(base.exe) };
    pushState({ app, engine: state.engine === "paused" ? "paused" : "active" });
  };

  setApp(0);
  window.setInterval(() => {
    demoIndex += 1;
    setApp(demoIndex);
    emitLog("DEBUG", "autorpc.detector", `poll: foreground changed -> ${DEMO_APPS[demoIndex % DEMO_APPS.length].exe}`);
  }, 9000);

  window.setInterval(() => {
    if (state.engine === "paused") return;
    const [level, logger, message] = LOG_SAMPLES[Math.floor(Math.random() * LOG_SAMPLES.length)];
    emitLog(level, logger, message);
  }, 2200);
}

export function mockListen<T>(event: string, handler: (payload: T) => void): () => void {
  const wrapped = (payload: unknown) => handler(payload as T);
  if (!handlers.has(event)) handlers.set(event, new Set());
  handlers.get(event)!.add(wrapped);
  if (event === evt.state) wrapped(state);
  return () => {
    handlers.get(event)?.delete(wrapped);
  };
}

export async function mockInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const a: Record<string, unknown> = args ?? {};
  const patch = (a["patch"] ?? {}) as Partial<Config>;

  switch (command) {
    case cmd.ready:
      startTimers();
      return undefined as T;

    case cmd.getState:
      return state as T;

    case cmd.getConfig:
      return structuredClone(config) as T;

    case cmd.setConfig: {
      config = { ...config, ...patch };
      emit(evt.configChanged, structuredClone(config));
      return structuredClone(config) as T;
    }

    case cmd.getPrefs:
      return readPrefs() as T;

    case cmd.setPrefs: {
      const raw = String(a["appearance"] ?? "system");
      const appearance: Appearance = raw === "light" || raw === "dark" ? raw : "system";
      const next: Prefs = { appearance };
      writePrefs(next);
      emit(evt.uiPrefsChanged, next);
      return next as T;
    }

    case cmd.setWindowTheme:
      return undefined as T;

    case cmd.getAutostart:
      return state.autostartEnabled as T;

    case cmd.setAutostart: {
      const enabled = Boolean(a["enabled"]);
      pushState({ autostartEnabled: enabled });
      return enabled as T;
    }

    case cmd.testConnection:
      return { ok: true, detail: "Connected to Discord as Discord AutoRPC (mock)", appName: "Discord AutoRPC" } as T;

    case cmd.pause:
      pushState({ engine: "paused" });
      emitLog("INFO", "autorpc.presence", "Presence cleared (paused from the UI)");
      return undefined as T;

    case cmd.resume:
      pushState({ engine: state.app ? "active" : "waiting" });
      return undefined as T;

    case cmd.renameApp: {
      const exe = String(a["exe"]);
      const name = String(a["name"]);
      const tagline = String(a["tagline"] ?? "");
      config = {
        ...config,
        overrides: { ...config.overrides, [exe]: { name, tagline } },
      };
      emit(evt.configChanged, structuredClone(config));
      if (state.app && state.app.exe === exe) {
        pushState({ app: { ...state.app, displayName: name, tagline: tagline || state.app.tagline } });
      }
      return undefined as T;
    }

    case cmd.removeOverride: {
      const exe = String(a["exe"]);
      const overrides = { ...config.overrides };
      delete overrides[exe];
      config = { ...config, overrides };
      emit(evt.configChanged, structuredClone(config));
      return undefined as T;
    }

    case cmd.ignoreApp: {
      const exe = String(a["exe"]);
      if (!managed.includes(exe)) managed = [...managed, exe].sort();
      emit(evt.toast, { kind: "info", message: `Ignoring ${exe}`, undoToken: `ignore:${exe}` });
      return undefined as T;
    }

    case cmd.unignoreApp: {
      const exe = String(a["exe"]);
      managed = managed.filter((x) => x !== exe);
      return undefined as T;
    }

    case cmd.getIgnored:
      return ignoredListing() as T;

    case cmd.getBuiltIns:
      return {
        taglines: {
          "notion.exe": "Working on a document",
          "obsidian.exe": "Organizing notes",
          "excel.exe": "Crunching numbers",
          "winword.exe": "Writing a document",
          "powerpnt.exe": "Building a deck",
          "spotify.exe": "Listening to music",
          "vlc.exe": "Watching something",
          "code.exe": "Writing code",
          "idea64.exe": "Writing code",
          "photoshop.exe": "Editing an image",
          "discord.exe": "Chatting on Discord",
        },
      } as T;

    case cmd.seedLogs: {
      const now = Date.now();
      return Array.from({ length: 40 }, (_, i) => {
        const [level, logger, message] = LOG_SAMPLES[i % LOG_SAMPLES.length];
        return { id: logId++, ts: now - (40 - i) * 1500, level, logger, message } satisfies LogLine;
      }) as T;
    }

    case cmd.getIconCache:
      return structuredClone(iconCache) as T;

    case cmd.clearIconCache: {
      const requested = Array.isArray(a["exeKeys"])
        ? (a["exeKeys"] as unknown[]).map((key) => String(key).toLowerCase())
        : null;
      const before = iconCache.length;
      iconCache = requested ? iconCache.filter((row) => !requested.includes(row.path.toLowerCase())) : [];
      pushState({
        iconCache: [...iconCache],
        ...(state.app ? { app: { ...state.app, icon: retryingIcon() } } : {}),
      });
      return (before - iconCache.length) as T;
    }

    case cmd.resetConfig: {
      config = structuredClone(DEFAULT_CONFIG);
      emit(evt.configChanged, structuredClone(config));
      return undefined as T;
    }

    case cmd.exportConfig:
    case cmd.exportLogs:
      return "C:\\Users\\Yash\\AppData\\Roaming\\DiscordAutoRPC\\export (mock).txt" as T;

    case cmd.openUrl:
      window.open(String(a["url"]), "_blank", "noopener");
      return undefined as T;

    case cmd.openLog:
    case cmd.openLogFolder:
    case cmd.openOnboarding:
    case cmd.openRename:
    case cmd.openSettings:
    case cmd.closeWindow:
      return undefined as T;

    case cmd.copyText:
      void navigator.clipboard?.writeText(String(a["text"] ?? ""));
      return undefined as T;

    case cmd.checkUpdates:
      return { current: state.version, latest: null, url: null } as T;

    case cmd.appIconUrl:
      return null as T;

    default:
      // Keep the mock loud rather than silently succeeding.
      throw new Error(`mock backend: unhandled command "${command}"`);
  }
}

/** Used by the toast store when the backend requests an undo. */
export function mockToast(message: string, kind: "info" | "success" | "error" = "info"): void {
  emit(evt.toast, { id: toastId++, kind, message });
}
