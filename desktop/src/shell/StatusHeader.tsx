/**
 * Persistent live status strip (SS-4 / §5.3).
 *
 * Shows what the app is doing right now, from any section: current app, tagline,
 * ticking timer, Discord connection, pause state. This is the surface that makes the
 * app feel alive rather than "configure and hope".
 */

import { Pause, Play, RefreshCw } from "lucide-react";
import { IconButton } from "@/components/Button";
import { StatusPill } from "@/components/StatusPill";
import { WindowControls } from "@/components/WindowControls";
import { invoke } from "@/ipc/client";
import { cmd, type DiscordStatus, type EngineStatus } from "@/ipc/types";
import { formatDuration, titleFromExe } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { engineStore } from "@/state/engine";
import { useStore } from "@/state/store";

function discordLabel(status: DiscordStatus): { tone: "ok" | "bad" | "muted" | "live"; text: string } {
  switch (status) {
    case "connected":
      return { tone: "ok", text: "Connected" };
    case "connecting":
      return { tone: "live", text: "Connecting" };
    case "not-running":
      return { tone: "bad", text: "Discord not running" };
    default:
      return { tone: "muted", text: "Engine offline" };
  }
}

function engineLabel(status: EngineStatus): string {
  switch (status) {
    case "active":
      return "Broadcasting";
    case "waiting":
      return "Waiting for an app";
    case "paused":
      return "Paused";
    default:
      return "Engine offline";
  }
}

export function StatusHeader() {
  const state = useStore(engineStore);
  const app = state.app;
  const paused = state.engine === "paused";
  const now = useNow(Boolean(app) && !paused);
  const elapsed = app?.startedAtMs ? now - app.startedAtMs : 0;
  const discord = discordLabel(state.discord);

  const togglePause = () => {
    void invoke(paused ? cmd.resume : cmd.pause).catch(() => undefined);
  };

  return (
    // This row is the window's toolbar as well as its status strip: it carries the drag
    // region and the window controls, which is why there is no separate title bar here
    // (D-055). Clicks on the buttons are excluded by Tauri's drag script.
    <header className="status-bar" data-tauri-drag-region="deep">
      {app?.iconUrl ? (
        <img className="status-bar__icon" src={app.iconUrl} alt="" />
      ) : (
        <span className="status-bar__icon status-bar__icon--placeholder" aria-hidden="true">
          <RefreshCw size={13} />
        </span>
      )}

      <div className="status-bar__text">
        <span className="status-bar__name">
          {app ? app.displayName : engineLabel(state.engine)}
        </span>
        <span className="status-bar__meta">
          {app
            ? app.tagline
              ? `${app.exe} — ${app.tagline}`
              : `${app.exe} — no tagline`
            : "Nothing detected yet"}
        </span>
      </div>

      <div className="status-bar__spacer" />

      {app && !paused ? (
        <span className="t-numeric t-secondary" aria-label="Time on this app">
          {formatDuration(elapsed)}
        </span>
      ) : null}

      <StatusPill tone={paused ? "muted" : discord.tone}>{paused ? "Paused" : discord.text}</StatusPill>

      <IconButton
        label={paused ? "Resume broadcasting" : "Pause broadcasting"}
        icon={paused ? <Play size={15} aria-hidden="true" /> : <Pause size={15} aria-hidden="true" />}
        disabled={state.engine === "offline"}
        onClick={togglePause}
      />

      <WindowControls />
    </header>
  );
}

/** Fallback display name when an app has no PE metadata — exported for the panes. */
export { titleFromExe };
