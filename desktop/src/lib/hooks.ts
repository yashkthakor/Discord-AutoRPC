/** Small React hooks with no dependencies. */

import { useEffect, useRef, useState } from "react";

/** Re-render on an interval while `active`. Used for the ticking presence timer. */
export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [active, intervalMs]);

  return now;
}

/** Debounced mirror of a value — for validation that shouldn't flash while typing (OB-6). */
export function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}

/** `Ctrl+1…6` section shortcuts (A11 / D-030). */
export function useSectionShortcuts(count: number, onSelect: (index: number) => void): void {
  const handler = useRef(onSelect);
  handler.current = onSelect;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.ctrlKey || event.altKey || event.shiftKey || event.metaKey) return;
      const index = Number.parseInt(event.key, 10);
      if (Number.isNaN(index) || index < 1 || index > count) return;
      event.preventDefault();
      handler.current(index - 1);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [count]);
}
