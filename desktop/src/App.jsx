import { useEffect, useMemo, useState } from "react";
import { api } from "./Client.js";
import { ApiError } from "./Client.js";
import SignInPage from "./SignInPage.jsx";
import FocusMode from "./FocusMode.jsx";
import NekoCat from "./components/NekoCat/index.js";
import TodayPanel from "./TodayPanel.jsx";
import { useNekoStatus } from "./UseNekoStatus.js";
import { useBubble } from "./UseBubble.js";
import { usePreference } from "./UsePreference.js";
import { formatDuration } from "./Format.js";
import "./App.css";

const TRACKING_LABEL = { running: "Tracking is on", paused: "Tracking is paused", unavailable: "Tracking unavailable" };

function DashboardApp({ pollMs = 5000, user, onSignOut }) {
  const { phase, neko, activity, today, refresh } = useNekoStatus({ intervalMs: pollMs });
  const [page, setPage] = useState("home");
  const [petEnabled, setPetEnabled] = usePreference("neko.desktopEnabled", false);
  const [bubbles, setBubbles] = usePreference("neko.bubbles", true);
  const [animated, setAnimated] = usePreference("neko.animated", true);
  const [petVisible, setPetVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const electron = Boolean(window.nekoDesktop);
  const homeMessage = useBubble(neko?.state ?? "idle", bubbles && phase === "ready");
  const [history, setHistory] = useState(null);
  const [historyError, setHistoryError] = useState("");
  const [focusAnalytics, setFocusAnalytics] = useState(null);
  const [focusAnalyticsError, setFocusAnalyticsError] = useState("");

  const loadDashboard = async () => {
    setPage("dashboard");
    setHistoryError("");
    setFocusAnalyticsError("");
    const [activityResult, focusResult] = await Promise.allSettled([api.history(14), api.focusAnalytics(7)]);
    if (activityResult.status === "fulfilled") {
      const activityReport = activityResult.value;
      setHistory(activityReport);
      if (activityReport.data_status && activityReport.data_status !== "available") {
        setHistoryError(activityReport.data_status === "missing"
          ? "The local activity log has not been created yet. New completed activity will appear here."
          : "The local activity log exists but cannot be read. Existing records have been preserved.");
      }
    } else {
      const error = activityResult.reason;
      setHistoryError(error instanceof ApiError && error.kind === "unauthorized"
        ? "Your sign-in expired. Sign in again to view saved activity."
        : error instanceof ApiError && error.kind === "unavailable"
          ? "NekoAI is disconnected. Saved activity could not be retrieved."
          : `The saved activity request failed${error?.status ? ` (HTTP ${error.status})` : ""}. Retry after checking the backend.`);
    }
    if (focusResult.status === "fulfilled") setFocusAnalytics(focusResult.value);
    else setFocusAnalyticsError(focusResult.reason?.kind === "unavailable"
      ? "Focus analytics are unavailable while NekoAI is disconnected."
      : `Focus analytics request failed${focusResult.reason?.status ? ` (HTTP ${focusResult.reason.status})` : ""}.`);
  };

  const allowPet = async () => {
    if (!electron) {
      setNotice("The desktop pet needs the installed NekoAI desktop app. Start it with Start_NekoAI.bat, then choose Allow Neko on Desktop there.");
      return;
    }
    setPending(true);
    setNotice("");
    try {
      const shown = await window.nekoDesktop.enablePet();
      if (!shown) throw new Error("The desktop pet window is not available.");
      setPetEnabled(true);
      setPetVisible(true);
      setNotice("Neko is now on your desktop. Use the controls below to move, hide, or show your companion.");
    } catch (error) { setNotice(error.message || "Neko could not be shown. Please restart the desktop app."); }
    finally { setPending(false); }
  };

  const hidePet = async () => {
    if (!electron) { setNotice("The desktop pet can only be hidden from the installed NekoAI app."); return; }
    const hidden = await window.nekoDesktop.hidePet();
    if (hidden) { setPetVisible(false); setNotice("Neko is hidden. Choose Show Neko on Desktop whenever you want it back."); }
  };

  const movePet = async () => {
    if (!electron) return;
    const enabled = await window.nekoDesktop.setInteractive(true);
    if (enabled) setNotice("Neko can now receive mouse input. Drag the cat to move it; press Ctrl+Alt+N when you are done.");
  };

  const deferPet = async () => {
    if (electron && petVisible) await hidePet();
    setPetEnabled(false);
    setNotice("No problem. Neko stays hidden. You can allow the desktop companion whenever you are ready.");
  };

  const tracking = neko?.tracking ?? "unavailable";
  const toggleTracking = async () => {
    setPending(true);
    try { await (tracking === "paused" ? api.resume() : api.pause()); refresh(); }
    catch { setNotice("Tracking could not be changed. Check the backend connection and try again."); }
    finally { setPending(false); }
  };

  const allDays = history?.days ?? [];
  const week = allDays.slice(-7);
  const recentSessions = history?.sessions?.filter((session) => !week[0] || session.date >= week[0].date) ?? [];
  const previousWeek = allDays.slice(-14, -7);
  const maxSeconds = Math.max(1, ...week.map((day) => day.total_seconds || 0));
  const categories = week.reduce((totals, day) => {
    for (const [category, seconds] of Object.entries(day.category_totals || {})) totals[category] = (totals[category] || 0) + seconds;
    return totals;
  }, {});
  const categoryRows = Object.entries(categories).filter(([, value]) => value > 0).sort((a, b) => b[1] - a[1]);
  const trackedWeek = week.reduce((sum, day) => sum + day.total_seconds, 0);
  const trackedPreviousWeek = previousWeek.reduce((sum, day) => sum + day.total_seconds, 0);
  const productiveWeek = week.reduce((sum, day) => sum + day.productive_seconds, 0);
  const mostProductiveDay = week.reduce((best, day) => !best || day.productive_seconds > best.productive_seconds ? day : best, null);
  const chartColors = ["#df8d42", "#6d9a84", "#8b79a9", "#d26f71", "#6885ad", "#b5a15b", "#8a796e"];
  const chart = useMemo(() => {
    const total = categoryRows.reduce((sum, [, n]) => sum + n, 0);
    let cursor = 0;
    const stops = categoryRows.map(([, n], i) => {
      const start = cursor; cursor += total ? n / total * 100 : 0;
      return `${chartColors[i % chartColors.length]} ${start}% ${cursor}%`;
    });
    return stops.length ? `conic-gradient(${stops.join(",")})` : "conic-gradient(#e9e2da 0% 100%)";
  }, [categoryRows]);

  return (
    <main className="site-shell">
      <header className="site-header">
        <button className="brand" onClick={() => setPage("home")} aria-label="NekoAI home"><span className="brand-mark">N</span><span>NekoAI</span></button>
        <nav aria-label="Main navigation">
          <button className={page === "home" ? "nav-link active" : "nav-link"} onClick={() => setPage("home")}>Home</button>
          <button className={page === "dashboard" ? "nav-link active" : "nav-link"} onClick={loadDashboard}>Activity dashboard</button>
          <button className={page === "focus" ? "nav-link active" : "nav-link"} onClick={() => setPage("focus")}>Focus Mode</button>
        </nav>
        <div className={`connection ${phase}`}><span />{phase === "ready" ? TRACKING_LABEL[tracking] : phase === "loading" ? "Connecting" : phase === "unauthorized" ? "Sign-in required" : "Backend offline"}</div>
        <button className="text-button signout-button" onClick={onSignOut} aria-label={`Sign out ${user}`}>Sign out</button>
      </header>

      {notice && <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")} aria-label="Dismiss message">×</button></div>}
      {phase === "unavailable" && <div className="notice warning" role="alert">NekoAI backend is disconnected. The dashboard will update when it reconnects.</div>}
      {phase === "unauthorized" && <div className="notice warning" role="alert">This app is not signed in to the local backend. Restart NekoAI with <code>Start_NekoAI.bat</code>.</div>}

      {page === "home" ? <>
        <section className="welcome-grid">
          <div className="welcome-copy">
            <p className="eyebrow">A calmer way to stay on track</p>
            <h1>Meet your<br /><em>desktop companion.</em></h1>
            <p className="intro">Neko quietly follows your activity, celebrates focused sessions, and can nudge you to take a break after a long stretch of work.</p>
            <div className="welcome-actions">
              <button className="primary-button" onClick={allowPet} disabled={pending || phase === "loading"}>{pending ? "Waking Neko…" : petVisible ? "Neko is on your desktop" : petEnabled ? "Show Neko on Desktop" : "Allow Neko on Desktop"}<span aria-hidden="true">→</span></button>
              <button className="text-button" onClick={deferPet}>Not now</button>
            </div>
            <div className="privacy-note"><span className="shield">✓</span><span><strong>Your focus stays yours.</strong> Neko stores app names, categories, session durations, and saved-session window titles locally. It never records keystrokes, screenshots, or passwords.</span></div>
          </div>
          <div className="cat-stage"><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="cat-glow"/><NekoCat state={neko?.state ?? "idle"} message={homeMessage} size={280} animated={animated} /><div className="cat-caption"><span className="live-dot"/> {petVisible ? "Neko is on your desktop" : petEnabled ? "Your desktop companion is enabled" : "Your companion is waiting"}</div></div>
        </section>

        {electron && <section className="pet-manager" aria-label="Desktop companion controls"><strong>Desktop companion</strong><span>{petVisible ? "Visible above your other windows" : "Hidden until you show Neko"}</span><div>{petVisible && <button className="outline-button" onClick={movePet}>Move / interact</button>}{petVisible && <button className="outline-button" onClick={hidePet}>Hide Neko</button>}<button className="text-button" onClick={() => window.nekoDesktop.exitApp()}>Exit NekoAI</button></div></section>}

        <section className="home-lower">
          <div className="section-heading"><div><p className="eyebrow">Your day, at a glance</p><h2>Focus without the fuss.</h2></div><button className="text-button dashboard-link" onClick={loadDashboard}>Open activity dashboard <span>→</span></button></div>
          <div className="feature-row">
            <article className="feature-card"><span className="feature-icon icon-activity">◷</span><div><h3>Activity awareness</h3><p>See your current category, app, and session time from the existing tracker.</p></div></article>
            <article className="feature-card"><span className="feature-icon icon-pause">Ⅱ</span><div><h3>Your pace, your choice</h3><p>Pause or resume tracking whenever you need a private moment.</p></div></article>
            <article className="feature-card"><span className="feature-icon icon-local">⌂</span><div><h3>Local by design</h3><p>Activity records stay on this computer and are used for your summaries.</p></div></article>
          </div>
          <div className="quick-status"><div><span className="status-symbol">◉</span><div><strong>Right now</strong><span>{activity?.category ?? (phase === "ready" ? "No active session" : "Waiting for tracker")}{activity?.app ? ` · ${activity.app}` : ""}</span></div></div><span className="duration">{activity?.session_seconds > 0 ? formatDuration(activity.session_seconds) : "—"}</span><button className="outline-button" disabled={!neko || pending} onClick={toggleTracking}>{tracking === "paused" ? "Resume tracking" : "Pause tracking"}</button></div>
        </section>
      </> : page === "focus" ? <FocusMode activity={activity} /> : <section className="dashboard-page">
        <div className="dashboard-title"><div><p className="eyebrow">Your activity, thoughtfully summarized</p><h1>Activity dashboard</h1><p>Live totals reset when NekoAI restarts. Saved history is based on completed sessions in the local activity log.</p></div><div className="dashboard-actions">{electron && <><button className="outline-button" onClick={allowPet}>{petVisible ? "Neko is visible" : petEnabled ? "Show Neko" : "Allow Neko on Desktop"}</button>{petVisible && <><button className="outline-button" onClick={movePet}>Move / interact</button><button className="outline-button" onClick={hidePet}>Hide Neko</button></>}</>}<button className="outline-button" onClick={toggleTracking} disabled={!neko || pending}>{tracking === "paused" ? "Resume tracking" : "Pause tracking"}</button></div></div>
        {historyError && <div className="history-error-banner" role="alert"><span>{historyError}</span><button className="outline-button" onClick={loadDashboard}>Retry saved history</button></div>}
        <div className="metric-grid"><article className="metric-card"><span>Tracked today</span><strong>{today ? formatDuration(today.total_seconds) : "—"}</strong><small>{today?.scope === "since_launch_today" ? "Since NekoAI started today" : phase === "ready" ? "No tracked time yet" : "Waiting for data"}</small></article><article className="metric-card productive"><span>Productive today</span><strong>{today ? formatDuration(today.productive_seconds) : "—"}</strong><small>Based on the tracker's supported categories</small></article><article className="metric-card"><span>Current activity</span><strong className="metric-current">{activity?.category ?? "—"}</strong><small>{activity?.app ?? "No application reported"}</small></article><article className="metric-card"><span>Tracker status</span><strong className="metric-current">{TRACKING_LABEL[tracking] ?? "Connecting"}</strong><small>{neko?.reason ?? "Waiting for tracker status"}</small></article></div>
        <div className="dash-grid">
          <article className="panel category-panel"><div className="panel-heading"><div><h2>Time by category</h2><p>Saved completed sessions · last 7 days</p></div></div>{historyError ? <p className="empty-state error-text">{historyError}</p> : categoryRows.length ? <div className="donut-layout"><div className="donut" style={{ background: chart }}><div><strong>{formatDuration(categoryRows.reduce((s, [, n]) => s + n, 0))}</strong><span>saved</span></div></div><ul className="legend">{categoryRows.map(([name, seconds], i) => <li key={name}><span style={{ "--legend-color": chartColors[i % chartColors.length] }}/><span>{name}</span><strong>{formatDuration(seconds)}</strong></li>)}</ul></div> : <p className="empty-state">{history ? "No completed sessions are in the saved activity log yet." : "Loading saved sessions…"}</p>}</article>
          <article className="panel week-panel"><div className="panel-heading"><div><h2>Daily activity</h2><p>Recorded session time per day · last 7 days</p></div></div>{historyError ? <p className="empty-state error-text">{historyError}</p> : week.length && week.some((d) => d.total_seconds > 0) ? <div className="week-chart" role="img" aria-label="Saved activity duration for each of the last seven days">{week.map((day) => <div className="day-column" key={day.date} title={`${day.date}: ${formatDuration(day.total_seconds)}`}><strong>{day.total_seconds ? formatDuration(day.total_seconds) : ""}</strong><div className="bar-track"><span style={{ height: `${Math.max(day.total_seconds ? 5 : 0, day.total_seconds / maxSeconds * 100)}%` }} /></div><span>{day.label}</span></div>)}</div> : <p className="empty-state">{history ? "No saved sessions in the last seven days. Neko records completed sessions locally." : "Loading saved sessions…"}</p>}</article>
        </div>
        {focusAnalyticsError && <p className="focus-error" role="alert">{focusAnalyticsError}</p>}{focusAnalytics && <section className="panel focus-analytics"><div className="panel-heading"><div><h2>Focus trends</h2><p>Focus sessions are grouped by local start date. Focus time is separate from app totals and isn't added to them.</p></div></div><div className="focus-weekly"><span>Tracked this week {formatDuration(trackedWeek)}</span><span>Productive {formatDuration(productiveWeek)}</span><span>Tracked change {formatDuration(Math.abs(trackedWeek - trackedPreviousWeek))} {trackedWeek >= trackedPreviousWeek ? "more" : "less"}</span><span>Most productive day {mostProductiveDay?.productive_seconds ? `${mostProductiveDay.label} · ${formatDuration(mostProductiveDay.productive_seconds)}` : "—"}</span><span>Focus today {formatDuration(focusAnalytics.days.at(-1)?.focus_seconds || 0)}</span><span>Today planned / actual {formatDuration(focusAnalytics.days.at(-1)?.planned_seconds || 0)} / {formatDuration(focusAnalytics.days.at(-1)?.focus_seconds || 0)}</span><span>Today sessions {focusAnalytics.days.at(-1)?.completed || 0} completed</span><span>Today distractions {focusAnalytics.days.at(-1)?.distractions || 0}</span><span>Today outside task {formatDuration(focusAnalytics.days.at(-1)?.outside_task_seconds || 0)}</span></div><div className="focus-trend-grid">{focusAnalytics.days.map((day) => <div key={day.date}><span>{day.label}</span><strong>{formatDuration(day.focus_seconds)}</strong><small>{day.completed} done · {day.interrupted} interrupted · {day.distractions} distractions</small><i style={{ width: `${Math.min(100, day.focus_seconds / Math.max(1, ...focusAnalytics.days.map((item) => item.focus_seconds)) * 100)}%` }} /></div>)}</div><div className="focus-weekly"><span>Completed {focusAnalytics.weekly.completed_sessions}</span><span>Interrupted {focusAnalytics.weekly.interrupted_sessions}</span><span>Average {formatDuration(focusAnalytics.weekly.average_completed_seconds)}</span><span>Planned / actual {formatDuration(focusAnalytics.weekly.planned_completed_seconds)} / {formatDuration(focusAnalytics.weekly.actual_completed_seconds)}</span><span>Longest {formatDuration(focusAnalytics.weekly.longest_completed_seconds)}</span><span>Outside task {formatDuration(focusAnalytics.weekly.outside_task_seconds)}</span><span>Focus change {formatDuration(Math.abs(focusAnalytics.weekly.change_seconds))} {focusAnalytics.weekly.change_seconds >= 0 ? "more" : "less"}</span><span>Completion {focusAnalytics.weekly.session_completion_rate == null ? "—" : `${Math.round(focusAnalytics.weekly.session_completion_rate * 100)}%`}</span></div></section>}
        <div className="preference-row"><strong>Companion preferences</strong><label><input type="checkbox" checked={bubbles} onChange={(event) => setBubbles(event.target.checked)} /> Speech bubbles</label><label><input type="checkbox" checked={animated} onChange={(event) => setAnimated(event.target.checked)} /> Animations</label><span>Saved in this browser on your device</span></div>
        <div className="dashboard-bottom"><TodayPanel today={today} /><article className="panel timeline-panel"><div className="panel-heading"><div><h2>Recent activity</h2><p>Saved completed sessions · last 7 days</p></div></div>{historyError ? <p className="empty-state error-text">{historyError}</p> : recentSessions.length ? <ol className="session-list">{recentSessions.slice(0, 8).map((session, index) => <li key={`${session.start_time}-${index}`}><span className="timeline-dot"/><time>{new Date(session.start_time).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}</time><span className="session-name">{session.category}{session.app ? <small>{session.app}</small> : null}</span><strong>{formatDuration(session.duration_seconds)}</strong></li>)}</ol> : <p className="empty-state">{history ? "No completed sessions to show yet." : "Loading saved sessions…"}</p>}</article><article className="panel privacy-panel"><div className="panel-heading"><div><h2>Activity privacy</h2><p>Stored locally on this computer</p></div></div><p>Neko uses foreground application names, activity categories, and session durations. Window titles are stored in the local activity log by the existing tracker, but are not returned by the live activity API.</p><p className="scope-note">Saved charts include completed sessions. The live “today” total is counted since the current NekoAI launch, as reported by the backend.</p></article></div>
      </section>}
      <footer className="site-footer"><span>NEKOAI <i>·</i> your companion, your pace</span><span>Activity data stays on this device</span></footer>
    </main>
  );
}

export default function App(props) {
  const [auth, setAuth] = useState({ status: "checking", user: null, error: "" });
  useEffect(() => {
    let alive = true;
    api.me().then(({ username }) => {
      if (alive) setAuth({ status: "signed-in", user: username, error: "" });
    }).catch((error) => {
      if (!alive) return;
      setAuth({ status: "signed-out", user: null,
        error: error?.kind === "unavailable" ? "NekoAI backend is disconnected. Check that the desktop app is running." : "" });
    });
    return () => { alive = false; };
  }, []);

  const login = async (username, password) => {
    const account = await api.login(username, password);
    setAuth({ status: "signed-in", user: account.username, error: "" });
  };
  const signOut = async () => {
    if (window.nekoDesktop) await window.nekoDesktop.hidePet();
    try { await api.logout(); } catch { /* local UI returns to sign-in; expired cookies are rejected */ }
    setAuth({ status: "signed-out", user: null, error: "" });
  };

  if (auth.status === "checking") return <main className="signin-shell"><p role="status">Connecting to NekoAI…</p></main>;
  if (auth.status !== "signed-in") return <SignInPage onLogin={login} backendError={auth.error} />;
  return <DashboardApp {...props} user={auth.user} onSignOut={signOut} />;
}
