/**
 * RenameForm (R-2…R-8) — shared by the Status pane sheet and the standalone window
 * (A21 / D-040). One component, two homes.
 *
 * Semantics that must not drift (R-4 / R-7):
 * - an empty tagline means "fall back to automatic", not "show nothing";
 * - applying is instant — no restart, no waiting for the 30 s config reload.
 */

import { useState } from "react";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Inputs";
import { invoke } from "@/ipc/client";
import { cmd } from "@/ipc/types";
import { toast } from "@/components/Toast";
import { normalizeExeKey, TAGLINE_SOFT_LIMIT } from "@/lib/validation";

export interface RenameFormProps {
  exe: string;
  initialName: string;
  initialTagline: string;
  recentApps?: string[];
  onDone: () => void;
  onCancel: () => void;
}

export function RenameForm({
  exe,
  initialName,
  initialTagline,
  recentApps = [],
  onDone,
  onCancel,
}: RenameFormProps) {
  const [target, setTarget] = useState(exe);
  const [name, setName] = useState(initialName);
  const [tagline, setTagline] = useState(initialTagline);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);

  const nameError = touched && !name.trim() ? "Display Name cannot be empty." : undefined;
  const overLimit = tagline.trim().length > TAGLINE_SOFT_LIMIT;

  const apply = async () => {
    setTouched(true);
    if (!name.trim()) return;

    setBusy(true);
    try {
      await invoke(cmd.renameApp, {
        exe: normalizeExeKey(target),
        name: name.trim(),
        tagline: tagline.trim(),
      });
      toast(`Now showing “${name.trim()}”`, { kind: "success" });
      onDone();
    } catch {
      toast("Couldn't apply that rename.", { kind: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="field" style={{ gap: "var(--sp-4)" }}>
      {recentApps.length > 0 ? (
        <label className="field">
          <span className="field__label">Application</span>
          <select className="select" value={target} onChange={(e) => setTarget(e.target.value)}>
            {[exe, ...recentApps.filter((x) => x !== exe)].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <span className="field__hint">
            Recently detected apps are listed so you can rename something that isn&rsquo;t in front.
          </span>
        </label>
      ) : null}

      <TextField
        label="Custom Display Name (shown as 'Playing ...')"
        value={name}
        onCommit={setName}
        onDraftChange={setName}
        placeholder="e.g. PhotoCraft or Photoshop"
        error={nameError}
        autoFocus
      />

      <TextField
        label="Custom Tagline (optional details line)"
        value={tagline}
        onCommit={setTagline}
        onDraftChange={setTagline}
        placeholder="Leave blank to keep automatic dynamic detail"
        hint={`Leave blank to fall back to the automatic tagline. ${tagline.trim().length}/${TAGLINE_SOFT_LIMIT} characters.`}
      />

      <div className="rename-preview">
        <span className="rename-preview__now">Preview</span>
        <span className="rename-preview__name">Playing {name.trim() || "…"}</span>
        <span className="rename-preview__tagline">
          {tagline.trim() || "Automatic detail from the window title"}
        </span>
      </div>

      {overLimit ? (
        <span className="counter counter--warn">
          Discord truncates past {TAGLINE_SOFT_LIMIT} characters.
        </span>
      ) : null}

      <div style={{ display: "flex", gap: "var(--sp-2)", justifyContent: "flex-end" }}>
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="primary" onClick={() => void apply()} disabled={busy}>
          Save &amp; Apply Instantly
        </Button>
      </div>
    </div>
  );
}
