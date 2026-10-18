/**
 * App Names & Overrides pane (O-1…O-9).
 *
 * One list, one source of truth: `config.overrides`. Every row commits through
 * `set_override`-equivalent writes (we send the whole map) so the file can never be
 * left half-written (SEM-6 / B-10 was a non-atomic write in the Python build).
 *
 * The Icon cache section at the bottom clears resolved icons per app (T-030): a row
 * clear resets the engine's retry ladder for that app, so the next poll fetches again.
 */

import { useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { Button, IconButton } from "@/components/Button";
import { InsetList } from "@/components/InsetList";
import { TextField } from "@/components/Inputs";
import { Popover } from "@/components/Overlay";
import { toast } from "@/components/Toast";
import { Card, Group } from "@/components/Structure";
import { invoke } from "@/ipc/client";
import { cmd, type Config, type IconCacheEntry, type Override } from "@/ipc/types";
import { invalidateAppIcon, useAppIcon } from "@/lib/icons";
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

      <IconCacheGroup />
    </>
  );
}

/* ------------------------------------------------------------ icon cache --- */

/**
 * Per-app icon cache (T-030): what `icon_cache.json` holds right now, with a clear per
 * row and a clear-all. A clear also resets the engine's retry ladder for that app, so the
 * next poll fetches again — this is the "the icon is wrong, try it again" control.
 */
function IconCacheGroup() {
  const engine = useStore(engineStore);

  useEffect(() => {
    // Ask for the authoritative listing; the answer arrives as a state update.
    void invoke(cmd.getIconCache).catch(() => undefined);
  }, []);

  const clear = async (keys: string[] | null) => {
    try {
      const count = await invoke<number | null>(cmd.clearIconCache, keys ? { exeKeys: keys } : undefined);
      if (keys) invalidateAppIcon(exeName(keys[0]));
      else invalidateAppIcon();
      // null means "forwarded to the engine" — its own toast reports the count.
      if (count === null) return;
      toast(
        count > 0
          ? `Cleared ${count} cached icon${count === 1 ? "" : "s"} — fetching again on the next poll.`
          : "Nothing was cached — the engine fetches it again anyway.",
        { kind: "success" },
      );
    } catch {
      toast("Couldn't clear the icon cache.", { kind: "error" });
    }
  };

  const entries = engine.iconCache;

  return (
    <Group
      title="Icon cache"
      description="Every icon the engine has resolved for an app. Clearing one makes the engine fetch that icon again on its next poll — use it when Discord is showing the wrong or default icon."
    >
      <InsetList<IconCacheEntry>
        ariaLabel="Icon cache"
        items={entries}
        getKey={(row) => row.path}
        filterText={(row) => row.path}
        filterPlaceholder="Filter cached icons"
        emptyTitle="No cached icons yet"
        emptyHint="Icons are listed here after the engine fetches one for the first time."
        removeLabel="Clear"
        onRemove={(row) => void clear([row.path])}
        renderRow={(row) => (
          <>
            <img className="inset-list__thumb" src={row.url} alt="" loading="lazy" />
            <div className="inset-list__main">
              <span className="inset-list__value">{exeName(row.path)}</span>
              <span className="inset-list__key t-mono">{row.path}</span>
            </div>
          </>
        )}
        footnote={
          <span
            className="field__row"
            style={{ justifyContent: "space-between", alignItems: "center", gap: "var(--sp-3)", flexWrap: "wrap" }}
          >
            <span className="t-caption">
              {entries.length} cached icon{entries.length === 1 ? "" : "s"}
            </span>
            <Button variant="secondary" size="sm" disabled={entries.length === 0} onClick={() => void clear(null)}>
              Clear all
            </Button>
          </span>
        }
      />
    </Group>
  );
}

/** `C:\App\Code.exe` → `code.exe`: the key the icon memo and the override map both use. */
function exeName(path: string): string {
  const parts = path.split(/[\\/]/);
  return (parts[parts.length - 1] || path).toLowerCase();
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
