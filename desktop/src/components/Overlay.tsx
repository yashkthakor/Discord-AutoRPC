/**
 * Popover, dialog, confirm dialog and sheet.
 *
 * No `window.confirm` and no app-blocking modal (FB-2): these are ordinary React
 * state, so the engine and the log stream keep running behind them.
 */

import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "./Button";

/* --------------------------------------------------------------- popover --- */

export interface PopoverProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  labelledBy?: string;
}

/** Rendered inside a `.popover-anchor`. Esc and outside-click both dismiss. */
export function Popover({ open, onClose, children, labelledBy }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (ref.current?.contains(target)) return;
      // The anchor wraps both the trigger and this panel: clicks there are ours.
      if (ref.current?.parentElement?.contains(target)) return;
      onClose();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="popover" role="dialog" aria-modal="false" aria-labelledby={labelledBy} ref={ref}>
      {children}
    </div>
  );
}

/* ---------------------------------------------------------------- dialog --- */

export interface DialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  actions: ReactNode;
}

export function Dialog({ open, title, children, onClose, actions }: DialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="scrim" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="alertdialog" aria-modal="true" aria-label={title}>
        <h2 className="dialog__title">{title}</h2>
        <div className="dialog__body">{children}</div>
        <div className="dialog__actions">{actions}</div>
      </div>
    </div>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/** Dialogs exist only for destructive actions (A14 / D-033). */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {body}
    </Dialog>
  );
}

/* ----------------------------------------------------------------- sheet --- */

export interface SheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function Sheet({ open, title, onClose, children }: SheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="scrim" onPointerDown={(e) => e.target === e.currentTarget && onClose()} />
      <aside className="sheet" role="dialog" aria-modal="true" aria-label={title}>
        <h2 className="dialog__title">{title}</h2>
        {children}
      </aside>
    </>
  );
}
