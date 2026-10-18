/**
 * Setup Assistant (OB-1…OB-14 / A20).
 *
 * Three steps, one column, no emoji. The window can be dismissed at any time with
 * “Set up later” — the app keeps running unconfigured and the tray keeps working
 * (Q4 answered: Cancel must not be a dead end).
 */

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Inputs";
import { StatusPill } from "@/components/StatusPill";
import { Card, EmptyState, Row } from "@/components/Structure";
import { Switch } from "@/components/Switch";
import { invoke } from "@/ipc/client";
import { cmd, type ConnectionTest } from "@/ipc/types";
import { useDebounced } from "@/lib/hooks";
import { normalizeAppId, validateAppId } from "@/lib/validation";
import { TitleBar } from "@/shell/TitleBar";
import { updateConfig } from "@/state/config";

const DEV_PORTAL = "https://discord.com/developers/applications";
const STEP_TITLES = [
  "Create a Discord application",
  "Copy its Application ID",
  "Paste it here",
] as const;

export function Onboarding() {
  const [step, setStep] = useState(0);
  const [appId, setAppId] = useState("");
  const [autoClose, setAutoClose] = useState(true);
  const [autostart, setAutostart] = useState(false);
  const [verify, setVerify] = useState<ConnectionTest | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void invoke<boolean>(cmd.getAutostart)
      .then(setAutostart)
      .catch(() => undefined);
  }, []);

  const debounced = useDebounced(appId, 250);
  const validation = validateAppId(debounced);

  const setUpLater = () => {
    void invoke(cmd.closeWindow).catch(() => undefined);
  };

  const toggleAutostart = async (enabled: boolean) => {
    setAutostart(enabled);
    try {
      await invoke(cmd.setAutostart, { enabled });
      setAutostart(await invoke<boolean>(cmd.getAutostart));
    } catch {
      setAutostart(await invoke<boolean>(cmd.getAutostart).catch(() => !enabled));
    }
  };

  const finish = async () => {
    const normalized = normalizeAppId(appId);
    if (!validateAppId(normalized).ok) return;

    setBusy(true);
    setVerify(null);
    try {
      const saved = await updateConfig(
        { application_id: normalized, auto_close_with_discord: autoClose },
        "Couldn't save your Application ID.",
      );
      if (!saved) return;

      const result = await invoke<ConnectionTest>(cmd.testConnection, { appId: normalized });
      setVerify(result);
      if (result.ok) {
        await invoke(cmd.openSettings).catch(() => undefined);
        await invoke(cmd.closeWindow).catch(() => undefined);
      }
    } catch {
      setVerify({ ok: false, detail: "The connection test couldn't run." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="window">
      <TitleBar title="Discord AutoRPC" />
      <div className="onboard">
        <div className="onboard__inner">
          <div className="field__row">
            <div className="onboard__steps" aria-label={`Step ${step + 1} of 3`}>
              {STEP_TITLES.map((title, index) => (
                <span
                  key={title}
                  className="onboard__step-dot"
                  data-active={index === step}
                  data-done={index < step}
                />
              ))}
            </div>
            <span className="t-caption t-numeric">Step {step + 1} of 3</span>
          </div>

          <div>
            <h1 className="onboard__title">{STEP_TITLES[step]}</h1>
            <p className="t-secondary" style={{ marginTop: 6, maxWidth: "56ch" }}>
              {step === 0
                ? "Discord needs an application before anything can be shown on your profile. It takes about a minute and it is free."
                : step === 1
                  ? "The Application ID tells Discord which app name to display. It is public information, not a secret."
                  : "Paste the ID and this app will start broadcasting as soon as Discord is running."}
            </p>
          </div>

          {step === 0 ? (
            <Card pad>
              <ol className="steps">
                <li>Open the Discord Developer Portal and sign in.</li>
                <li>Choose “New Application”, give it any name — that name is what shows on your profile.</li>
                <li>Keep the tab open and continue here.</li>
              </ol>
              <div style={{ marginTop: "var(--sp-4)" }}>
                <Button
                  variant="primary"
                  icon={<ExternalLink size={14} aria-hidden="true" />}
                  onClick={() => void invoke(cmd.openUrl, { url: DEV_PORTAL }).catch(() => undefined)}
                >
                  Open the Developer Portal
                </Button>
              </div>
            </Card>
          ) : null}

          {step === 1 ? (
            <Card pad>
              <ol className="steps">
                <li>In the portal, open your application.</li>
                <li>On the General Information page, find Application ID.</li>
                <li>Use “Copy” next to it — pasting the whole URL works too, the ID is picked out automatically.</li>
              </ol>
              <p className="t-caption" style={{ marginTop: "var(--sp-4)" }}>
                Rich Presence needs no bot token, no secret and no permissions on your account.
              </p>
            </Card>
          ) : null}

          {step === 2 ? (
            <Card>
              <Row label="Application ID" description="17–21 digits. Whitespace and URLs are cleaned up for you." stack>
                <TextField
                  value={appId}
                  onCommit={setAppId}
                  onDraftChange={setAppId}
                  mono
                  autoFocus
                  placeholder="1234567890123456789"
                  ariaLabel="Discord Application ID"
                  valid={validation.ok}
                  error={appId.length > 1 && !validation.ok ? validation.error : undefined}
                />
              </Row>

              <Row label="Start with Windows" description="Launch quietly in the tray when you sign in.">
                <Switch
                  checked={autostart}
                  onChange={(next) => void toggleAutostart(next)}
                  label="Start with Windows"
                />
              </Row>

              <Row label="Close with Discord" description="Exit when Discord exits.">
                <Switch checked={autoClose} onChange={setAutoClose} label="Close with Discord" />
              </Row>

              {verify ? (
                <Row
                  label={
                    <span className="field__row">
                      <StatusPill tone={verify.ok ? "ok" : "bad"}>
                        {verify.ok ? "Connected" : "Not connected"}
                      </StatusPill>
                    </span>
                  }
                  description={verify.detail}
                />
              ) : null}
            </Card>
          ) : null}

          {step === 2 && verify && !verify.ok ? (
            <EmptyState
              title="Not connected yet"
              hint="Discord has to be running on this PC for the connection test to work. You can paste the ID anyway and finish — it will connect the moment Discord starts."
            />
          ) : null}

          <div className="onboard__footer">
            <Button variant="secondary" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
              Back
            </Button>
            <span className="spacer" />
            <Button variant="quiet" onClick={setUpLater}>
              Set up later
            </Button>
            {step < 2 ? (
              <Button variant="primary" onClick={() => setStep((s) => s + 1)}>
                Continue
              </Button>
            ) : (
              <Button
                variant="primary"
                disabled={!validation.ok || busy}
                onClick={() => void finish()}
              >
                {busy ? "Connecting…" : "Finish setup"}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
