/** Formatting helpers. Pure, testable, no React. */

/** Duration for the Status pane timer and the status bar: `1:04:09` / `4:09`. */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}

/** `14:07:33` — matches the engine's log time format. */
export function formatClockTime(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** `code.exe` → `Code` — only used when no display name is available. */
export function titleFromExe(exe: string): string {
  const base = exe.replace(/\.exe$/i, "").replace(/[-_]+/g, " ").trim();
  if (!base) return exe;
  return base.charAt(0).toUpperCase() + base.slice(1);
}

export function truncateMiddle(value: string, max = 68): string {
  if (value.length <= max) return value;
  const head = Math.ceil((max - 1) / 2);
  const tail = Math.floor((max - 1) / 2);
  return `${value.slice(0, head)}…${value.slice(value.length - tail)}`;
}

export function pluralize(count: number, singular: string, plural?: string): string {
  return `${count} ${count === 1 ? singular : (plural ?? `${singular}s`)}`;
}
