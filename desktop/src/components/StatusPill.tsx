/**
 * Status pill.
 *
 * State is never conveyed by colour alone (A11Y-3): the pill always carries a text
 * label, and the dot only reinforces it.
 */

import type { ReactNode } from "react";

export type PillTone = "muted" | "ok" | "bad" | "live" | "plain";

export interface StatusPillProps {
  tone?: PillTone;
  children: ReactNode;
  mono?: boolean;
  title?: string;
}

export function StatusPill({ tone = "muted", children, mono = false, title }: StatusPillProps) {
  const classes = ["pill", tone === "plain" ? "" : `pill--${tone}`, mono ? "pill--mono" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes} title={title}>
      <span className="pill__dot" aria-hidden="true" />
      {children}
    </span>
  );
}
