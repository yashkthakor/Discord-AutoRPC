/** The Settings window: sidebar + status strip + the active pane. */

import { useState } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { Button } from "@/components/Button";
import { invoke } from "@/ipc/client";
import { cmd, SECTIONS, type SectionId } from "@/ipc/types";
import { useSectionShortcuts } from "@/lib/hooks";
import { configStore } from "@/state/config";
import { engineStore } from "@/state/engine";
import { ignoredStore } from "@/state/ignored";
import { useStore } from "@/state/store";
import { AppNamesPane } from "@/panes/AppNamesPane";
import { GeneralPane } from "@/panes/GeneralPane";
import { IgnoredAppsPane } from "@/panes/IgnoredAppsPane";
import { LogsPane } from "@/panes/LogsPane";
import { StatusPane } from "@/panes/StatusPane";
import { TaglinesPane } from "@/panes/TaglinesPane";
import { Sidebar } from "./Sidebar";
import { StatusHeader } from "./StatusHeader";

export function SettingsWindow() {
  const [active, setActive] = useState<SectionId>("status");
  const engine = useStore(engineStore);
  const config = useStore(configStore);
  const ignored = useStore(ignoredStore);

  useSectionShortcuts(SECTIONS.length, (index) => {
    const section = SECTIONS[index];
    if (section) setActive(section.id);
  });

  const counts: Partial<Record<SectionId, number>> = {
    apps: config ? Object.keys(config.overrides).length : 0,
    taglines: config ? Object.keys(config.taglines).length : 0,
    ignored: ignored.managed.length + ignored.legacy.length,
  };

  return (
    <div className="app">
      <Sidebar active={active} onSelect={setActive} counts={counts} />

      <main className="main">
        {engine.engine === "offline" ? (
          <div className="banner" role="status">
            <AlertTriangle size={14} aria-hidden="true" />
            <span>
              The engine isn&rsquo;t responding. Detection and presence are paused; your settings are
              safe.
            </span>
            <span style={{ flex: 1 }} />
            <Button variant="quiet" size="sm" onClick={() => void invoke(cmd.openLog).catch(() => undefined)}>
              Open log
            </Button>
          </div>
        ) : null}

        {engine.engine !== "offline" && !engine.configured ? (
          <div className="banner" role="status">
            <Info size={14} aria-hidden="true" className="t-secondary" />
            <span>Discord isn&rsquo;t set up yet, so nothing is being broadcast.</span>
            <span style={{ flex: 1 }} />
            <Button
              variant="quiet"
              size="sm"
              onClick={() => void invoke(cmd.openOnboarding).catch(() => undefined)}
            >
              Set up Discord
            </Button>
          </div>
        ) : null}

        <StatusHeader />

        <div className="page">
          <div className="page__inner">
            {active === "status" ? <StatusPane onNavigate={setActive} /> : null}
            {active === "general" ? <GeneralPane /> : null}
            {active === "apps" ? <AppNamesPane /> : null}
            {active === "taglines" ? <TaglinesPane /> : null}
            {active === "ignored" ? <IgnoredAppsPane /> : null}
            {active === "logs" ? <LogsPane /> : null}
          </div>
        </div>
      </main>
    </div>
  );
}
