import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "quiet" | "dangerText";

const VARIANT_CLASS: Record<Variant, string> = {
  primary: "btn--primary",
  secondary: "btn--secondary",
  danger: "btn--danger",
  quiet: "btn--quiet",
  dangerText: "btn--danger-text",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "md" | "sm";
  icon?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  children,
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  const classes = ["btn", VARIANT_CLASS[variant], size === "sm" ? "btn--sm" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <button type={type} className={classes} {...rest}>
      {icon}
      {children}
    </button>
  );
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required: icon-only controls must be labelled (A11Y-2). */
  label: string;
  icon: ReactNode;
  tone?: "default" | "danger";
}

export function IconButton({ label, icon, tone = "default", className, ...rest }: IconButtonProps) {
  const classes = ["icon-btn", tone === "danger" ? "icon-btn--danger" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <button type="button" className={classes} aria-label={label} title={label} {...rest}>
      {icon}
    </button>
  );
}
