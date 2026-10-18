/**
 * Logs pane (L-1…L-12).
 *
 * Console-style, read-only, monospace. Structured lines (L-8) let us colour levels,
 * filter by minimum level (L-9) and search with highlighting (L-10) — none of which the
 * Qt build could do with a plain text edit.
 *
 * Rendering is capped: the store keeps a bounded ring buffer, and only the tail is
 * mounted, so a DEBUG storm cannot make the window janky (PERF-1).
 */

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactElement } from "react";
import {
  ArrowDownToLine,
  Copy,
  Download,
  Eraser,
  FolderOpen,
  RefreshCw,
  Search,
} from "lucide-react";
import { Button } from "@/components/Button";
import { SearchInput } from "@/components/Inputs";
import { ConfirmDialog } from "@/components/Overlay";
import { SegmentedControl } from "@/components/SegmentedControl";
import { toast } from "@/components/Toast";
import { Group } from "@/components/Structure";
import { invoke } from "@/ipc/client";
import { cmd, type LogLevel, type LogLine } from "@/ipc/types";
import { formatClockTime } from "@/lib/format";
import { clearLogView, logsStore } from "@/state/logs";
import { useStore } from "@/state/store";

const LEVELS: LogLevel[] = ["DEBUG", "INFO", "WARNING", "ERROR"];
const RENDER_CAP = 1200;

function rank(level: LogLevel): number {
  return LEVELS.indexOf(level);
}

