/**
 * `config.json` state, with autosave semantics (A12 / D-031 / SEM-3).
 *
 * Every mutation is optimistic: apply locally, tell the backend, roll back and toast
 * if the backend refuses. There is no draft state and no Save button.
 *
 * `config-changed` (SEM-7) replaces the store wholesale — the UI must therefore never
 * treat the store as authoritative for a field the user is mid-edit. Text fields hold
 * their own local value and commit on blur/Enter, so a push arriving mid-typing is
 * harmless.
 */

import { invoke, on } from "@/ipc/client";
import { cmd, evt, type Config } from "@/ipc/types";
import { toast } from "@/components/Toast";
import { createStore } from "./store";

export const configStore = createStore<Config | null>(null);

let started = false;

export function initConfig(): void {
  if (started) return;
  started = true;

  on<Config>(evt.configChanged, (next) => configStore.set(next));

  void invoke<Config>(cmd.getConfig)
    .then((config) => configStore.set(config))
    .catch(() => toast("Couldn't load config.json.", { kind: "error" }));
}

/**
 * Commit a config patch. Returns true when the write succeeded.
 * The optimistic update is reverted on failure so the UI never lies about the file.
 */
export async function updateConfig(patch: Partial<Config>, failureMessage?: string): Promise<boolean> {
  const previous = configStore.get();
  if (!previous) return false;

  configStore.set({ ...previous, ...patch });

  try {
    const next = await invoke<Config>(cmd.setConfig, { patch });
    configStore.set(next);
    return true;
  } catch {
    configStore.set(previous);
    toast(failureMessage ?? "Couldn't save that change — reverted.", { kind: "error" });
    return false;
  }
}

/** Convenience for the two exe-keyed maps (overrides, taglines). */
export async function updateMapEntry<K extends "overrides" | "taglines">(
  key: K,
  map: Config[K],
): Promise<boolean> {
  return updateConfig({ [key]: map } as unknown as Partial<Config>);
}
