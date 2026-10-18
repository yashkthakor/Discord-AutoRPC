/**
 * Status pane (A15 / D-034) — the landing surface.
 *
 * Shows the app that is being broadcast right now, in full: icon, name, tagline,
 * ticking timer, connection state, and the three actions that matter (pause, rename,
 * ignore). The "why this tagline?" disclosure is deliberately deferred (A15).
 */

import { useState } from "react";
import { Ban, Pause, Pencil, Play } from "lucide-react";
import { Button } from "@/components/Button";
import { Sheet } from "@/components/Overlay";
import { RenameForm } from "@/components/RenameForm";
import { StatusPill } from "@/components/StatusPill";
import { Card, EmptyState, Group, KV } from "@/components/Structure";
import { invoke } from "@/ipc/client";
import { cmd, type SectionId } from "@/ipc/types";
import { formatClockTime, formatDuration } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { useAppIcon } from "@/lib/icons";
import { engineStore } from "@/state/engine";
import { ignoreApp } from "@/state/ignored";
import { useStore } from "@/state/store";

export interface StatusPaneProps {
  onNavigate: (section: SectionId) => void;
}

export function StatusPane({ onNavigate }: StatusPaneProps) {
  const state = useStore(engineStore);
  const app = state.app;
  const iconUrl = useAppIcon(app?.exe ?? null);
  const [renameOpen, setRenameOpen] = useState(false);

  const paused = state.engine === "paused";
  const now = useNow(Boolean(app) && !paused);
  const elapsed = app?.startedAtMs ? now - app.startedAtMs : 0;

  const togglePause = () => {
    void invoke(paused ? cmd.resume : cmd.pause).catch(() => undefined);
  };

  return (
    <>
      <Group
        title="Now broadcasting"
        description="What your Discord profile shows right now. Updates within one poll cycle."
      >
        <Card pad>
          {!app ? (
            <EmptyState
              title={paused ? "Broadcasting is paused" : "Nothing detected yet"}
              hint={
                paused
                  ? "Resume to start broadcasting whichever app you switch to."
                  : "Switch to any application and it will show up here within a few seconds."
              }
              action={
                paused ? (
                  <Button variant="primary" onClick={togglePause}>
                    Resume
                  </Button>
                ) : null
              }
            />
          ) : (
            <div className="field" style={{ gap: "var(--sp-4)" }}>
              <div className="hero">
                {iconUrl ? (
                  <img className="hero__icon" src={iconUrl} alt="" />
                ) : (
                  <span className="hero__icon hero__icon--placeholder" aria-hidden="true" />
                )}
                <div className="hero__text">
                  <span className="hero__name">{app.displayName}</span>
                  <span className="hero__tagline">{app.tagline ?? "No tagline"}</span>
                </div>
                {!paused ? (
                  <span className="hero__timer" aria-label="Time on this app">
                    {formatDuration(elapsed)}
                  </span>
                ) : null}
              </div>

              <div className="hero__actions">
                <Button
                  variant="secondary"
                  icon={paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
                  onClick={togglePause}
                >
                  {paused ? "Resume" : "Pause"}
                </Button>
                <Button
                  variant="secondary"
                  icon={<Pencil size={14} aria-hidden="true" />}
                  onClick={() => setRenameOpen(true)}
                >
                  Rename
                </Button>
                <Button
                  variant="secondary"
                  icon={<Ban size={14} aria-hidden="true" />}
                  onClick={() => void ignoreApp(app.exe, app.displayName)}
                >
                  Ignore this app
                </Button>
              </div>
            </div>
          )}
        </Card>
      </Group>

      <Group title="Details" description="What the engine resolved for this app.">
        <Card>
          <KV k="Executable">
            <span className="t-mono">{app?.exe ?? "—"}</span>
          </KV>
          <KV k="Full path">
            <span className="t-mono">{app?.path ?? "—"}</span>
          </KV>
          <KV k="Process ID">
            <span className="t-numeric">{app?.pid ?? "—"}</span>
          </KV>
          <KV k="Detected at">
            {app?.startedAtMs ? formatClockTime(app.startedAtMs) : "—"}
          </KV>
          <KV k="Tagline">
            {app?.tagline ? app.tagline : <span className="t-secondary">None — the second line is empty</span>}
          </KV>
          <KV k="Discord">
            {state.discord === "connected" ? (
              <StatusPill tone="ok">Connected</StatusPill>
            ) : state.discord === "not-running" ? (
              <StatusPill tone="bad">Discord not running</StatusPill>
            ) : state.discord === "connecting" ? (
              <StatusPill tone="live">Connecting</StatusPill>
            ) : (
              <StatusPill tone="muted">Unavailable</StatusPill>
            )}
          </KV>
        </Card>
      </Group>

      {!state.configured ? (
        <Group title="Setup" description="Nothing is broadcast until an Application ID is set.">
          <Card pad>
            <Button variant="primary" onClick={() => onNavigate("general")}>
              Go to General
            </Button>
          </Card>
        </Group>
      ) : null}

      <Sheet open={renameOpen} title="Rename active app" onClose={() => setRenameOpen(false)}>
        {app ? (
          <RenameForm
            exe={app.exe}
            initialName={app.displayName}
            initialTagline={app.tagline ?? ""}
            recentApps={state.recentApps}
            onDone={() => setRenameOpen(false)}
            onCancel={() => setRenameOpen(false)}
          />
        ) : null}
      </Sheet>
    </>
  );
}
