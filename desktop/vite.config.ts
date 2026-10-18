import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

/**
 * Vite config for the Tauri shell.
 *
 * Notes:
 * - Port 1420 is fixed because `tauri.conf.json` points `devUrl` at it.
 * - `src-tauri` is excluded from the watcher so Rust rebuilds don't reload the webview.
 * - Build target is pinned to a Chromium baseline that WebView2 always satisfies.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
  build: {
    target: "chrome110",
    sourcemap: true,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      // One window per entry point (SH-1): settings, first-run onboarding, quick rename.
      input: {
        settings: fileURLToPath(new URL("./index.html", import.meta.url)),
        onboarding: fileURLToPath(new URL("./onboarding.html", import.meta.url)),
        rename: fileURLToPath(new URL("./rename.html", import.meta.url)),
      },
    },
  },
});
