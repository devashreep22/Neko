import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "./Client.js";

const INITIAL = { phase: "loading", neko: null, activity: null, today: null };

/**
 * Polls the backend. phase: "loading" | "ready" | "unauthorized" | "unavailable".
 * On failure the last good data is kept so the cat does not vanish while
 * reconnecting. Polls slowly while the tab is hidden and backs off on errors.
 */
export function useNekoStatus({ intervalMs = 2000, hiddenIntervalMs = 10_000, client = api } = {}) {
  const [snap, setSnap] = useState(INITIAL);
  const refreshRef = useRef(() => {});

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    let failures = 0;
    let controller = null;

    const schedule = () => {
      const base = document.visibilityState === "hidden" ? hiddenIntervalMs : intervalMs;
      const delay = failures ? Math.min(30_000, base * 2 ** Math.min(failures, 4)) : base;
      timer = setTimeout(poll, delay);
    };

    async function poll() {
      controller = new AbortController();
      const opts = { signal: controller.signal };
      try {
        const [neko, activity, today] = await Promise.all([
          client.state(opts), client.current(opts), client.today(opts),
        ]);
        if (cancelled) return;
        failures = 0;
        setSnap({ phase: "ready", neko, activity, today });
      } catch (err) {
        if (cancelled || err?.name === "AbortError") return;
        failures += 1;
        const phase = err instanceof ApiError && err.kind === "unauthorized" ? "unauthorized" : "unavailable";
        setSnap((prev) => ({ ...prev, phase }));
      }
      if (!cancelled) schedule();
    }

    refreshRef.current = () => {
      clearTimeout(timer);
      controller?.abort();
      poll();
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [intervalMs, hiddenIntervalMs, client]);

  return { ...snap, refresh: () => refreshRef.current() };
}
