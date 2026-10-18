/**
 * Shared mount for the three windows (SH-1).
 *
 * Routes are separate HTML entry points rather than hash routes: a window's identity is
 * fixed at creation time by the Rust shell, and `index.html` / `onboarding.html` /
 * `rename.html` cannot be mis-parsed or percent-encoded the way a `#fragment` in a
 * `WebviewUrl::App` path can be.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Fonts are bundled locally — no remote font loading (FONT-1 / SEC-1).
import "@fontsource-variable/inter";
import "@fontsource/cascadia-code/400.css";

import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/components.css";

import { App } from "./App";
import type { WindowRoute } from "./lib/boot";

export function mount(route: WindowRoute): void {
  const container = document.getElementById("root");
  if (!container) throw new Error("#root is missing from the document");

  createRoot(container).render(
    <StrictMode>
      <App route={route} />
    </StrictMode>,
  );
}
