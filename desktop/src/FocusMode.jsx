import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./Client.js";
import { formatDuration } from "./Format.js";

const PRESETS = [15, 25, 30, 45, 60];

function failureMessage(error) {
  if (error?.kind === "unauthorized") return "Sign in again to manage focus sessions.";
  if (error?.kind === "unavailable") return "NekoAI is disconnected. Focus controls are unavailable until it reconnects.";
  if (error instanceof ApiError && error.status >= 500) return `The focus service failed (HTTP ${error.status}).`;
  return error?.message || "The focus session request failed.";
}

export default function FocusMode({ activity }) {
  const [session, setSession] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [detail, setDetail] = useState(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [duration, setDuration] = useState(25);
  const [customDuration, setCustomDuration] = useState(25);
  const [domainsText, setDomainsText] = useState("");
  const [mode, setMode] = useState("monitor");
  const [browserAddress, setBrowserAddress] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const wasOpen = useRef(false);
  const observedDistractions = useRef(null);
  const lastDistractionReaction = useRef(0);

  const refresh = useCallback(async () => {
    const [active, saved] = await Promise.all([api.focus.active(), api.focus.sessions()]);
    setSession(active.session);
    setSessions(saved.sessions || []);
  }, []);

  useEffect(() => {
    let live = true;
    const poll = async () => {
      try {
        const active = await api.focus.active();
        if (live) {
          if (active.session) {
            const count = active.session.distraction_count || 0;
            if (observedDistractions.current !== null && count > observedDistractions.current && Date.now() - lastDistractionReaction.current >= 5 * 60_000) {
              window.nekoDesktop?.focusReaction?.("A small detour happened. Take a breath and return when you're ready.");
              lastDistractionReaction.current = Date.now();
            }
            observedDistractions.current = count;
          } else observedDistractions.current = null;
          if (wasOpen.current && !active.session) {
            const saved = await api.focus.sessions();
            setSessions(saved.sessions || []);
          }
          wasOpen.current = Boolean(active.session);
          setSession(active.session);
        }
      } catch (reason) {
        if (live) setError(failureMessage(reason));
      }
    };
    const loadSaved = async () => {
      try {
        const saved = await api.focus.sessions();
        if (live) setSessions(saved.sessions || []);
      } catch (reason) {
        if (live) setError(failureMessage(reason));
      }
    };
    poll();
    loadSaved();
    const timer = window.setInterval(poll, 1000);
    return () => { live = false; window.clearInterval(timer); };
  }, []);

  const perform = async (action) => {
    setBusy(true);
    setError("");
    try {
      const next = await action();
      if (next?.id) setSession(next);
      await refresh();
      wasOpen.current = Boolean((await api.focus.active()).session);
      setDetail(null);
      return true;
    } catch (reason) { setError(failureMessage(reason)); }
    finally { setBusy(false); }
  };

  const react = (text) => window.nekoDesktop?.focusReaction?.(text);

  const start = (event) => {
    event.preventDefault();
    const minutes = duration === "custom" ? Number(customDuration) : Number(duration);
    perform(() => api.focus.start({
      task_title: title,
      description: description.trim() || null,
      duration_minutes: minutes,
      approved_domains: domainsText.split(/[\n,]/).map((domain) => domain.trim()).filter(Boolean),
      enforcement_mode: mode,
    })).then((succeeded) => { if (succeeded) { setTitle(""); react("One step at a time. You can do this!"); } });
  };

  const end = () => {
    if (!window.confirm("End this focus session now? The saved session will be marked cancelled if its planned time is not complete.")) return;
    perform(() => api.focus.end()).then((succeeded) => { if (succeeded) react("Session saved. Nice work showing up!"); });
  };

  const exportSessions = () => {
    const blob = new Blob([JSON.stringify(sessions, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "neko-focus-sessions.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const active = session && ["active", "paused"].includes(session.status);
  const openAllowedSite = async () => {
    try {
      if (!window.nekoDesktop?.openFocusBrowser) throw new Error("Neko Focus Browser is available only in the NekoAI desktop application.");
      await window.nekoDesktop.openFocusBrowser(browserAddress);
      setError("");
    } catch (reason) { setError(failureMessage(reason)); }
  };

  return (
    <section className="dashboard-page focus-page">
      <div className="dashboard-title"><div><p className="eyebrow">A session for the task in front of you</p><h1>Focus Mode</h1><p>Focus time records the timer and detected app switches. It does not prove productivity.</p></div></div>
      {error && <p className="focus-error" role="alert">{error}</p>}
      {active ? (
        <article className="panel focus-active" aria-live="polite">
      <div className="focus-active-heading"><div><p className="eyebrow">{session.status === "paused" ? "Paused" : "Focus session active"}</p><h2>{session.task_title}</h2>{session.description && <p>{session.description}</p>}</div><strong className="focus-clock">{formatDuration(session.remaining_seconds)}</strong></div>
          <div className="focus-progress"><span style={{ width: `${session.progress * 100}%` }} /></div>
          <div className="focus-metrics"><span>Elapsed <strong>{formatDuration(session.active_seconds)}</strong></span><span>Current app <strong>{activity?.app || "Waiting for sample"}</strong></span><span>Distractions <strong>{session.distraction_count}</strong></span><span>Outside task <strong>{formatDuration(session.outside_task_seconds)}</strong></span></div>
          {session.enforcement_mode === "controlled_browser" && <p className={`focus-enforcement ${session.enforcement_status}`}>Neko Focus Browser: {session.enforcement_status === "enforced" ? "allowlist enforcement confirmed" : session.enforcement_status === "paused" ? "paused" : "unavailable or not confirmed"}. Other browsers are monitored as app switches, not blocked.</p>}
          {session.enforcement_mode === "monitor" && <p className="focus-enforcement">Monitoring app switches only. Website navigation is not blocked.</p>}
          {session.current_domain && <p>Current Focus Browser site: <strong>{session.current_domain}</strong></p>}
          <p className="focus-neko">{session.status === "paused" ? "Neko is taking a quiet pause with you." : session.remaining_seconds === 0 ? "Neko celebrates your completed focus time." : "Neko is cheering you on. Your speech-bubble preference is unchanged."}</p>
          <div className="focus-actions">{session.status === "active" ? <button className="outline-button" disabled={busy} onClick={() => perform(() => api.focus.pause()).then((ok) => ok && react("Focus paused. Take the time you need."))}>Pause focus</button> : <button className="outline-button" disabled={busy} onClick={() => perform(() => api.focus.resume()).then((ok) => ok && react("Welcome back. Your focus session has resumed."))}>Resume focus</button>}{session.enforcement_mode === "controlled_browser" && session.status === "active" && <div className="focus-browser-launch"><label>Open an approved website<input value={browserAddress} onChange={(event) => setBrowserAddress(event.target.value)} placeholder="https://leetcode.com" /></label><button className="outline-button" disabled={busy || !browserAddress.trim()} onClick={openAllowedSite}>Open in Neko Focus Browser</button></div>}<button className="outline-button" disabled={busy} onClick={end}>End session</button></div>
        </article>
      ) : (
        <form className="panel focus-setup" onSubmit={start}>
          <h2>Plan a focus session</h2>
          <label>Task title<input required maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Solve LeetCode problems" /></label>
          <label>Optional goal<textarea maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Complete two array problems" /></label>
          <fieldset><legend>Duration</legend><div className="focus-presets">{PRESETS.map((minutes) => <button type="button" key={minutes} className={duration === minutes ? "selected" : ""} onClick={() => setDuration(minutes)}>{minutes} min</button>)}<button type="button" className={duration === "custom" ? "selected" : ""} onClick={() => setDuration("custom")}>Custom</button></div>{duration === "custom" && <input aria-label="Custom duration in minutes" type="number" min="1" max="240" value={customDuration} onChange={(e) => setCustomDuration(e.target.value)} />}</fieldset>
          <label>Approved websites <span className="focus-help">One domain per line. Use *.example.com only when you want subdomains included.</span><textarea value={domainsText} onChange={(e) => setDomainsText(e.target.value)} placeholder="leetcode.com" /></label>
          <label>Session mode<select value={mode} onChange={(e) => setMode(e.target.value)}><option value="monitor">Monitor app switches</option><option value="controlled_browser">Neko Focus Browser with website allowlist</option></select></label>
          <p className="focus-help">The controlled browser applies its allowlist inside Neko Focus Browser only. It cannot block navigation in Chrome, Edge, or other external browsers.</p>
          <button className="primary-button" type="submit" disabled={busy}>{busy ? "Starting…" : "Start Focus Session"}</button>
        </form>
      )}
      <article className="panel focus-history"><div className="panel-heading"><div><h2>Focus history</h2><p>Saved locally on this computer</p></div><button className="outline-button" type="button" onClick={exportSessions} disabled={!sessions.length}>Export JSON</button></div>
        {!sessions.length ? <p className="empty-state">No focus sessions have been saved yet.</p> : <ol className="focus-session-list">{sessions.map((item) => <li key={item.id}><button type="button" onClick={async () => { try { setDetail(await api.focus.detail(item.id)); setError(""); } catch (reason) { setError(failureMessage(reason)); } }}><span><strong>{item.task_title}</strong><small>{new Date(item.started_at).toLocaleString()} · {item.status}</small></span><span>{formatDuration(item.active_seconds)} / {formatDuration(item.planned_seconds)}</span></button></li>)}</ol>}
        {detail && <div className="focus-detail"><h3>{detail.task_title}</h3><p>{detail.description || "No goal recorded."}</p><p>{detail.completion_reason || detail.status} · Started {new Date(detail.started_at).toLocaleString()}{detail.ended_at ? ` · Ended ${new Date(detail.ended_at).toLocaleString()}` : ""}</p><p>Planned {formatDuration(detail.planned_seconds)} · Active {formatDuration(detail.active_seconds)} · Paused {formatDuration(detail.paused_seconds)}</p><p>{detail.distraction_count} distractions · {formatDuration(detail.outside_task_seconds)} outside-task time</p><p>Approved domains: {detail.approved_domains?.join(", ") || "None"}</p>{detail.activity_categories?.length > 0 && <p>Tracked categories: {detail.activity_categories.map((item) => `${item.category} ${formatDuration(item.seconds)}`).join(" · ")}</p>}{detail.distractions?.length > 0 && <ul>{detail.distractions.map((item) => <li key={item.id}>{item.kind}{item.app_name ? ` · ${item.app_name}` : ""}{item.domain ? ` · ${item.domain}` : ""} · {formatDuration(item.duration_seconds)}</li>)}</ul>}</div>}
      </article>
    </section>
  );
}
