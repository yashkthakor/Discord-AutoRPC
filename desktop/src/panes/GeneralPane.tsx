/**
 * General pane (G-1…G-12).
 *
 * Autosave everywhere (A12 / D-031): switches commit on click, text commits on blur or
 * Enter, numbers clamp on blur. Nothing here has a Save button, and an invalid field
 * never writes — nor does it block the others (SEM-8).
 */

import { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink } from "lucide-react";
import { Button } from "@/components/Button";
import { NumberField, Select, TextField } from "@/components/Inputs";
import { InsetList } from "@/components/InsetList";
import { Dialog } from "@/components/Overlay";
import { SegmentedControl } from "@/components/SegmentedControl";
import { StatusPill } from "@/components/StatusPill";
import { Card, Group, Row } from "@/components/Structure";
import { Switch } from "@/components/Switch";
import { toast } from "@/components/Toast";
import { invoke } from "@/ipc/client";
import { cmd, type Appearance, type ConnectionTest } from "@/ipc/types";
import { useDebounced } from "@/lib/hooks";
import { normalizeAppId, normalizeExeKey, validateAppId } from "@/lib/validation";
import { configStore, updateConfig } from "@/state/config";
import { engineStore } from "@/state/engine";
import { prefsStore, setAppearance } from "@/state/prefs";
import { useStore } from "@/state/store";

const DEV_PORTAL = "https://discord.com/developers/applications";

export function GeneralPane() {
  return (
    <>
      <DiscordGroup />
      <BehaviourGroup />
      <TimingGroup />
      <AppearanceGroup />
      <AdvancedGroup />
      <ResetGroup />
    </>
  );
}

/* ------------------------------------------------------------- Discord --- */

function DiscordGroup() {
  const config = useStore(configStore);
  const stored = config?.application_id ?? "";

  const [draft, setDraft] = useState(stored);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<ConnectionTest | null>(null);

  useEffect(() => {
    setDraft(stored);
  }, [stored]);

  const debounced = useDebounced(draft, 250);
  const validation = validateAppId(debounced);
  // Shown only once there is more than a stray character, and after the debounce, so
  // typing a 19-digit ID never produces a wall of red (OB-6).
  const showError = debounced.length > 1 && !validation.ok;

  const commit = (raw: string) => {
    const normalized = normalizeAppId(raw);
    setDraft(normalized);
    if (!normalizeAppId(draft) || normalized === stored) return;
    if (!validateAppId(normalized).ok) return; // never write an invalid id (SEM-8)
    void updateConfig({ application_id: normalized }, "Couldn't save the Application ID.");
  };

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      setResult(await invoke<ConnectionTest>(cmd.testConnection, { appId: normalizeAppId(draft) }));
    } catch {
      setResult({ ok: false, detail: "The test could not run." });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Group
      title="Discord"
      description="The Application ID ties this app to a Discord application you control. Create one, then copy its ID."
    >
      <Card>
        <Row label="Application ID" description="Numbers only, 17–21 digits. Stored in config.json." stack>
          <div className="field" style={{ gap: "var(--sp-2)" }}>
            <TextField
              value={draft}
              onCommit={commit}
              onDraftChange={setDraft}
              mono
              placeholder="1234567890123456789"
              ariaLabel="Discord Application ID"
              error={showError ? validation.error : undefined}
              valid={!showError && validation.ok && draft.length > 0}
            />
            <div className="field__row">
              <Button
                variant="secondary"
                size="sm"
                disabled={!validation.ok || testing}
                onClick={() => void test()}
              >
                {testing ? "Testing…" : "Test connection"}
              </Button>
              <Button
                variant="quiet"
                size="sm"
                icon={<ExternalLink size={13} aria-hidden="true" />}
                onClick={() => void invoke(cmd.openUrl, { url: DEV_PORTAL }).catch(() => undefined)}
              >
                Open Developer Portal
              </Button>
              {result ? (
                <StatusPill tone={result.ok ? "ok" : "bad"} title={result.detail}>
                  {result.ok ? "Connected" : "Not connected"}
                </StatusPill>
              ) : null}
            </div>
            {result ? (
              <span className={result.ok ? "field__hint" : "field__error"}>{result.detail}</span>
            ) : (
              <span className="field__hint">
                An Application ID is not a secret — it is public by design. Never enter a token or client
                secret anywhere in this app.
              </span>
            )}
          </div>
        </Row>

        <Row
          label="Setup Assistant"
          description="Re-run the first-run walkthrough: create the application, name it, paste the ID."
        >
          <Button variant="secondary" size="sm" onClick={() => void invoke(cmd.openOnboarding).catch(() => undefined)}>
            Re-run setup
          </Button>
        </Row>
      </Card>
    </Group>
  );
}

