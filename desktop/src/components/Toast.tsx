/**
 * Toasts (A14 / D-033): a quiet bottom-centre pill with an optional Undo action.
 *
 * - `aria-live="polite"` so screen readers announce without interrupting (A11Y-2).
 * - Never modal, never focus-stealing, never blocking (FB-2).
 * - Undo is a real reversal: the caller supplies the reversal, we only render it.
 */

import { useEffect } from "react";
import { on } from "@/ipc/client";
import { evt } from "@/ipc/types";
import { createStore, useStore } from "@/state/store";

export type ToastKind = "info" | "success" | "error";

export interface ToastAction {
  label: string;
  run: () => void;
}

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
  action?: ToastAction;
}

const store = createStore<ToastItem[]>([]);
let nextId = 1;

const DEFAULT_MS = 3600;
const UNDO_MS = 6500;
const ERROR_MS = 6000;
const MAX_VISIBLE = 3;

export function toast(
  message: string,
  opts: { kind?: ToastKind; durationMs?: number; action?: ToastAction } = {},
): number {
  const id = nextId++;
  const item: ToastItem = {
    id,
    kind: opts.kind ?? "info",
    message,
    ...(opts.action ? { action: opts.action } : {}),
  };

  store.set((prev) => [...prev, item].slice(-MAX_VISIBLE));

  const duration = opts.durationMs ?? (opts.action ? UNDO_MS : opts.kind === "error" ? ERROR_MS : DEFAULT_MS);
  window.setTimeout(() => dismissToast(id), duration);
  return id;
}

export function dismissToast(id: number): void {
  store.set((prev) => prev.filter((t) => t.id !== id));
}

/** Rendered once per window, above everything else. */
export function ToastViewport() {
  const items = useStore(store);

  useEffect(
    () =>
      on<{ kind?: ToastKind; message: string }>(evt.toast, (payload) => {
        toast(payload.message, { kind: payload.kind ?? "info" });
      }),
    [],
  );

  return (
    <div className="toast-viewport" aria-live="polite" aria-atomic="false">
      {items.map((t) => (
        <div className={`toast toast--${t.kind}`} key={t.id} role="status">
          <span>{t.message}</span>
          {t.action ? (
            <button
              type="button"
              className="toast__action"
              onClick={() => {
                t.action?.run();
                dismissToast(t.id);
              }}
            >
              {t.action.label}
            </button>
          ) : null}
        </div>
      ))}
    </div>
  );
}
