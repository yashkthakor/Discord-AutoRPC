/**
 * Theme application (A4–A8 / D-023…D-027).
 *
 * `System` removes `data-theme` entirely, so the media query in `tokens.css` wins and
 * an OS change is followed live — including while Settings is open (THEME-1).
 * An explicit choice sets `data-theme` on the document element.
 *
 * The window itself is shown only after the first paint, by the `ready` command, so
 * the wrong theme is never visible (THEME-3 — see D-046 for how this is implemented).
 */

import type { Appearance } from "@/ipc/types";

export function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function resolveAppearance(appearance: Appearance): "light" | "dark" {
  if (appearance === "system") return systemPrefersDark() ? "dark" : "light";
  return appearance;
}

/** Apply an appearance to the document. Safe to call before React renders. */
export function applyAppearance(appearance: Appearance): void {
  const root = document.documentElement;
  if (appearance === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", appearance);
}

/** Notify when the OS theme changes while `System` is active. */
export function watchSystemTheme(onChange: () => void): () => void {
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
