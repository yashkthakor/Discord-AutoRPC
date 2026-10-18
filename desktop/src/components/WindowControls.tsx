/**
 * Window controls for the frameless chrome (D-055).
 *
 * The window has no native caption, so these are the only way to minimize, maximize and
 * close it. Order and placement follow the Windows convention — minimize, maximize/restore,
 * close, ending at the top-right corner — because a left-hand traffic light would be a
 * novelty a Windows user has to learn. The *styling* is ours (flat, token-coloured, a red
 * close hover), which is what the native title bar could not give us.
 *
 * Dragging and double-click-to-maximize are not handled here: Tauri's own drag-region script
 * does both, and these buttons are real `<button>` elements, which that script ignores.
 */

import { useEffect, useState } from "react";
import { Copy, Minus, Square, X } from "lucide-react";
import { invoke, on } from "@/ipc/client";
import { cmd, evt, type WindowChrome } from "@/ipc/types";

export interface WindowControlsProps {
  /**
   * `full` — Settings, which is a resizable window.
   * `close` — the fixed-size onboarding and rename windows, where minimize and maximize
   * would be meaningless (and maximize would produce a stretched dialog).
   */
  variant?: "full" | "close";
}

export function WindowControls({ variant = "full" }: WindowControlsProps) {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (variant === "close") return undefined;

    // Only the main window is watched, so an aux window never receives this.
    return on<WindowChrome>(evt.windowState, (next) => setMaximized(next.maximized));
  }, [variant]);

  return (
    <div className="window-controls">
      {variant === "full" ? (
        <>
          <button
            type="button"
            className="window-controls__button"
            aria-label="Minimize"
            title="Minimize"
            onClick={() => void invoke(cmd.minimizeWindow).catch(() => undefined)}
          >
            <Minus size={15} aria-hidden="true" />
          </button>

          <button
            type="button"
            className="window-controls__button"
            aria-label={maximized ? "Restore" : "Maximize"}
            title={maximized ? "Restore" : "Maximize"}
            onClick={() => void invoke(cmd.toggleMaximize).catch(() => undefined)}
          >
            {maximized ? <Copy size={13} aria-hidden="true" /> : <Square size={13} aria-hidden="true" />}
          </button>
        </>
      ) : null}

      <button
        type="button"
        className="window-controls__button window-controls__button--close"
        aria-label="Close"
        title="Close"
        onClick={() => void invoke(cmd.closeWindow).catch(() => undefined)}
      >
        <X size={15} aria-hidden="true" />
      </button>
    </div>
  );
}
