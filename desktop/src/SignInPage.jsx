import { useState } from "react";

export default function SignInPage({ onLogin, backendError }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onLogin(username, password);
      setPassword("");
    } catch (cause) {
      setError(cause?.kind === "unavailable"
        ? "NekoAI could not reach its local backend. Start the desktop app with Start_NekoAI.bat and try again."
        : cause?.status === 401
          ? "That username or password was not recognized. Check both and try again."
          : "Sign-in failed. Check the backend connection and try again.");
    } finally { setBusy(false); }
  };

  return <main className="signin-shell">
    <section className="signin-card" aria-labelledby="signin-title">
      <div className="signin-brand"><span className="brand-mark">N</span><span>NekoAI</span></div>
      <p className="eyebrow">Your companion, your pace</p>
      <h1 id="signin-title">Welcome back.</h1>
      <p className="signin-intro">Sign in to open your activity dashboard and desktop companion.</p>
      {backendError && <p className="signin-error" role="status">{backendError}</p>}
      {error && <p className="signin-error" role="alert">{error}</p>}
      <form onSubmit={submit}>
        <label htmlFor="neko-username">Username</label>
        <input id="neko-username" name="username" autoComplete="username" value={username}
          onChange={(event) => setUsername(event.target.value)} required maxLength={100} />
        <label htmlFor="neko-password">Password</label>
        <input id="neko-password" name="password" type="password" autoComplete="current-password"
          value={password} onChange={(event) => setPassword(event.target.value)} required maxLength={256} />
        <button className="primary-button signin-submit" disabled={busy} type="submit">
          {busy ? "Signing in…" : "Sign in"}<span aria-hidden="true">→</span>
        </button>
      </form>
      <p className="signin-local">Your account and activity stay on this computer.</p>
    </section>
  </main>;
}
