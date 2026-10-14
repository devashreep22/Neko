import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import NekoCat, { STATES, resolveState } from "./NekoCat.jsx";

describe("resolveState", () => {
  it("accepts every known state", () => STATES.forEach((s) => expect(resolveState(s)).toBe(s)));
  it("is case/space tolerant", () => expect(resolveState("  Coding ")).toBe("coding"));
  it("falls back to idle for unknown or invalid input", () => {
    for (const v of ["dancing", "", null, undefined, 42, {}, "__proto__", "constructor"])
      expect(resolveState(v)).toBe("idle");
  });
});

describe("<NekoCat />", () => {
  it.each(STATES)("renders state %s", (s) => {
    const html = renderToStaticMarkup(<NekoCat state={s} />);
    expect(html).toContain(`data-state="${s}"`);
    expect(html).toContain("<svg");
  });
  it("renders idle for an unknown state without throwing", () => {
    expect(renderToStaticMarkup(<NekoCat state="nonsense" />)).toContain('data-state="idle"');
  });
  it("shows the message only when provided", () => {
    expect(renderToStaticMarkup(<NekoCat message="Nice work!" />)).toContain("Nice work!");
    expect(renderToStaticMarkup(<NekoCat />)).not.toContain("neko-bubble");
  });
  it("can disable animation", () => {
    expect(renderToStaticMarkup(<NekoCat animated={false} />)).toContain('data-animated="false"');
  });
  it("gives each instance unique clip ids", () => {
    const html = renderToStaticMarkup(<><NekoCat /><NekoCat /></>);
    const ids = [...html.matchAll(/<clipPath id="([^"]+)"/g)].map((m) => m[1]);
    expect(new Set(ids).size).toBe(2);
  });
  it("has an accessible label", () => {
    expect(renderToStaticMarkup(<NekoCat state="sleepy" />)).toContain('aria-label="Neko is sleepy"');
  });
});