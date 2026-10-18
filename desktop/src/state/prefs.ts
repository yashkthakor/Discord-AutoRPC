/**
 * `ui_prefs.json` — appearance only (A5 / D-024 / THEME-1, THEME-2).
 *
 * Never written to `config.json`, never stored in localStorage in the real app, and
 * only ever mutated through a backend command (SEC-2).
 */

import { invoke, on } from "@/ipc/client";
import { cmd, evt, type Appearance, type Prefs } from "@/ipc/types";
import { toast } from "@/components/Toast";
import { applyAppearance } from "@/lib/theme";
import { createStore } from "./store";

const DEFAULT_PREFS: Prefs = { appearance: "system" };

export const prefsStore = createStore<Prefs>(DEFAULT_PREFS);

let started = false;

export function initPrefs(): void {
  if (started) return;
  started = true;

  on<Prefs>(evt.uiPrefsChanged, (next) => {
    prefsStore.set(next);
    applyAppearance(next.appearance);
  });
}

/**
 * Read the stored preference and apply it. Awaited by the bootstrap before the window
 * is shown, so the first visible frame is already in the right theme.
 */
export async function loadPrefs(): Promise<void> {
  try {
    const prefs = await invoke<Prefs>(cmd.getPrefs);
    prefsStore.set(prefs);
    applyAppearance(prefs.appearance);
  } catch {
    // A missing or unreadable file means System (A5).
    prefsStore.set(DEFAULT_PREFS);
    applyAppearance(DEFAULT_PREFS.appearance);
  }
}

/**
 * Change the appearance. The switch is instant — no colour transition (A8) — because
 * the attribute flips before the backend round-trip finishes.
 */
export async function setAppearance(appearance: Appearance): Promise<void> {
  const previous = prefsStore.get();
  prefsStore.set({ appearance });
  applyAppearance(appearance);

  try {
    await invoke<Prefs>(cmd.setPrefs, { appearance });
  } catch {
    prefsStore.set(previous);
    applyAppearance(previous.appearance);
    toast("Couldn't save the appearance preference.", { kind: "error" });
  }
}
