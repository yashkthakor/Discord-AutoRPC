/**
 * App Names & Overrides pane (O-1…O-9).
 *
 * One list, one source of truth: `config.overrides`. Every row commits through
 * `set_override`-equivalent writes (we send the whole map) so the file can never be
 * left half-written (SEM-6 / B-10 was a non-atomic write in the Python build).
 */

import { useState } from "react";
import { Pencil } from "lucide-react";
import { Button, IconButton } from "@/components/Button";
import { InsetList } from "@/components/InsetList";
import { TextField } from "@/components/Inputs";
import { Popover } from "@/components/Overlay";
import { toast } from "@/components/Toast";
import { Card, Group } from "@/components/Structure";
import type { Config, Override } from "@/ipc/types";
import { useAppIcon } from "@/lib/icons";
import { normalizeExeKey, validateIconUrl } from "@/lib/validation";
import { configStore, updateConfig } from "@/state/config";
import { engineStore } from "@/state/engine";
import { useStore } from "@/state/store";

export function AppNamesPane() {
  const config = useStore(configStore);
  const engine = useStore(engineStore);
  const [editing, setEditing] = useState<string | null>(null);

  if (!config) return null;

  const entries = Object.entries(config.overrides).sort(([a], [b]) => a.localeCompare(b));

  const writeMap = async (map: Record<string, Override>, message?: string) => {
    const ok = await updateConfig({ overrides: map }, "Couldn't save that app name.");
    if (ok && message) toast(message, { kind: "success" });
    return ok;
  };

  const remove = async (exe: string) => {
    const previous = config.overrides;
    const next = { ...previous };
    delete next[exe];
    const ok = await writeMap(next);
    if (ok) {
      toast(`Removed the name for ${exe}`, {
        action: { label: "Undo", run: () => void writeMap(previous) },
      });
    }
  };

  const upsert = async (exe: string, override: Override) => {
    await writeMap({ ...config.overrides, [exe]: override });
  };

  return (
    <>
      <Group
        title="App Names"
        description="Override what Discord shows for an app. The name is the first line; the tagline is optional and replaces the automatic second line."
      >
        <InsetList<[string, Override]>
          ariaLabel="App names"
          items={entries}
          getKey={([exe]) => exe}
          filterText={([exe, override]) => `${exe} ${override.name} ${override.tagline ?? ""}`}
          filterPlaceholder="Filter app names"
          emptyTitle="No app names yet"
          emptyHint="Add one and it applies the next time that app comes to the front — no restart needed."
          removeLabel="Remove"
          addLabel="Add app name"
          onRemove={([exe]) => void remove(exe)}
          renderAdd={(close) => (
            <OverrideForm
              initial={{ exe: "", name: "", tagline: "", iconUrl: "" }}
              suggestions={engine.recentApps}
              existing={config.overrides}
              submitLabel="Add"
              onSubmit={(exe, override) => {
                void upsert(exe, override);
                close();
              }}
              onCancel={close}
            />
          )}
          renderRow={([exe, override]) => (
            <OverrideRow
              exe={exe}
              override={override}
              recording={engine.app?.exe === exe}
              config={config}
              suggestions={engine.recentApps}
              editing={editing === exe}
              onEdit={() => setEditing(editing === exe ? null : exe)}
              onCloseEdit={() => setEditing(null)}
              onSubmit={(nextExe, nextOverride) => {
                const map = { ...config.overrides };
                if (nextExe !== exe) delete map[exe];
                map[nextExe] = nextOverride;
                void writeMap(map);
                setEditing(null);
              }}
            />
          )}
          footnote={
            <span className="t-caption">
              The executable key is always lowercase with a <span className="t-mono">.exe</span> suffix — that
              is the key the engine matches on.
            </span>
          }
        />
      </Group>

      <Group title="How this is resolved" description="In order, first match wins.">
        <Card>
          <ol className="steps" style={{ padding: "var(--sp-4)" }}>
            <li>An override in this list</li>
            <li>The app&rsquo;s own version information from its executable</li>
            <li>The executable name, cleaned up</li>
          </ol>
        </Card>
      </Group>
    </>
  );
}

/* ------------------------------------------------------------------ row --- */

interface OverrideRowProps {
  exe: string;
  override: Override;
  config: Config;
  recording: boolean;
  suggestions: string[];
  editing: boolean;
  onEdit: () => void;
  onCloseEdit: () => void;
  onSubmit: (exe: string, override: Override) => void;
}

