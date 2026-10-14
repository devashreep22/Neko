import { useEffect, useState } from "react";
import { api } from "./Client.js";
import NekoCat from "./components/NekoCat/index.js";
import { useBubble } from "./UseBubble.js";
import { useNekoStatus } from "./UseNekoStatus.js";
import { usePreference } from "./UsePreference.js";
import { formatDuration } from "./Format.js";

export default function PetApp() {
  const { phase, neko, activity, refresh } = useNekoStatus({ intervalMs: 2000 });
  const [bubbles, setBubbles] = usePreference("neko.bubbles", true);
  const [animated, setAnimated] = usePreference("neko.animated", true);
  const [interactive, setInteractive] = useState(false);
  const [focusMessage, setFocusMessage] = useState(null);
  const state = neko?.state ?? "idle";
  const stateMessage = useBubble(state, bubbles && phase === "ready");
  const message = bubbles ? focusMessage || stateMessage : null;
  const tracking = neko?.tracking ?? "running";

  useEffect(() => {
    const stopInteraction = window.nekoDesktop?.onInteractionChange(setInteractive);
    const stopReaction = window.nekoDesktop?.onFocusReaction((text) => {
      setFocusMessage(text);
      window.setTimeout(() => setFocusMessage((current) => current === text ? null : current), 8000);
    });
    return () => { stopInteraction?.(); stopReaction?.(); };
  }, []);

  const toggleTracking = async () => {
    try {
      await (tracking === "paused" ? api.resume() : api.pause());
    } catch {
      // The next status poll reports backend or authentication failures.
    }
    refresh();
  };

  return (
    <main className={`pet-shell${interactive ? " is-interactive" : ""}`}>
      <NekoCat state={phase === "ready" || neko ? state : "idle"} message={message} size={280} animated={animated} />
      <section className="pet-controls" aria-label="NekoAI desktop pet controls">
        <p aria-live="polite">
          {phase === "loading" ? "Connecting to NekoAI..." :
            phase === "unauthorized" ? "NekoAI sign-in is unavailable." :
              phase === "unavailable" ? "Backend disconnected; reconnecting..." :
                `${activity?.category ?? "No activity"}${activity?.app ? ` | ${activity.app}` : ""}${activity?.session_seconds > 0 ? ` | ${formatDuration(activity.session_seconds)}` : ""}`}
        </p>
        {neko?.reason && <p>{neko.reason}</p>}
        <div className="pet-actions">
          {neko && tracking !== "unavailable" && (
            <button className="app-button" onClick={toggleTracking}>
              {tracking === "paused" ? "Resume" : "Pause"}
            </button>
          )}
          <button className="app-button" onClick={() => window.nekoDesktop?.openDashboard()}>
            Today &amp; dashboard
          </button>
          <button className="app-button" onClick={() => window.nekoDesktop?.setInteractive(false)}>Done moving</button>
          <button className="app-button" onClick={() => window.nekoDesktop?.hidePet()}>Hide Neko</button>
        </div>
        <div className="pet-preferences">
          <label><input type="checkbox" checked={bubbles} onChange={(e) => setBubbles(e.target.checked)} /> Speech bubbles</label>
          <label><input type="checkbox" checked={animated} onChange={(e) => setAnimated(e.target.checked)} /> Animations</label>
        </div>
        <p>Ctrl+Alt+N toggles mouse interaction | Ctrl+Alt+D opens the dashboard</p>
      </section>
    </main>
  );
}
