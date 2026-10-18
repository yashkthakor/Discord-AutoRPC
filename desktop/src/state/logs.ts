/**
 * Log buffer (L-7…L-10, PERF-1).
 *
 * Incoming lines are appended to a pending buffer and flushed once per animation
 * frame, so a burst of DEBUG lines cannot cause one render per line. The store keeps
 * a bounded ring buffer; the Logs pane renders a capped window of the filtered tail.
 */

import { invoke, on } from "@/ipc/client";
import { cmd, evt, type LogLine } from "@/ipc/types";
import { createStore } from "./store";

const MAX_LINES = 5000;

export const logsStore = createStore<LogLine[]>([]);

let pending: LogLine[] = [];
let scheduled = false;
let started = false;

function flush(): void {
  scheduled = false;
  if (pending.length === 0) return;

  const merged = [...logsStore.get(), ...pending];
  pending = [];
  logsStore.set(merged.length > MAX_LINES ? merged.slice(merged.length - MAX_LINES) : merged);
}

function schedule(): void {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(flush);
}

export function initLogs(): void {
  if (started) return;
  started = true;

  on<LogLine>(evt.log, (line) => {
    pending.push(line);
    schedule();
  });

  void invoke<LogLine[]>(cmd.seedLogs)
    .then((seed) => {
      pending = [...seed, ...pending];
      schedule();
    })
    .catch(() => undefined);
}

/** L-5 — clears the view only. The log file on disk is untouched. */
export function clearLogView(): void {
  pending = [];
  logsStore.set([]);
}
