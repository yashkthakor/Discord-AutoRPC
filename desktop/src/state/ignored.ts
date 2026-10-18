/**
 * The unified ignore list (A18 / D-037 / I-5).
 *
 * One store is in play: `config.ignored_exes`, which both the tray menu and the Ignored
 * Apps pane write. `legacy` (leftovers in `ignore_list.json`) and `defaults` (the shipped
 * seeds, so rows can be tagged) come from the backend listing. See D-047.
 */

import { invoke } from "@/ipc/client";
import { cmd, type IgnoredListing } from "@/ipc/types";
import { toast } from "@/components/Toast";
import { createStore } from "./store";

const EMPTY: IgnoredListing = { managed: [], legacy: [], defaults: [] };

export const ignoredStore = createStore<IgnoredListing>(EMPTY);

export async function refreshIgnored(): Promise<void> {
  try {
    ignoredStore.set(await invoke<IgnoredListing>(cmd.getIgnored));
  } catch {
    toast("Couldn't read the ignore list.", { kind: "error" });
  }
}

export async function ignoreApp(exe: string, label?: string): Promise<void> {
  const previous = ignoredStore.get();
  if (previous.managed.includes(exe)) return;

  ignoredStore.set({ ...previous, managed: [...previous.managed, exe].sort() });

  try {
    await invoke(cmd.ignoreApp, { exe });
    toast(`${label ?? exe} is now ignored`, {
      action: {
        label: "Undo",
        run: () => {
          void unignoreApp(exe);
        },
      },
    });
  } catch {
    ignoredStore.set(previous);
    toast("Couldn't add that to the ignore list.", { kind: "error" });
  }
}

export async function unignoreApp(exe: string): Promise<void> {
  const previous = ignoredStore.get();
  ignoredStore.set({ ...previous, managed: previous.managed.filter((x) => x !== exe) });

  try {
    await invoke(cmd.unignoreApp, { exe });
    toast(`${exe} will be broadcast again`, {
      action: {
        label: "Undo",
        run: () => {
          void ignoreApp(exe);
        },
      },
    });
  } catch {
    ignoredStore.set(previous);
    toast("Couldn't remove that from the ignore list.", { kind: "error" });
  }
}
