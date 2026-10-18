/**
 * The only module that touches Tauri.
 *
 * Outside a Tauri window (plain `npm run dev` in a browser) every call is served by
 * the mock backend so the UI stays developable and demoable. That fallback is a
 * development affordance, not a product feature: `isTauri()` is checked once per call.
 */

import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { mockInvoke, mockListen } from "./mock";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export function isTauri(): boolean {
  return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

/** Invoke a backend command. Falls back to the mock backend outside Tauri. */
export function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri()) return mockInvoke<T>(command, args);
  return tauriInvoke<T>(command, args);
}

/** Subscribe to a pushed event. Returns an unsubscribe function. */
export function on<T>(event: string, handler: (payload: T) => void): () => void {
  if (!isTauri()) return mockListen(event, handler);

  let unlisten: UnlistenFn | null = null;
  let disposed = false;

  void listen<T>(event, (e) => handler(e.payload)).then((fn) => {
    if (disposed) fn();
    else unlisten = fn;
  });

  return () => {
    disposed = true;
    unlisten?.();
  };
}

/** Fire-and-forget logging to the backend log file. Never throws. */
export function logFromUi(level: "debug" | "info" | "warn" | "error", message: string): void {
  if (!isTauri()) return;
  void tauriInvoke("ui_log", { level, message }).catch(() => undefined);
}
