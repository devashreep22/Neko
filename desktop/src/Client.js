/** The only place that talks to the NekoAI backend. Same-origin, cookie auth. */

export class ApiError extends Error {
  /** kind: "unauthorized" (no/expired login) | "unavailable" (backend unreachable) | "http" */
  constructor(kind, status, message) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

async function request(path, { method = "GET", signal, body } = {}) {
  let res;
  const timeoutSignal = AbortSignal.timeout(5000);
  const requestSignal = signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
      signal: requestSignal,
    });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError("unavailable", 0, "Cannot reach the NekoAI backend");
  }
  if (res.status === 401) throw new ApiError("unauthorized", 401, "Not logged in");
  if (!res.ok) throw new ApiError("http", res.status, `Request failed (${res.status})`);
  try {
    return await res.json();
  } catch {
    throw new ApiError("http", res.status, "Unexpected response from the backend");
  }
}

export const api = {
  me: () => request("/api/auth/me"),
  login: (username, password) => request("/api/auth/login", { method: "POST", body: { username, password } }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  state: (opts) => request("/api/neko/state", opts),
  current: (opts) => request("/api/activity/current", opts),
  today: (opts) => request("/api/activity/today", opts),
  history: (days = 7) => request(`/api/analytics/history?days=${encodeURIComponent(days)}`),
  focusAnalytics: (days = 7) => request(`/api/analytics/focus?days=${encodeURIComponent(days)}`),
  focus: {
    active: () => request("/api/focus/session"),
    sessions: () => request("/api/focus/sessions"),
    detail: (id) => request(`/api/focus/sessions/${encodeURIComponent(id)}`),
    start: (body) => request("/api/focus/sessions", { method: "POST", body }),
    pause: () => request("/api/focus/session/pause", { method: "POST" }),
    resume: () => request("/api/focus/session/resume", { method: "POST" }),
    end: () => request("/api/focus/session/end", { method: "POST" }),
  },
  pause: () => request("/api/tracking/pause", { method: "POST" }),
  resume: () => request("/api/tracking/resume", { method: "POST" }),
};
