/**
 * Text, search, number and select controls.
 *
 * Commit model (A12 / D-031): text commits on blur or Enter, never per keystroke.
 * A value pushed by the backend while the field is focused is *not* applied — the
 * user's in-progress edit always wins (SEM-7).
 */

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface TextFieldProps {
  value: string;
  onCommit: (next: string) => void;
  /** Called on every keystroke — for live previews only. Never for writes. */
  onDraftChange?: (draft: string) => void;
  label?: string;
  placeholder?: string;
  hint?: string;
  error?: string;
  valid?: boolean;
  mono?: boolean;
  password?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  maxLength?: number;
  ariaLabel?: string;
  width?: number | string;
}

export function TextField({
  value,
  onCommit,
  onDraftChange,
  label,
  placeholder,
  hint,
  error,
  valid = false,
  mono = false,
  password = false,
  disabled = false,
  autoFocus = false,
  maxLength,
  ariaLabel,
  width,
}: TextFieldProps) {
  const [draft, setDraft] = useState(value);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setDraft(value);
  }, [value, focused]);

  const commit = () => {
    if (draft !== value) onCommit(draft);
  };

  const classes = [
    "input",
    mono ? "input--mono" : "",
    error ? "input--invalid" : "",
    !error && valid ? "input--valid" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      commit();
    } else if (event.key === "Escape") {
      setDraft(value);
      onDraftChange?.(value);
      event.currentTarget.blur();
    }
  };

  return (
    <div className="field" style={width ? { width } : undefined}>
      {label ? <label className="field__label">{label}</label> : null}
      <input
        className={classes}
        type={password ? "password" : "text"}
        value={draft}
        placeholder={placeholder}
        disabled={disabled}
        autoFocus={autoFocus}
        maxLength={maxLength}
        aria-label={ariaLabel ?? label}
        aria-invalid={error ? true : undefined}
        spellCheck={false}
        autoComplete="off"
        onChange={(e) => {
          setDraft(e.target.value);
          onDraftChange?.(e.target.value);
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          commit();
        }}
        onKeyDown={handleKeyDown}
      />
      {error ? (
        <span className="field__error">{error}</span>
      ) : hint ? (
        <span className="field__hint">{hint}</span>
      ) : null}
    </div>
  );
}

export interface SearchInputProps {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  ariaLabel: string;
  icon?: ReactNode;
}

export function SearchInput({ value, onChange, placeholder, ariaLabel, icon }: SearchInputProps) {
  return (
    <div className="search">
      {icon}
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={ariaLabel}
        spellCheck={false}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

export interface NumberFieldProps {
  value: number;
  onCommit: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  ariaLabel: string;
  disabled?: boolean;
}

/** Bounded numeric field with a stepper. Stepper clicks debounce; blur/Enter commits. */
export function NumberField({
  value,
  onCommit,
  min,
  max,
  step = 1,
  unit,
  ariaLabel,
  disabled = false,
}: NumberFieldProps) {
  const [draft, setDraft] = useState(String(value));
  const [focused, setFocused] = useState(false);
  const debounce = useRef<number | null>(null);

  useEffect(() => {
    if (!focused) setDraft(String(value));
  }, [value, focused]);

  useEffect(
    () => () => {
      if (debounce.current !== null) window.clearTimeout(debounce.current);
    },
    [],
  );

  const clamp = (n: number) => Math.min(max, Math.max(min, n));

  const commitValue = (raw: string) => {
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) {
      setDraft(String(value));
      return;
    }
    const next = clamp(parsed);
    setDraft(String(next));
    if (next !== value) onCommit(next);
  };

  const nudge = (delta: number) => {
    const current = Number.parseInt(draft, 10);
    const base = Number.isNaN(current) ? value : current;
    const next = clamp(base + delta);
    setDraft(String(next));
    if (debounce.current !== null) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      debounce.current = null;
      if (next !== value) onCommit(next);
    }, 350);
  };

  return (
    <div className="number-field">
      <input
        inputMode="numeric"
        value={draft}
        aria-label={ariaLabel}
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value.replace(/[^\d]/g, ""))}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          commitValue(draft);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitValue(draft);
          if (e.key === "ArrowUp") {
            e.preventDefault();
            nudge(step);
          }
          if (e.key === "ArrowDown") {
            e.preventDefault();
            nudge(-step);
          }
          if (e.key === "Escape") setDraft(String(value));
        }}
      />
      {unit ? <span className="number-field__unit">{unit}</span> : null}
      <div className="number-field__steppers">
        <button
          type="button"
          className="number-field__stepper"
          aria-label="Increase"
          disabled={disabled || Number.parseInt(draft, 10) >= max}
          onClick={() => nudge(step)}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M5 1.5 8.5 7h-7L5 1.5Z" fill="currentColor" />
          </svg>
        </button>
        <button
          type="button"
          className="number-field__stepper"
          aria-label="Decrease"
          disabled={disabled || Number.parseInt(draft, 10) <= min}
          onClick={() => nudge(-step)}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M5 8.5 1.5 3h7L5 8.5Z" fill="currentColor" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export interface SelectProps<T extends string> {
  value: T;
  options: ReadonlyArray<{ value: T; label: string }>;
  onChange: (next: T) => void;
  ariaLabel: string;
  disabled?: boolean;
}

export function Select<T extends string>({ value, options, onChange, ariaLabel, disabled }: SelectProps<T>) {
  return (
    <select
      className="select"
      value={value}
      aria-label={ariaLabel}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as T)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
