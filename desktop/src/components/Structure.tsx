/** Layout primitives: grouped inset sections, label/control rows, empty states. */

import type { ReactNode } from "react";

export interface GroupProps {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}

/** A titled settings section. The card inside is an inset list (A1 / D-020). */
export function Group({ title, description, children }: GroupProps) {
  return (
    <section className="group" aria-label={title}>
      <div>
        <h2 className="group__title">{title}</h2>
        {description ? <p className="group__desc">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, pad = false }: { children: ReactNode; pad?: boolean }) {
  return <div className={pad ? "card card--pad" : "card"}>{children}</div>;
}

export interface RowProps {
  label: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  stack?: boolean;
}

/** Label left, control right, description under the label (A9 / A13). */
export function Row({ label, description, children, stack = false }: RowProps) {
  return (
    <div className={stack ? "row row--stack" : "row"}>
      <div className="row__text">
        <span className="row__label">{label}</span>
        {description ? <span className="row__desc">{description}</span> : null}
      </div>
      {children ? <div className="row__control">{children}</div> : null}
    </div>
  );
}

export function KV({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="kv">
      <span className="kv__k">{k}</span>
      <span className="kv__v">{children}</span>
    </div>
  );
}

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ icon, title, hint, action }: EmptyStateProps) {
  return (
    <div className="empty">
      {icon}
      <span className="empty__title">{title}</span>
      {hint ? <span className="empty__hint">{hint}</span> : null}
      {action}
    </div>
  );
}
