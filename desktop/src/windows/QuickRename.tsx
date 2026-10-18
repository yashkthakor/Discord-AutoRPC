/**
 * Standalone quick-rename window (R-1 / A21).
 *
 * The tray's “Rename Active App” opens this small window rather than a modal on top of
 * Settings, so it can be used without bringing Settings forward. The Status pane shows
 * the same form in a sheet — one component, two homes.
 *
 * The window is frameless, so `TitleBar` supplies the drag region and the close button
 * (D-055). Its title is the app name, not the task — the task is the heading below, and
 * repeating it twice would read as a mistake.
 */

import { RenameForm } from "@/components/RenameForm";
import { EmptyState } from "@/components/Structure";
import { invoke } from "@/ipc/client";
import { cmd } from "@/ipc/types";
import { TitleBar } from "@/shell/TitleBar";
import { engineStore } from "@/state/engine";
import { useStore } from "@/state/store";

export function QuickRename() {
  const state = useStore(engineStore);
  const app = state.app;

  const close = () => {
    void invoke(cmd.closeWindow).catch(() => undefined);
  };

  return (
    <div className="window">
      <TitleBar title="Discord AutoRPC" />

      <div className="onboard">
        <div className="onboard__inner">
          <div>
            <h1 className="onboard__title">Rename Active App</h1>
            <p className="t-secondary" style={{ marginTop: 6 }}>
              Changes apply immediately — Discord updates the moment you click Save.
            </p>
          </div>

          {app ? (
            <RenameForm
              exe={app.exe}
              initialName={app.displayName}
              initialTagline={app.tagline ?? ""}
              recentApps={state.recentApps}
              onDone={close}
              onCancel={close}
            />
          ) : (
            <EmptyState
              title="Nothing is being broadcast"
              hint="Switch to the app you want to rename, or open Settings and add a name from the App Names list."
              action={
                <button type="button" className="btn btn--primary" onClick={close}>
                  Close
                </button>
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
