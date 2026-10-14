import { useEffect, useRef, useState } from "react";
import { BUBBLE_MS, COOLDOWN_MS, messageFor } from "./Messages.js";

/** Shows a short message when the state changes, never repeating it too soon. */
export function useBubble(state, enabled) {
  const [message, setMessage] = useState(null);
  const previous = useRef(null);
  const lastShown = useRef({});

  useEffect(() => {
    if (!enabled) {
      setMessage(null);
      return undefined;
    }
    if (state === previous.current) return undefined;
    previous.current = state;
    setMessage(null);
    const text = messageFor(state);
    const now = Date.now();
    const last = lastShown.current[state];
    if (!text || (last && now - last < COOLDOWN_MS)) return undefined;
    lastShown.current[state] = now;
    setMessage(text);
    const id = setTimeout(() => setMessage(null), BUBBLE_MS);
    return () => clearTimeout(id);
  }, [state, enabled]);

  return message;
}
