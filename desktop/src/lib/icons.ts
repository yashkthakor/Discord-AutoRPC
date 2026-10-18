/**
 * Resolved app icons.
 *
 * The engine already knows how to resolve an icon (override → cache → SteamGridDB →
 * extract + upload). The UI asks the backend for the URL and caches the answer so
 * scrolling a list never re-requests. `invalidateAppIcon` drops that memo after an icon
 * cache clear, so a refresh is visible without reloading the window (T-030).
 */

import { useEffect, useState } from "react";
import { invoke } from "@/ipc/client";
import { cmd } from "@/ipc/types";

const cache = new Map<string, string | null>();
const listeners = new Set<() => void>();

/**
 * Drop memoized URLs — one app's, or every app's — and re-request them, so a cleared icon
 * shows up without a window reload (T-030).
 *
 * The engine fetches a cleared icon on its next poll, so a follow-up invalidation is
 * scheduled once one cycle has passed: the first pass usually still gets `null`.
 */
export function invalidateAppIcon(exe?: string): void {
  const drop = () => {
    if (exe) cache.delete(exe);
    else cache.clear();
    listeners.forEach((notify) => notify());
  };

  drop();
  window.setTimeout(drop, 7000);
}

export function useAppIcon(exe: string | null): string | null {
  const [url, setUrl] = useState<string | null>(() => (exe ? (cache.get(exe) ?? null) : null));
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const notify = () => setRevision((value) => value + 1);
    listeners.add(notify);
    return () => {
      listeners.delete(notify);
    };
  }, []);

  useEffect(() => {
    if (!exe) {
      setUrl(null);
      return;
    }

    const cached = cache.get(exe);
    if (cached !== undefined) {
      setUrl(cached);
      return;
    }

    let alive = true;
    void invoke<string | null>(cmd.appIconUrl, { exe })
      .then((value) => {
        cache.set(exe, value ?? null);
        if (alive) setUrl(value ?? null);
      })
      .catch(() => {
        cache.set(exe, null);
      });

    return () => {
      alive = false;
    };
  }, [exe, revision]);

  return url;
}
