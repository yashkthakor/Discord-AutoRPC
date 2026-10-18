/**
 * One bundle, three windows (SH-1).
 *
 * The route is passed in by the entry point, which the Rust shell picked when it created
 * the window, so a window never changes identity mid-life.
 */

import { useEffect } from "react";
import { ToastViewport } from "@/components/Toast";
import { bootstrap, type WindowRoute } from "@/lib/boot";
import { ErrorBoundary } from "@/shell/ErrorBoundary";
import { SettingsWindow } from "@/shell/SettingsWindow";
import { Onboarding } from "@/windows/Onboarding";
import { QuickRename } from "@/windows/QuickRename";

export function App({ route }: { route: WindowRoute }) {
  useEffect(() => {
    void bootstrap();
  }, []);

  return (
    <>
      <ErrorBoundary>
        {route === "onboarding" ? (
          <Onboarding />
        ) : route === "rename" ? (
          <QuickRename />
        ) : (
          <SettingsWindow />
        )}
      </ErrorBoundary>
      <ToastViewport />
    </>
  );
}
