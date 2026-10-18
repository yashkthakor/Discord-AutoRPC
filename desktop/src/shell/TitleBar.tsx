/**
 * The strip that replaces the native caption on the auxiliary windows (D-055).
 *
 * Settings does not use this: its status row is the drag region, so the window has one bar
 * instead of two. Onboarding and rename have no such row, so they get this one — without it
 * a frameless window could not be moved at all.
 *
 * `data-tauri-drag-region="deep"` means a click anywhere inside the strip drags the window,
 * *except* on the controls, which are buttons and are therefore ignored by Tauri's script.
 * Double-clicking it maximizes, also for free.
 */

import { WindowControls } from "@/components/WindowControls";

export interface TitleBarProps {
  title: string;
}

export function TitleBar({ title }: TitleBarProps) {
  return (
    <header className="titlebar" data-tauri-drag-region="deep">
      <span className="titlebar__title">{title}</span>
      <WindowControls variant="close" />
    </header>
  );
}
