/**
 * Taglines pane (T-1…T-8).
 *
 * Two lists with different powers: the user's taglines (editable, and they win over the
 * engine's built-in table) and the engine's built-ins (read-only, shown so users can see
 * what they are overriding and start from a copy).
 */

import { useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { Button, IconButton } from "@/components/Button";
import { InsetList } from "@/components/InsetList";
import { TextField } from "@/components/Inputs";
import { Popover } from "@/components/Overlay";
import { toast } from "@/components/Toast";
import { Card, Group, Row } from "@/components/Structure";
import { invoke } from "@/ipc/client";
import { cmd, type BuiltIns } from "@/ipc/types";
import { normalizeExeKey, TAGLINE_SOFT_LIMIT, taglineLengthState } from "@/lib/validation";
import { configStore, updateConfig } from "@/state/config";
import { engineStore } from "@/state/engine";
import { useStore } from "@/state/store";

export function TaglinesPane() {
  const config = useStore(configStore);
  const engine = useStore(engineStore);
  const [editing, setEditing] = useState<string | null>(null);
  const [builtIns, setBuiltIns] = useState<Record<string, string> | null>(null);
  const [prefill, setPrefill] = useState<{ exe: string; tagline: string } | null>(null);

  useEffect(() => {
    void invoke<BuiltIns>(cmd.getBuiltIns)
      .then((value) => setBuiltIns(value.taglines))
      .catch(() => setBuiltIns({}));
  }, []);

  if (!config) return null;

  const entries = Object.entries(config.taglines).sort(([a], [b]) => a.localeCompare(b));

  const writeMap = (map: Record<string, string>, message?: string) => {
    void updateConfig({ taglines: map }, "Couldn't save that tagline.").then((ok) => {
      if (ok && message) toast(message, { kind: "success" });
    });
  };

  const remove = (exe: string) => {
    const previous = config.taglines;
    const next = { ...previous };
    delete next[exe];
    void updateConfig({ taglines: next }, "Couldn't remove that tagline.").then((ok) => {
      if (ok) {
        toast(`Removed the tagline for ${exe}`, {
          action: { label: "Undo", run: () => writeMap(previous) },
        });
      }
    });
  };

  return (
    <>
      <Group
        title="Taglines"
        description="The second line under your name. A tagline here always wins over the automatic one."
      >
        <p className="t-caption">
          Resolution order: <strong>App Names override</strong> → <strong>your tagline below</strong> →{" "}
          <strong>details from the window title</strong> → <strong>built-in default</strong>.
        </p>

        <InsetList<[string, string]>
          ariaLabel="Taglines"
          items={entries}
          getKey={([exe]) => exe}
          filterText={([exe, tagline]) => `${exe} ${tagline}`}
          filterPlaceholder="Filter taglines"
          emptyTitle="No custom taglines"
          emptyHint="Without one, the second line comes from the window title when dynamic taglines are on."
          removeLabel="Remove"
          addLabel="Add tagline"
          onRemove={([exe]) => remove(exe)}
          renderAdd={(close) => (
            <TaglineForm
              initial={prefill ?? { exe: "", tagline: "" }}
              suggestions={engine.recentApps}
              existing={config.taglines}
              onSubmit={(exe, tagline) => {
                writeMap({ ...config.taglines, [exe]: tagline });
                setPrefill(null);
                close();
              }}
              onCancel={() => {
                setPrefill(null);
                close();
              }}
            />
          )}
          renderRow={([exe, tagline]) => (
            <TaglineRow
              exe={exe}
              tagline={tagline}
              recording={engine.app?.exe === exe}
              suggestions={engine.recentApps}
              existing={config.taglines}
              editing={editing === exe}
              onEdit={() => setEditing(editing === exe ? null : exe)}
              onCloseEdit={() => setEditing(null)}
              onSubmit={(nextTagline) => {
                writeMap({ ...config.taglines, [exe]: nextTagline });
                setEditing(null);
              }}
            />
          )}
          footnote={
            <span className="t-caption">
              Taglines are plain text. Anything longer than {TAGLINE_SOFT_LIMIT} characters may be truncated
              by Discord.
            </span>
          }
        />
      </Group>

      <Group
        title="Built-in taglines"
        description="Shipped with the app and used when nothing else applies. Read-only — add your own entry above to override one."
      >
        <Card>
          {builtIns === null ? (
            <Row label="Loading…" />
          ) : Object.keys(builtIns).length === 0 ? (
            <Row label="None available" description="The engine did not report any built-in taglines." />
          ) : (
            Object.entries(builtIns)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([exe, tagline]) => (
                <Row key={exe} label={<span className="t-mono">{exe}</span>} description={tagline}>
                  <Button variant="quiet" size="sm" onClick={() => setPrefill({ exe, tagline })}>
                    Override
                  </Button>
                </Row>
              ))
          )}
        </Card>
      </Group>
    </>
  );
}