export function LogsPane() {
  const lines = useStore(logsStore);
  const [level, setLevel] = useState<LogLevel>("DEBUG");
  const [query, setQuery] = useState("");
  const [following, setFollowing] = useState(true);
  const [resetOpen, setResetOpen] = useState(false);
  const viewRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef(-1);

  const counts = useMemo(() => {
    const tally: Record<LogLevel, number> = { DEBUG: 0, INFO: 0, WARNING: 0, ERROR: 0 };
    for (const line of lines) tally[line.level] += 1;
    return tally;
  }, [lines]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return lines.filter((line) => {
      if (rank(line.level) < rank(level)) return false;
      if (!needle) return true;
      return (
        line.message.toLowerCase().includes(needle) || line.logger.toLowerCase().includes(needle)
      );
    });
  }, [lines, level, query]);

  const visible = filtered.length > RENDER_CAP ? filtered.slice(filtered.length - RENDER_CAP) : filtered;

  // Follow the tail unless the user has scrolled up (L-2).
  useEffect(() => {
    if (!following) return;
    const view = viewRef.current;
    if (!view) return;
    view.scrollTop = view.scrollHeight;
  }, [visible.length, following]);

  const jumpToLatest = () => {
    setFollowing(true);
    const view = viewRef.current;
    if (view) view.scrollTop = view.scrollHeight;
  };

  /** Enter / Shift+Enter step through matches (L-10). */
  const stepMatch = (direction: 1 | -1) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return;
    const matches = visible.filter(
      (line) => line.message.toLowerCase().includes(needle) || line.logger.toLowerCase().includes(needle),
    );
    if (matches.length === 0) return;

    setFollowing(false);
    const next = (cursorRef.current + direction + matches.length) % matches.length;
    cursorRef.current = next;
    const target = viewRef.current?.querySelector(`[data-line="${matches[next]!.id}"]`);
    target?.scrollIntoView({ block: "center" });
  };

  const onSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      stepMatch(event.shiftKey ? -1 : 1);
    }
  };

  const copyVisible = async () => {
    const text = visible
      .map(
        (line) =>
          `[${line.displayTime ?? formatClockTime(line.ts)}] ${line.level} ${line.logger} - ${line.message}`,
      )
      .join("\n");
    if (!text) {
      toast("There is nothing to copy.");
      return;
    }
    try {
      await invoke(cmd.copyText, { text });
      toast(`Copied ${visible.length} lines`);
    } catch {
      toast("Couldn't copy to the clipboard.", { kind: "error" });
    }
  };

  const exportLogs = async () => {
    try {
      const path = await invoke<string | null>(cmd.exportLogs);
      if (path) toast(`Saved the log to ${path}`, { kind: "success" });
    } catch {
      toast("Couldn't export the log file.", { kind: "error" });
    }
  };

  const resetIconCache = async () => {
    try {
      const count = await invoke<number>(cmd.clearIconCache);
      toast(`Cleared ${count} cached icon${count === 1 ? "" : "s"}. Next detections will fetch fresh ones.`, {
        kind: "success",
      });
    } catch {
      toast("Couldn't clear the icon cache.", { kind: "error" });
    }
  };

  return (
    <Group
      title="Logs"
      description="Everything the engine has done, newest at the bottom. The file on disk keeps the last 200 lines plus three rotated backups."
    >
      <div className="log-shell">
        <div className="field__row" style={{ flexWrap: "wrap" }}>
          <SegmentedControl<LogLevel>
            ariaLabel="Minimum log level"
            value={level}
            onChange={setLevel}
            options={LEVELS.map((value) => ({ value, label: value === "WARNING" ? "Warn" : value.charAt(0) + value.slice(1).toLowerCase(), count: counts[value] }))}
          />

          <div onKeyDown={onSearchKeyDown}>
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder="Search messages (Enter for next)"
              ariaLabel="Search logs"
              icon={<Search size={14} aria-hidden="true" />}
            />
          </div>

          <span className="t-caption t-numeric">
            {filtered.length} of {lines.length} lines
            {filtered.length > visible.length ? ` (showing the last ${RENDER_CAP})` : ""}
          </span>
        </div>

        <div className="field__row" style={{ flexWrap: "wrap" }}>
          <Button
            variant="secondary"
            size="sm"
            icon={<ArrowDownToLine size={14} aria-hidden="true" />}
            aria-pressed={following}
            onClick={jumpToLatest}
          >
            {following ? "Following" : "Jump to latest"}
          </Button>
          <Button variant="secondary" size="sm" icon={<Copy size={14} aria-hidden="true" />} onClick={() => void copyVisible()}>
            Copy
          </Button>
          <Button variant="secondary" size="sm" icon={<Download size={14} aria-hidden="true" />} onClick={() => void exportLogs()}>
            Export…
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={<FolderOpen size={14} aria-hidden="true" />}
            onClick={() => void invoke(cmd.openLogFolder).catch(() => undefined)}
          >
            Open folder
          </Button>
          <span style={{ flex: 1 }} />
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} aria-hidden="true" />}
            onClick={() => setResetOpen(true)}
          >
            Reset icon cache
          </Button>
          <Button
            variant="quiet"
            size="sm"
            icon={<Eraser size={14} aria-hidden="true" />}
            onClick={() => {
              clearLogView();
              toast("Cleared the view. The log file was not touched.");
            }}
          >
            Clear view
          </Button>
        </div>

        <div className="log-shell__body">
          <div
            className="log"
            ref={viewRef}
            role="log"
            aria-live="off"
            aria-label="Log output"
            onScroll={(event) => {
              const element = event.currentTarget;
              const atBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
              setFollowing(atBottom);
            }}
          >
            {visible.length === 0 ? (
              <div className="empty">
                <span className="empty__title">No log lines yet</span>
                <span className="empty__hint">
                  {lines.length === 0
                    ? "The engine hasn't written anything since this window opened."
                    : "Every line is filtered out — raise or lower the level filter."}
                </span>
              </div>
            ) : (
              visible.map((line) => (
                <LogRow key={line.id} line={line} query={query.trim()} />
              ))
            )}
          </div>

          {!following && visible.length > 0 ? (
            <div className="jump">
              <Button variant="primary" size="sm" onClick={jumpToLatest}>
                Jump to latest
              </Button>
            </div>
          ) : null}
        </div>
      </div>

      <ConfirmDialog
        open={resetOpen}
        title="Reset the icon cache?"
        body="Every cached icon is deleted. The next time an app is detected its icon is extracted and uploaded again, which means a short burst of network requests."
        confirmLabel="Reset cache"
        onConfirm={() => void resetIconCache()}
        onClose={() => setResetOpen(false)}
      />
    </Group>
  );
}

function LogRow({ line, query }: { line: LogLine; query: string }) {
  return (
    <div className={`log__line log__line--${line.level}`} data-line={line.id}>
      <span className="log__ts t-numeric">{line.displayTime ?? formatClockTime(line.ts)}</span>
      <span className="log__logger" title={line.logger}>
        {line.logger}
      </span>
      <span className="log__msg">{highlight(line.message, query)}</span>
    </div>
  );
}

/** Case-insensitive highlight without dangerouslySetInnerHTML. */
function highlight(message: string, query: string) {
  if (!query) return message;

  const lowerMessage = message.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const parts: Array<string | ReactElement> = [];
  let index = 0;
  let key = 0;

  for (;;) {
    const found = lowerMessage.indexOf(lowerQuery, index);
    if (found === -1 || lowerQuery.length === 0) {
      parts.push(message.slice(index));
      break;
    }
    if (found > index) parts.push(message.slice(index, found));
    parts.push(
      <mark key={key++}>{message.slice(found, found + lowerQuery.length)}</mark>,
    );
    index = found + lowerQuery.length;
  }

  return parts;
}
