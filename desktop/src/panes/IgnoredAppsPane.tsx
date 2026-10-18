/**
 * Ignored Apps pane (I-1…I-8).
 *
 * What the engine actually honours (`detector.is_ignored`), in one place:
 *   1. `config.ignored_exes` — the editable list, seeded with twelve Windows apps;
 *   2. `ignore_list.json` — what the Python tray's "Ignore current app" wrote;
 *   3. anything running from `%SystemRoot%` — hardcoded, not configurable.
 *
 * This pane shows (1) as the list you edit, (2) only if the startup migration could not fold
 * it in, and (3) as a note. Both the tray menu and this list write (1), so there is exactly
 * one store in play (A18 / D-037 / D-047).
 */

import { useEffect } from "react";
import { Ban, Info } from "lucide-react";
import { Button } from "@/components/Button";
import { InsetList } from "@/components/InsetList";
import { Card, Group, Row } from "@/components/Structure";
import { engineStore } from "@/state/engine";
import { ignoreApp, ignoredStore, refreshIgnored, unignoreApp } from "@/state/ignored";
import { useStore } from "@/state/store";
import { AddExeForm } from "./GeneralPane";

export function IgnoredAppsPane() {
  const ignored = useStore(ignoredStore);
  const engine = useStore(engineStore);

  useEffect(() => {
    void refreshIgnored();
  }, []);

  const managed = [...ignored.managed].sort((a, b) => a.localeCompare(b));
  const currentExe = engine.app?.exe ?? null;
  const shipped = new Set(ignored.defaults.map((item) => item.toLowerCase()));

  return (
    <>
      <Group
        title="Ignored Apps"
        description="Ignored apps are never broadcast, even when they are in the foreground. The tray's “Ignore” item and this list write the same setting."
      >
        <InsetList<string>
          ariaLabel="Ignored apps"
          items={managed}
          getKey={(item) => item}
          filterText={(item) => item}
          filterPlaceholder="Filter ignored apps"
          emptyTitle="Nothing is ignored"
          emptyHint="Without this list, whatever you have in front is broadcast — including apps you would rather not show."
          removeLabel="Remove"
          addLabel="Add ignored app"
          onRemove={(item) => void unignoreApp(item)}
          renderAdd={(close) => (
            <AddExeForm
              title="Ignore an application"
              hint="For example discord.exe — useful when Discord itself should show nothing."
              submitLabel="Ignore"
              onSubmit={(value) => {
                void ignoreApp(value);
                close();
              }}
              onCancel={close}
            />
          )}
          renderRow={(item) => (
            <div className="inset-list__main">
              <span className="inset-list__value">
                {item}
                {shipped.has(item.toLowerCase()) ? <span className="tag">shipped default</span> : null}
              </span>
              {currentExe === item ? (
                <span className="inset-list__key">Currently in the foreground</span>
              ) : null}
            </div>
          )}
          footnote={
            <span className="t-caption">
              Entries match on the executable name only, so every window of that app is skipped. Removing a
              shipped default is allowed — put it back if the presence starts flickering.
            </span>
          }
        />
      </Group>

      {ignored.legacy.length > 0 ? (
        <Group
          title="Added elsewhere"
          description="Entries in ignore_list.json that the startup migration could not fold into the list above. They are still honoured by the engine."
        >
          <Card>
            {[...ignored.legacy].sort().map((item) => (
              <Row key={item} label={<span className="t-mono">{item}</span>}>
                <Button
                  variant="quiet"
                  size="sm"
                  onClick={() => {
                    void ignoreApp(item).then(() => void refreshIgnored());
                  }}
                >
                  Copy into the list above
                </Button>
              </Row>
            ))}
          </Card>
        </Group>
      ) : null}

      <Group
        title="Always skipped"
        description="Hardcoded in the engine. There is no switch for this and there should not be one."
      >
        <p className="t-caption" style={{ display: "flex", gap: "var(--sp-2)", alignItems: "flex-start" }}>
          <Info size={14} aria-hidden="true" />
          <span>
            Anything running from <span className="t-mono">%SystemRoot%</span> — Explorer, the shell, the lock
            screen and the rest of Windows — is skipped so the presence does not flicker whenever you open the
            Start menu. Private and incognito browser windows are skipped too, under{" "}
            <strong>Hide private browsing</strong> in General.
          </span>
        </p>
      </Group>

      {currentExe && !ignored.managed.includes(currentExe) ? (
        <Group title="Quick action" description="The app in the foreground right now.">
          <Card>
            <Row label={<span className="t-mono">{currentExe}</span>} description={engine.app?.displayName}>
              <Button
                variant="secondary"
                size="sm"
                icon={<Ban size={14} aria-hidden="true" />}
                onClick={() => void ignoreApp(currentExe, engine.app?.displayName)}
              >
                Ignore
              </Button>
            </Row>
          </Card>
        </Group>
      ) : null}
    </>
  );
}