/* ----------------------------------------------------------- Behaviour --- */

function BehaviourGroup() {
  const config = useStore(configStore);
  const engine = useStore(engineStore);
  const [autostart, setAutostart] = useState(engine.autostartEnabled);

  // G-3 / SEM-5: read the real OS state, never assume the config value is the truth.
  useEffect(() => {
    void invoke<boolean>(cmd.getAutostart)
      .then(setAutostart)
      .catch(() => undefined);
  }, []);

  const toggleAutostart = async (enabled: boolean) => {
    try {
      await invoke(cmd.setAutostart, { enabled });
      setAutostart(await invoke<boolean>(cmd.getAutostart));
    } catch {
      setAutostart(await invoke<boolean>(cmd.getAutostart).catch(() => !enabled));
      toast("Windows refused the startup entry — it may be blocked by policy.", { kind: "error" });
    }
  };

  return (
    <Group title="Behaviour" description="How the app reacts to what you are doing.">
      <Card>
        <Row
          label="Start with Windows"
          description="Adds a shortcut to your user startup folder. Writes the real Windows entry, not just a setting."
        >
          <Switch checked={autostart} onChange={(next) => void toggleAutostart(next)} label="Start with Windows" />
        </Row>

        <Row
          label="Close with Discord"
          description="Exit when Discord exits. Recommended: a presence cannot be shown without Discord anyway."
        >
          <Switch
            checked={config?.auto_close_with_discord ?? false}
            onChange={(next) => void updateConfig({ auto_close_with_discord: next })}
            label="Close with Discord"
          />
        </Row>

        <Row
          label="Hide private browsing"
          description="Incognito and InPrivate windows are never broadcast. Keeping this on is a privacy promise, not a preference."
        >
          <Switch
            checked={config?.mask_private_browsing ?? true}
            onChange={(next) => void updateConfig({ mask_private_browsing: next })}
            label="Hide private browsing"
          />
        </Row>

        <Row
          label="Dynamic taglines"
          description="Build the second line from the window title, for example “Writing a document — report.docx”."
        >
          <Switch
            checked={config?.enable_dynamic_taglines ?? true}
            onChange={(next) => void updateConfig({ enable_dynamic_taglines: next })}
            label="Dynamic taglines"
          />
        </Row>
      </Card>
    </Group>
  );
}

/* -------------------------------------------------------------- Timing --- */

function TimingGroup() {
  const config = useStore(configStore);
  if (!config) return null;

  return (
    <Group title="Timing" description="Trade-offs between responsiveness and how often Discord is touched.">
      <Card>
        <Row
          label="Switch delay"
          description="How long an app must stay in front before it is broadcast. Prevents flicker when you alt-tab through windows. Larger is calmer; smaller is snappier."
        >
          <NumberField
            value={config.debounce_seconds}
            min={2}
            max={60}
            unit="s"
            ariaLabel="Switch delay in seconds"
            onCommit={(next) => void updateConfig({ debounce_seconds: next })}
          />
        </Row>

        <Row
          label="Idle timeout"
          description="How long the presence stays up after nothing changes. Discord applies its own timeout to some activity types, so the shorter of the two wins."
        >
          <NumberField
            value={config.idle_timeout_seconds}
            min={10}
            max={600}
            unit="s"
            ariaLabel="Idle timeout in seconds"
            onCommit={(next) => void updateConfig({ idle_timeout_seconds: next })}
          />
        </Row>
      </Card>
    </Group>
  );
}

