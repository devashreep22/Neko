import { useCallback, useState } from "react";

/** A UI preference remembered in this browser (never leaves the machine). */
export function usePreference(key, fallback) {
  const [value, setValue] = useState(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  });
  const update = useCallback((next) => {
    setValue(next);
    try {
      window.localStorage.setItem(key, JSON.stringify(next));
    } catch {
      /* storage unavailable: the preference just won't persist */
    }
  }, [key]);
  return [value, update];
}