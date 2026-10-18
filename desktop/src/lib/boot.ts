/**
 * Window bootstrap.
 *
 * Order matters (A8 / THEME-3 / D-046):
 *   1. the correct theme is applied to the document *before* React renders
 *   2. stores subscribe to pushed events and fetch their first snapshot
 *   3. the stored appearance is read and applied
 *   4. the first paint is awaited
 *   5. only then is the backend asked to show the window
 *
 * The window is created hidden by the Rust side, so no frame is ever presented in the
 * wrong theme — that is why no synchronous boot script is needed.
 */

import { invoke } from "@/ipc/client";
import { cmd } from "@/ipc/types";
import { applyAppearance } from "./theme";
import { initEngine } from "@/state/engine";
import { initConfig } from "@/state/config";
import { initLogs } from "@/state/logs";
import { initPrefs, loadPrefs } from "@/state/prefs";
import { refreshIgnored } from "@/state/ignored";

export type WindowRoute = "settings" | "onboarding" | "rename";

function nextPaint(): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()));
  });
}

export async function bootstrap(): Promise<void> {
  // 1 — System is the default, and the tokens cascade handles it with no attribute.
  applyAppearance("system");

  // 2 — subscribe + seed
  initPrefs();
  initEngine();
  initConfig();
  initLogs();
  void refreshIgnored();

  // 3 — the stored preference wins over the system default
  await loadPrefs();

  // 4 + 5
  await nextPaint();
  try {
    await invoke(cmd.ready);
  } catch {
    // In a browser there is no window to show; that is expected during development.
  }
}
