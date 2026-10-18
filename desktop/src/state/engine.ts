/** Live engine state, pushed by the backend (§6.3). The UI never polls. */

import { invoke, on } from "@/ipc/client";
import { cmd, evt, type EngineState } from "@/ipc/types";
import { createStore } from "./store";

const EMPTY: EngineState = {
  version: "",
  engine: "offline",
  discord: "offline",
  configured: false,
  updateTag: null,
  app: null,
  recentApps: [],
  autostartEnabled: false,
};

export const engineStore = createStore<EngineState>(EMPTY);

let started = false;

export function initEngine(): void {
  if (started) return;
  started = true;

  on<EngineState>(evt.state, (next) => engineStore.set(next));

  void invoke<EngineState>(cmd.getState)
    .then((state) => engineStore.set(state))
    .catch(() => {
      engineStore.set({ ...EMPTY, engine: "offline" });
    });
}

export function currentApp() {
  return engineStore.get().app;
}