function OverrideRow({
  exe,
  override,
  config,
  recording,
  suggestions,
  editing,
  onEdit,
  onCloseEdit,
  onSubmit,
}: OverrideRowProps) {
  const iconUrl = useAppIcon(exe);

  return (
    <>
      {iconUrl ? (
        <img className="inset-list__thumb" src={iconUrl} alt="" />
      ) : (
        <span className="inset-list__thumb" aria-hidden="true" />
      )}

      <div className="inset-list__main">
        <span className="inset-list__value">
          {override.name}
          {recording ? <span className="t-caption"> — on screen now</span> : null}
        </span>
        <span className="inset-list__key">
          {exe}
          {override.tagline ? ` — ${override.tagline}` : ""}
        </span>
      </div>

      <div className="inset-list__actions">
        <div className="popover-anchor">
          <IconButton
            label={`Edit ${exe}`}
            icon={<Pencil size={15} aria-hidden="true" />}
            onClick={onEdit}
          />
          <Popover open={editing} onClose={onCloseEdit}>
            <OverrideForm
              initial={{
                exe,
                name: override.name,
                tagline: override.tagline ?? "",
                iconUrl: override.icon_url ?? "",
              }}
              suggestions={suggestions}
              existing={config.overrides}
              editingKey={exe}
              submitLabel="Save"
              onSubmit={onSubmit}
              onCancel={onCloseEdit}
            />
          </Popover>
        </div>
      </div>
    </>
  );
}

/* ----------------------------------------------------------------- form --- */

interface OverrideFormProps {
  initial: { exe: string; name: string; tagline: string; iconUrl: string };
  suggestions: string[];
  existing: Record<string, Override>;
  editingKey?: string;
  submitLabel: string;
  onSubmit: (exe: string, override: Override) => void;
  onCancel: () => void;
}

function OverrideForm({
  initial,
  suggestions,
  existing,
  editingKey,
  submitLabel,
  onSubmit,
  onCancel,
}: OverrideFormProps) {
  const [exe, setExe] = useState(initial.exe);
  const [name, setName] = useState(initial.name);
  const [tagline, setTagline] = useState(initial.tagline);
  const [iconUrl, setIconUrl] = useState(initial.iconUrl);

  const key = normalizeExeKey(exe || initial.exe);
  const duplicate = !editingKey && key !== "" && key in existing;
  const iconCheck = validateIconUrl(iconUrl);
  const nameEmpty = name.trim().length === 0;

  // O-9: warn, never block — the user may be pre-configuring something not installed yet.
  const unknown = key !== "" && suggestions.length > 0 && !suggestions.includes(key);

  return (
    <>
      {editingKey ? null : (
        <TextField
          label="Executable"
          value={exe}
          onCommit={setExe}
          onDraftChange={setExe}
          placeholder="code.exe"
          mono
          autoFocus
          ariaLabel="Executable name"
          error={duplicate ? "That app already has a custom name — edit that entry instead." : undefined}
        />
      )}

      <TextField
        label="Display name (the 'Playing …' line)"
        value={name}
        onCommit={setName}
        onDraftChange={setName}
        placeholder="Visual Studio Code"
        autoFocus={Boolean(editingKey)}
        ariaLabel="Display name"
        error={nameEmpty ? "A display name is required." : undefined}
      />

      <TextField
        label="Tagline (optional second line)"
        value={tagline}
        onCommit={setTagline}
        onDraftChange={setTagline}
        placeholder="Leave blank to keep the automatic tagline"
        ariaLabel="Tagline"
      />

      <TextField
        label="Icon URL (optional)"
        value={iconUrl}
        onCommit={setIconUrl}
        onDraftChange={setIconUrl}
        placeholder="https://…"
        mono
        ariaLabel="Icon URL"
        error={iconCheck.ok ? undefined : iconCheck.error}
      />

      {suggestions.length > 0 && !editingKey ? (
        <div className="field">
          <span className="field__label">Recently detected</span>
          <div className="hero__actions">
            {suggestions.slice(0, 6).map((suggestion) => (
              <Button key={suggestion} variant="secondary" size="sm" onClick={() => setExe(suggestion)}>
                {suggestion}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      {unknown ? (
        <span className="field__hint">
          Nothing named <span className="t-mono">{key}</span> has been seen running yet. It will still work when
          it launches.
        </span>
      ) : null}

      <div className="popover__actions">
        <Button variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={key === "" || nameEmpty || duplicate || !iconCheck.ok}
          onClick={() =>
            onSubmit(key, {
              name: name.trim(),
              ...(tagline.trim() ? { tagline: tagline.trim() } : {}),
              ...(iconUrl.trim() ? { icon_url: iconUrl.trim() } : {}),
            })
          }
        >
          {submitLabel}
        </Button>
      </div>
    </>
  );
}