/* ---------------------------------------------------------- Appearance --- */

function AppearanceGroup() {
  const prefs = useStore(prefsStore);

  return (
    <Group
      title="Appearance"
      description="System follows the Windows app theme live, including while this window is open."
    >
      <Card>
        <Row label="Theme" description="Saved to ui_prefs.json, so it never touches config.json.">
          <SegmentedControl<Appearance>
            ariaLabel="Theme"
            value={prefs.appearance}
            onChange={(next) => void setAppearance(next)}
            options={[
              { value: "system", label: "System" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
          />
        </Row>
      </Card>
    </Group>
  );
}

/* ------------------------------------------------------------ Advanced --- */

function AdvancedGroup() {
  const config = useStore(configStore);
  if (!config) return null;

  return (
    <Group
      title="Advanced"
      description="These can stop broadcasting entirely if set carelessly. They are visible on purpose."
    >
      <Card>
        <Row
          label="Poll interval"
          description="How often the foreground window is checked, in seconds. Lower detects faster at the cost of CPU; 5 seconds is a good default."
        >
          <NumberField
            value={config.poll_interval}
            min={1}
            max={60}
            unit="s"
            ariaLabel="Poll interval in seconds"
            onCommit={(next) => void updateConfig({ poll_interval: next })}
          />
        </Row>

        <Row
          label="Only broadcast allow-listed apps"
          description="When on, anything not in the list below is ignored. This is the usual cause of “nothing is broadcasting”."
        >
          <Switch
            checked={config.whitelist_only}
            onChange={(next) => void updateConfig({ whitelist_only: next })}
            label="Only broadcast allow-listed apps"
          />
        </Row>

        {config.whitelist_only ? (
          <Row label="Allow list" description="Normalized to lowercase with a .exe suffix." stack>
            <InsetList<string>
              ariaLabel="Allow list"
              items={[...config.whitelist].sort()}
              getKey={(item) => item}
              filterText={(item) => item}
              filterPlaceholder="Filter allow list"
              emptyTitle="Nothing is allow-listed"
              emptyHint="With this list empty and the switch on, nothing will ever be broadcast."
              removeLabel="Remove"
              addLabel="Add app"
              onRemove={(item) => {
                const previous = config.whitelist;
                void updateConfig({ whitelist: previous.filter((x) => x !== item) }, "Couldn't update the allow list.").then(
                  (ok) => {
                    if (ok) {
                      toast(`Removed ${item} from the allow list`, {
                        action: { label: "Undo", run: () => void updateConfig({ whitelist: previous }) },
                      });
                    }
                  },
                );
              }}
              renderAdd={(close) => (
                <AddExeForm
                  title="Allow an application"
                  hint="Enter an executable name, for example code.exe."
                  submitLabel="Allow"
                  onSubmit={(value) => {
                    if (config.whitelist.includes(value)) {
                      close();
                      return;
                    }
                    void updateConfig({ whitelist: [...config.whitelist, value].sort() });
                    close();
                  }}
                  onCancel={close}
                />
              )}
              renderRow={(item) => (
                <>
                  <span className="inset-list__value">{item}</span>
                </>
              )}
            />
          </Row>
        ) : null}

        <Row
          label="Icon upload host"
          description="Where extracted icons are uploaded so Discord can display them. Both hosts are third-party and public: anyone with the URL can view the image."
        >
          <Select<"freeimage" | "catbox">
            ariaLabel="Icon upload host"
            value={config.upload_host}
            onChange={(next) => void updateConfig({ upload_host: next })}
            options={[
              { value: "freeimage", label: "freeimage.host" },
              { value: "catbox", label: "catbox.moe" },
            ]}
          />
        </Row>

        <Row
          label="SteamGridDB API key"
          description="Optional. Used only to fetch nicer box art for games Discord doesn't know. The key is stored locally in config.json."
          stack
        >
          <TextField
            value={config.steamgriddb_api_key}
            onCommit={(next) => void updateConfig({ steamgriddb_api_key: next.trim() })}
            password
            placeholder="Paste a key, or leave blank"
            ariaLabel="SteamGridDB API key"
            hint="A non-working key means a failed lookup every time a new game launches — that is a real cost, not a silent no-op."
          />
        </Row>
      </Card>
    </Group>
  );
}

/* --------------------------------------------------------------- Reset --- */

function ResetGroup() {
  const [open, setOpen] = useState(false);

  const exportFirst = async () => {
    try {
      const path = await invoke<string>(cmd.exportConfig);
      toast(`Saved a copy to ${path}`, { kind: "success" });
    } catch {
      toast("Couldn't export config.json.", { kind: "error" });
    }
  };

  const reset = async () => {
    try {
      await invoke(cmd.resetConfig);
      toast("Settings were reset to their defaults.", { kind: "success" });
    } catch {
      toast("Couldn't reset the settings.", { kind: "error" });
    }
  };

  return (
    <Group title="Reset" description="Reset every setting. Your icon cache and log files are left alone.">
      <Card>
        <Row
          label="Reset all settings"
          description="Restores defaults in config.json. App names, taglines and the ignore list are cleared."
        >
          <Button variant="dangerText" size="sm" onClick={() => setOpen(true)}>
            Reset…
          </Button>
        </Row>
      </Card>

      <Dialog
        open={open}
        title="Reset all settings?"
        onClose={() => setOpen(false)}
        actions={
          <>
            <Button variant="quiet" onClick={() => void exportFirst()}>
              Export config first
            </Button>
            <span style={{ flex: 1 }} />
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void reset()}>
              Reset
            </Button>
          </>
        }
      >
        <span style={{ display: "flex", gap: "var(--sp-2)" }}>
          <AlertTriangle size={16} aria-hidden="true" />
          This cannot be undone from inside the app. Export a copy first if you have custom names or
          taglines worth keeping.
        </span>
      </Dialog>
    </Group>
  );
}

/* -------------------------------------------------------- shared pieces --- */

interface AddExeFormProps {
  title: string;
  hint?: string;
  submitLabel: string;
  initial?: string;
  disabledReason?: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}

/** The exe-key half of every add form. Normalization happens here, once (O-4 / T-4). */
export function AddExeForm({
  title,
  hint,
  submitLabel,
  initial = "",
  disabledReason,
  onSubmit,
  onCancel,
}: AddExeFormProps) {
  const [value, setValue] = useState(initial);
  const normalized = normalizeExeKey(value);
  const blocked = Boolean(disabledReason);

  return (
    <>
      <span className="t-section" id="add-exe-title">
        {title}
      </span>
      <TextField
        label="Executable"
        value={value}
        onCommit={setValue}
        onDraftChange={setValue}
        placeholder="code.exe"
        mono
        autoFocus
        ariaLabel="Executable name"
        hint={hint}
      />
      {normalized && normalized !== value.trim().toLowerCase() ? (
        <span className="field__hint">
          Will be saved as <span className="t-mono">{normalized}</span>
        </span>
      ) : null}
      {disabledReason ? <span className="field__error">{disabledReason}</span> : null}
      <div className="popover__actions">
        <Button variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={!normalized || blocked}
          onClick={() => onSubmit(normalized)}
        >
          {submitLabel}
        </Button>
      </div>
    </>
  );
}
