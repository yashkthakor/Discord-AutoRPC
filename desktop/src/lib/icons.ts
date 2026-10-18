/**
 * Resolved app icons.
 *
 * The engine already knows how to resolve an icon (override → cache → SteamGridDB →
 * extract + upload). The UI asks the backend for the URL and caches the answer for the
 * window's lifetime so scrolling a list never re-requests.
 */

import { useEffect, useState } from "react";
import { invoke } from "@/ipc/client";
import { cmd } from "@/ipc/types";

const cache = new Map<string, string | null>();

export function useAppIcon(exe: string | null): string | null {
  const [url, setUrl] = useState<string | null>(() => (exe ? (cache.get(exe) ?? null) : null));

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
  }, [exe]);

  return url;
}
