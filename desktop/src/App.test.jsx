import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  status: { phase: "ready", neko: { state: "coding", tracking: "running", reason: "Focused work" },
    activity: { category: "Coding", app: "Code.exe", session_seconds: 120 },
    today: { scope: "since_launch_today", total_seconds: 120, productive_seconds: 120 }, refresh: vi.fn() },
  enablePet: vi.fn(), hidePet: vi.fn(), setInteractive: vi.fn(), exitApp: vi.fn(), history: vi.fn(),
  me: vi.fn(), login: vi.fn(), logout: vi.fn(),
}));

vi.mock("./UseNekoStatus.js", () => ({ useNekoStatus: () => mocks.status }));
vi.mock("./Client.js", () => ({ api: {
  me: (...args) => mocks.me(...args), login: (...args) => mocks.login(...args), logout: (...args) => mocks.logout(...args),
  history: (...args) => mocks.history(...args), focusAnalytics: vi.fn().mockResolvedValue({ days: [], weekly: {} }),
  pause: vi.fn(), resume: vi.fn(),
}, ApiError: class ApiError extends Error { constructor(kind, status, message) { super(message); this.kind = kind; this.status = status; } } }));

import App from "./App.jsx";

describe("NekoAI onboarding and dashboard", () => {
  afterEach(cleanup);

  beforeEach(() => {
    window.localStorage.clear();
    delete window.nekoDesktop;
    mocks.enablePet.mockReset();
    mocks.me.mockReset().mockResolvedValue({ username: "Devashree" });
    mocks.login.mockReset().mockResolvedValue({ username: "Devashree" });
    mocks.logout.mockReset().mockResolvedValue({ status: "signed_out" });
    mocks.history.mockReset().mockResolvedValue({ scope: "saved_completed_sessions", days: [], category_totals: {} });
  });

  it("explains that browser mode cannot launch the desktop pet", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Allow Neko on Desktop/ }));
    expect(screen.getByText(/installed NekoAI desktop app/i)).toBeTruthy();
    expect(screen.getByText(/stores app names, categories, session durations, and saved-session window titles locally/i)).toBeTruthy();
  });

  it("reveals the pet through the Electron bridge and reports success", async () => {
    mocks.enablePet.mockResolvedValue(true);
    window.nekoDesktop = { enablePet: mocks.enablePet };
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Allow Neko on Desktop/ }));
    await waitFor(() => expect(mocks.enablePet).toHaveBeenCalledOnce());
    expect(await screen.findByText(/Neko is now on your desktop/i)).toBeTruthy();
  });

  it("loads real dashboard history and distinguishes empty saved history", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Activity dashboard" }));
    expect(await screen.findByRole("heading", { name: "Activity dashboard" })).toBeTruthy();
    expect(await screen.findByText(/No completed sessions are in the saved activity log yet/i)).toBeTruthy();
    expect(mocks.history).toHaveBeenCalledOnce();
  });

  it("distinguishes a missing history file from an empty successful log", async () => {
    mocks.history.mockResolvedValueOnce({ scope: "saved_completed_sessions", data_status: "missing", days: [], category_totals: {} });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Activity dashboard" }));
    expect((await screen.findAllByText(/local activity log has not been created yet/i)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Retry saved history" })).toBeTruthy();
  });

  it("requires backend login and returns to sign-in on sign-out", async () => {
    mocks.me.mockRejectedValueOnce(Object.assign(new Error("Not signed in"), { kind: "unauthorized", status: 401 }));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Welcome back." })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "Devashree" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: /Meet your/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sign out Devashree" }));
    expect(await screen.findByRole("heading", { name: "Welcome back." })).toBeTruthy();
  });

  it("shows a backend validated invalid-credentials message", async () => {
    mocks.me.mockRejectedValueOnce(Object.assign(new Error("Not signed in"), { kind: "unauthorized", status: 401 }));
    mocks.login.mockRejectedValueOnce(Object.assign(new Error("Invalid"), { kind: "http", status: 401 }));
    render(<App />);
    await screen.findByRole("heading", { name: "Welcome back." });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "Devashree" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/not recognized/i);
  });
});
