/** Switch (A13 / D-032): the only boolean control in the app. No checkboxes. */

export interface SwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Accessible name, since the visible label lives in the surrounding row. */
  label: string;
  disabled?: boolean;
}

export function Switch({ checked, onChange, label, disabled = false }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="switch"
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="switch__knob" />
    </button>
  );
}
