import { describe, expect, it } from "vitest";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { focusUrlAllowed } = require("../electron/focus-policy.cjs");
const policy = { active: true, mode: "controlled_browser", session_id: "session", domains: ["leetcode.com", "*.example.org"] };

describe("Neko Focus Browser navigation policy", () => {
  it("allows the exact approved hostname and its paths", () => {
    expect(focusUrlAllowed("https://leetcode.com/problems/two-sum", policy)).toBe(true);
  });
  it("blocks deceptive suffixes, unapproved hosts, and pop-up navigation targets", () => {
    expect(focusUrlAllowed("https://leetcode.com.attacker.example", policy)).toBe(false);
    expect(focusUrlAllowed("https://attacker.example", policy)).toBe(false);
  });
  it("includes subdomains only for explicit wildcard entries", () => {
    expect(focusUrlAllowed("https://docs.example.org", policy)).toBe(true);
    expect(focusUrlAllowed("https://example.org", policy)).toBe(false);
  });
  it("rejects unsupported schemes, credentials, and nonstandard ports", () => {
    expect(focusUrlAllowed("file:///etc/passwd", policy)).toBe(false);
    expect(focusUrlAllowed("https://user@leetcode.com", policy)).toBe(false);
    expect(focusUrlAllowed("https://leetcode.com:8443", policy)).toBe(false);
  });
  it("fails closed while policy is unknown and suspends restrictions while paused", () => {
    expect(focusUrlAllowed("https://leetcode.com", null)).toBe(false);
    expect(focusUrlAllowed("https://other.example", { ...policy, active: false })).toBe(true);
  });
});
