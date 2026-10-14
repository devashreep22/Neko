import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({ active: vi.fn(), sessions: vi.fn(), start: vi.fn(), pause: vi.fn(), resume: vi.fn(), end: vi.fn(), detail: vi.fn() }));
vi.mock("./Client.js", () => ({
  api: { focus: {
    active: (...args) => mocks.active(...args), sessions: (...args) => mocks.sessions(...args),
    start: (...args) => mocks.start(...args), pause: (...args) => mocks.pause(...args),
    resume: (...args) => mocks.resume(...args), end: (...args) => mocks.end(...args), detail: (...args) => mocks.detail(...args),
  } },
  ApiError: class ApiError extends Error { constructor(kind, status, message) { super(message); this.kind = kind; this.status = status; } },
}));
import FocusMode from "./FocusMode.jsx";

const openSession = { id: "one", task_title: "Solve problems", status: "active", remaining_seconds: 1500,
  active_seconds: 0, paused_seconds: 0, planned_seconds: 1500, progress: 0, distraction_count: 0,
  outside_task_seconds: 0, enforcement_mode: "monitor", enforcement_status: "monitoring", distractions: [] };

describe("Focus Mode", () => {
  afterEach(() => { cleanup(); delete window.nekoDesktop; });
  beforeEach(() => {
    mocks.active.mockReset().mockResolvedValue({ session: null });
    mocks.sessions.mockReset().mockResolvedValue({ sessions: [] });
    mocks.start.mockReset().mockResolvedValue(openSession);
    mocks.pause.mockReset().mockResolvedValue({ ...openSession, status: "paused" });
    mocks.resume.mockReset().mockResolvedValue(openSession);
    mocks.end.mockReset().mockResolvedValue({ ...openSession, status: "cancelled" });
  });

  it("creates a task with the selected duration and allowlist", async () => {
    render(<FocusMode />);
    fireEvent.change(screen.getByLabelText("Task title"), { target: { value: "Solve problems" } });
    fireEvent.click(screen.getByRole("button", { name: "30 min" }));
    fireEvent.change(screen.getByLabelText(/Approved websites/), { target: { value: "leetcode.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Start Focus Session" }));
    await waitFor(() => expect(mocks.start).toHaveBeenCalledWith(expect.objectContaining({
      task_title: "Solve problems", duration_minutes: 30, approved_domains: ["leetcode.com"], enforcement_mode: "monitor",
    })));
  });

  it("displays persisted active state and offers pause", async () => {
    mocks.active.mockResolvedValue({ session: openSession });
    render(<FocusMode activity={{ app: "Code.exe" }} />);
    expect(await screen.findByRole("heading", { name: "Solve problems" })).toBeTruthy();
    expect(screen.getByText("Code.exe")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Pause focus" }));
    await waitFor(() => expect(mocks.pause).toHaveBeenCalledOnce());
  });

  it("shows disconnected state without claiming enforcement", async () => {
    mocks.active.mockRejectedValue(Object.assign(new Error("Cannot reach backend"), { kind: "unavailable" }));
    render(<FocusMode />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/disconnected/i);
  });

  it("routes an approved address through the Electron bridge", async () => {
    mocks.active.mockResolvedValue({ session: { ...openSession, enforcement_mode: "controlled_browser", approved_domains: ["leetcode.com"] } });
    const openFocusBrowser = vi.fn().mockResolvedValue(true);
    window.nekoDesktop = { openFocusBrowser };
    render(<FocusMode />);
    fireEvent.change(await screen.findByLabelText("Open an approved website"), { target: { value: "https://leetcode.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Open in Neko Focus Browser" }));
    await waitFor(() => expect(openFocusBrowser).toHaveBeenCalledWith("https://leetcode.com"));
    delete window.nekoDesktop;
  });

  it("requires confirmation and ends the persisted session", async () => {
    mocks.active.mockResolvedValue({ session: openSession });
    window.confirm = vi.fn().mockReturnValue(true);
    render(<FocusMode />);
    fireEvent.click(await screen.findByRole("button", { name: "End session" }));
    await waitFor(() => expect(mocks.end).toHaveBeenCalledOnce());
  });
});
