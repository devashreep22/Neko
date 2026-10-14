import { formatDuration } from "./Format.js";

export default function TodayPanel({ today }) {
  const totals = Object.entries(today?.totals ?? {}).filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1]);
  const sum = totals.reduce((acc, [, s]) => acc + s, 0);
  return (
    <section className="app-card" aria-labelledby="today-title">
      <h2 id="today-title">Today</h2>
      {totals.length === 0 ? (
        <p className="app-muted">No activity tracked yet today.</p>
      ) : (
        <>
          <p className="app-muted">
            {formatDuration(sum)} tracked, {formatDuration(today?.productive_seconds)} productive
          </p>
          <ul className="app-bars">
            {totals.map(([category, seconds]) => (
              <li key={category}>
                <span className="app-bar-label">{category}</span>
                <span className="app-bar"><span style={{ width: `${(seconds / sum) * 100}%` }} /></span>
                <span className="app-bar-value">{formatDuration(seconds)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="app-fine">Live totals are counted since NekoAI started today. Completed sessions are saved locally.</p>
    </section>
  );
}