/* ------------------------------------------------------------------ row --- */

interface TaglineRowProps {
  exe: string;
  tagline: string;
  recording: boolean;
  suggestions: string[];
  existing: Record<string, string>;
  editing: boolean;
  onEdit: () => void;
  onCloseEdit: () => void;
  onSubmit: (tagline: string) => void;
}

function TaglineRow({
  exe,
  tagline,
  recording,
  suggestions,
  existing,
  editing,
  onEdit,
  onCloseEdit,
  onSubmit,
}: TaglineRowProps) {
  const lengthState = taglineLengthState(tagline);

  return (
    <>
      <div className="inset-list__main">
        <span className="inset-list__value">
          {tagline}
          {recording ? <span className="t-caption"> — on screen now</span> : null}
        </span>
        <span className="inset-list__key">{exe}</span>
      </div>

      {lengthState !== "ok" ? (
        <span className={lengthState === "over" ? "counter counter--warn" : "counter"}>
          {tagline.length}/{TAGLINE_SOFT_LIMIT}
        </span>
      ) : null}

      <div className="inset-list__actions">
        <div className="popover-anchor">
          <IconButton
            label={`Edit tagline for ${exe}`}
            icon={<Pencil size={15} aria-hidden="true" />}
            onClick={onEdit}
          />
          <Popover open={editing} onClose={onCloseEdit}>
            <TaglineForm
              initial={{ exe, tagline }}
              suggestions={suggestions}
              existing={existing}
              editingKey={exe}
              onSubmit={(_exe, nextTagline) => onSubmit(nextTagline)}
              onCancel={onCloseEdit}
            />
          </Popover>
        </div>
      </div>
    </>
  );
}

/* ----------------------------------------------------------------- form --- */

interface TaglineFormProps {
  initial: { exe: string; tagline: string };
  suggestions: string[];
  existing: Record<string, string>;
  editingKey?: string;
  onSubmit: (exe: string, tagline: string) => void;
  onCancel: () => void;
}

function TaglineForm({ initial, suggestions, existing, editingKey, onSubmit, onCancel }: TaglineFormProps) {
  const [exe, setExe] = useState(initial.exe);
  const [tagline, setTagline] = useState(initial.tagline);

  const key = normalizeExeKey(exe || initial.exe);
  const duplicate = !editingKey && key !== "" && key in existing;
  const lengthState = taglineLengthState(tagline);
  const unknown = key !== "" && suggestions.length > 0 && !suggestions.includes(key);

  return (
    <>
      {editingKey ? (
        <span className="t-caption t-mono">{editingKey}</span>
      ) : (
        <TextField
          label="Executable"
          value={exe}
          onCommit={setExe}
          onDraftChange={setExe}
          placeholder="notion.exe"
          mono
          autoFocus
          ariaLabel="Executable name"
          error={duplicate ? "That app already has a tagline — edit it instead." : undefined}
        />
      )}

      <TextField
        label="Tagline"
        value={tagline}
        onCommit={setTagline}
        onDraftChange={setTagline}
        placeholder="Writing something serious"
        autoFocus={Boolean(editingKey)}
        ariaLabel="Tagline"
        maxLength={200}
      />

      <div className="preview-chip">
        <span>Playing this app</span>
        <strong>{tagline.trim() || "no tagline"}</strong>
        <span className={lengthState === "over" ? "counter counter--warn" : "counter"}>
          {tagline.trim().length}/{TAGLINE_SOFT_LIMIT}
        </span>
      </div>

      {lengthState === "over" ? (
        <span className="field__hint">Discord may truncate this. Consider shortening it.</span>
      ) : null}

      {unknown ? (
        <span className="field__hint">
          Nothing named <span className="t-mono">{key}</span> has been seen running yet.
        </span>
      ) : null}

      <div className="popover__actions">
        <Button variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          disabled={key === "" || tagline.trim() === "" || duplicate}
          onClick={() => onSubmit(key, tagline.trim())}
        >
          Save
        </Button>
      </div>
    </>
  );
}
