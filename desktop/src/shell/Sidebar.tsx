/** Sidebar navigation (SS-1 / A11 / D-030). Six panes, plain-text labels, no emoji. */

import type { ReactNode } from "react";
import {
  Activity,
  AppWindow,
  EyeOff,
  MessageSquareText,
  ScrollText,
  Settings2,
} from "lucide-react";
import { SECTIONS, type SectionId } from "@/ipc/types";

const ICONS: Record<SectionId, ReactNode> = {
  status: <Activity size={16} aria-hidden="true" />,
  general: <Settings2 size={16} aria-hidden="true" />,
  apps: <AppWindow size={16} aria-hidden="true" />,
  taglines: <MessageSquareText size={16} aria-hidden="true" />,
  ignored: <EyeOff size={16} aria-hidden="true" />,
  logs: <ScrollText size={16} aria-hidden="true" />,
};

export interface SidebarProps {
  active: SectionId;
  onSelect: (section: SectionId) => void;
  counts: Partial<Record<SectionId, number>>;
}

export function Sidebar({ active, onSelect, counts }: SidebarProps) {
  return (
    <nav className="sidebar" aria-label="Settings sections">
      {/* The top of the sidebar is the window's drag handle above the navigation — the strip
          a macOS window keeps free for its traffic lights (D-055). */}
      <div className="sidebar__drag" data-tauri-drag-region />
      <span className="sidebar__heading">Discord AutoRPC</span>
      {SECTIONS.map((section, index) => {
        const count = counts[section.id];
        const shortcut = `Ctrl+${index + 1}`;
        return (
          <button
            key={section.id}
            type="button"
            className="sidebar__item"
            aria-current={section.id === active}
            title={`${section.label} (${shortcut})`}
            onClick={() => onSelect(section.id)}
          >
            {ICONS[section.id]}
            <span>{section.label}</span>
            {typeof count === "number" && count > 0 ? (
              <span className="sidebar__count t-numeric">{count}</span>
            ) : null}
            <span className="visually-hidden">{shortcut}</span>
          </button>
        );
      })}
    </nav>
  );
}
