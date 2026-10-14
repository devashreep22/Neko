import { useId } from "react";
import "./NekoCat.css";

/** Neko states the backend may send. The frontend never invents others. */
export const STATES = [
  "idle", "coding", "learning", "watching", "happy",
  "angry", "sleepy", "celebrating", "drink",
];

const LABELS = {
  idle: "relaxing", coding: "focused on coding", learning: "learning",
  watching: "watching something", happy: "happy", angry: "annoyed",
  sleepy: "sleepy", celebrating: "celebrating", drink: "reminding you to drink water",
};

/*
 * Expression table (separate from animation, which lives in the CSS keyed by `anim`).
 *  cover  eyelid coverage 0..1      tilt   eyelid angle in degrees (+ = angry)
 *  brow   brow rotation in degrees  browY  brow vertical offset
 *  px,py  gaze offset               scale  eye size multiplier
 *  eyes   "open" | "arcs" (happy ^ ^)   mouth smile|flat|small|frown|open|yawn
 *  fx     small prop shown near the cat   anim  body animation name
 */
const EXPRESSIONS = {
  idle:        { cover: 0,    tilt: 0,  brow: 0,   browY: 0,  px: 0, py: 0, scale: 1,    eyes: "open", mouth: "smile", fx: "none",   anim: "breathe" },
  coding:      { cover: 0.35, tilt: 0,  brow: 8,   browY: 3,  px: 0, py: 2, scale: 1,    eyes: "open", mouth: "flat",  fx: "code",   anim: "typing" },
  learning:    { cover: 0,    tilt: 0,  brow: -6,  browY: -4, px: 0, py: 0, scale: 1.12, eyes: "open", mouth: "small", fx: "book",   anim: "think" },
  watching:    { cover: 0.25, tilt: 0,  brow: 0,   browY: 0,  px: 5, py: 0, scale: 1,    eyes: "open", mouth: "smile", fx: "screen", anim: "sway" },
  happy:       { cover: 0,    tilt: 0,  brow: -4,  browY: -3, px: 0, py: 0, scale: 1,    eyes: "arcs", mouth: "open",  fx: "hearts", anim: "bounce" },
  angry:       { cover: 0.3,  tilt: 20, brow: 16,  browY: 4,  px: 0, py: 0, scale: 1,    eyes: "open", mouth: "frown", fx: "angry",  anim: "huff" },
  sleepy:      { cover: 0.78, tilt: 0,  brow: -2,  browY: 2,  px: 0, py: 3, scale: 1,    eyes: "open", mouth: "yawn",  fx: "zzz",    anim: "sleep" },
  celebrating: { cover: 0,    tilt: 0,  brow: -6,  browY: -4, px: 0, py: 0, scale: 1,    eyes: "arcs", mouth: "open",  fx: "confetti", anim: "jump" },
  drink:       { cover: 0.1,  tilt: 0,  brow: 0,   browY: 0,  px: -4, py: 0, scale: 1,   eyes: "open", mouth: "smile", fx: "water",  anim: "bob" },
};

/** Map anything the backend sends to a known state; unknown values fall back to idle. */
export function resolveState(value) {
  const key = typeof value === "string" ? value.trim().toLowerCase() : "";
  return Object.prototype.hasOwnProperty.call(EXPRESSIONS, key) ? key : "idle";
}

function Eye({ x, side, clipId }) {
  return (
    <g transform={`translate(${x} 100)`}>
      <g className="neko-gaze">
        <g className="neko-escale">
          <g className="neko-blink">
            <ellipse rx="13" ry="16" fill="var(--ink)" />
            <circle cx="-4" cy="-6" r="4.2" fill="#fff" />
            <circle cx="4" cy="6" r="1.8" fill="#fff" opacity=".7" />
            <g clipPath={`url(#${clipId})`}>
              <rect className="neko-lid" style={{ "--side": side }} x="-24" y="-60" width="48" height="60" fill="var(--fur)" />
            </g>
          </g>
        </g>
      </g>
      <path className="neko-arc" d="M-10 5 Q0 -9 10 5" fill="none" stroke="var(--ink)" strokeWidth="4" strokeLinecap="round" />
    </g>
  );
}

function Brow({ x, side }) {
  return (
    <g transform={`translate(${x} 77)`}>
      <line className="neko-brow" style={{ "--side": side }} x1="-9" y1="0" x2="9" y2="0" stroke="var(--brow-color)" strokeWidth="3.5" strokeLinecap="round" />
    </g>
  );
}

const CONFETTI = [
  [-10, 20, "#f43f5e"], [20, 6, "#38bdf8"], [60, 14, "#facc15"], [100, 4, "#a78bfa"],
  [140, 12, "#34d399"], [180, 8, "#fb923c"], [205, 28, "#f43f5e"], [-14, 60, "#facc15"],
  [40, 36, "#34d399"], [165, 40, "#38bdf8"],
];

/**
 * One reusable Neko. Appearance is driven only by `state` (from the backend).
 * Props: state, message (optional speech bubble), size (px width),
 *        animated (false disables all motion), className.
 */
export default function NekoCat({ state = "idle", message, size = 240, animated = true, className = "" }) {
  const s = resolveState(state);
  const ex = EXPRESSIONS[s];
  const uid = "neko" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const clipId = `${uid}-clip`;
  const vars = {
    "--cover": ex.cover, "--tilt": `${ex.tilt}deg`, "--brow": `${ex.brow}deg`,
    "--browY": `${ex.browY}px`, "--px": `${ex.px}px`, "--py": `${ex.py}px`, "--scale": ex.scale,
  };

  return (
    <div
      className={`neko ${className}`.trim()}
      style={{ width: size }}
      data-state={s} data-anim={ex.anim} data-eyes={ex.eyes}
      data-mouth={ex.mouth} data-fx={ex.fx} data-animated={animated ? "true" : "false"}
    >
      {message ? <div className="neko-bubble" role="status">{message}</div> : null}
      <svg viewBox="-20 0 240 220" role="img" aria-label={`Neko is ${LABELS[s]}`} style={vars}>
        <defs>
          <clipPath id={clipId}><ellipse rx="14.5" ry="17.5" /></clipPath>
        </defs>
        <g className="neko-all">
          <path className="neko-tail" d="M138 182 C176 180 192 146 172 120" fill="none" stroke="var(--fur)" strokeWidth="15" strokeLinecap="round" />
          <ellipse cx="100" cy="172" rx="44" ry="36" fill="var(--fur)" />
          <ellipse cx="100" cy="180" rx="26" ry="24" fill="var(--belly)" />
          <ellipse cx="80" cy="205" rx="14" ry="8" fill="var(--fur)" />
          <ellipse cx="120" cy="205" rx="14" ry="8" fill="var(--fur)" />

          <g className="neko-head">
            <path d="M52 72 L47 22 L88 52 Z" fill="var(--fur)" stroke="var(--fur)" strokeWidth="8" strokeLinejoin="round" />
            <path d="M148 72 L153 22 L112 52 Z" fill="var(--fur)" stroke="var(--fur)" strokeWidth="8" strokeLinejoin="round" />
            <path d="M58 62 L55 38 L76 52 Z" fill="var(--pink)" />
            <path d="M142 62 L145 38 L124 52 Z" fill="var(--pink)" />
            <ellipse cx="100" cy="98" rx="58" ry="50" fill="var(--fur)" />
            <path d="M100 52 L100 64 M88 55 L90 65 M112 55 L110 65" stroke="var(--fur-dark)" strokeWidth="4" strokeLinecap="round" />
            <circle cx="55" cy="118" r="9" fill="var(--pink)" opacity=".45" />
            <circle cx="145" cy="118" r="9" fill="var(--pink)" opacity=".45" />
            <Eye x={72} side={1} clipId={clipId} />
            <Eye x={128} side={-1} clipId={clipId} />
            <Brow x={72} side={1} />
            <Brow x={128} side={-1} />
            <path d="M94 110 L106 110 L100 117 Z" fill="var(--pink)" stroke="var(--pink)" strokeWidth="2" strokeLinejoin="round" />
            <g transform="translate(100 119)" fill="none" stroke="var(--ink)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
              <path className="neko-mouth m-smile" d="M-11 0 Q-5 8 0 1 Q5 8 11 0" />
              <path className="neko-mouth m-flat" d="M-7 4 L7 4" />
              <path className="neko-mouth m-small" d="M-4 3 Q0 7 4 3" />
              <path className="neko-mouth m-frown" d="M-10 9 Q0 -2 10 9" />
              <path className="neko-mouth m-open" d="M-9 1 Q0 18 9 1 Z" fill="var(--ink)" />
              <ellipse className="neko-mouth m-yawn" cx="0" cy="7" rx="6" ry="8" fill="var(--ink)" />
            </g>
            <g stroke="var(--ink)" strokeWidth="1.8" strokeLinecap="round" opacity=".55">
              <path d="M40 112 L14 106 M40 120 L14 124" />
              <path d="M160 112 L186 106 M160 120 L186 124" />
            </g>
          </g>

          <g className="neko-fx fx-code" transform="translate(166 18)">
            <rect width="50" height="30" rx="8" fill="#1f2937" />
            <path d="M8 29 L2 40 L18 29 Z" fill="#1f2937" />
            <text x="25" y="21" textAnchor="middle" fontFamily="monospace" fontSize="15" fill="#6ee7b7">{"</>"}<tspan className="neko-cursor">_</tspan></text>
          </g>
          <g className="neko-fx fx-book" transform="translate(100 194)">
            <path d="M-32 -2 L0 5 L32 -2 L32 18 L0 25 L-32 18 Z" fill="#fff" stroke="#6366f1" strokeWidth="2.5" strokeLinejoin="round" />
            <path d="M0 5 L0 25 M-24 6 L-8 9.5 M-24 12 L-8 15.5 M8 9.5 L24 6 M8 15.5 L24 12" stroke="#a5b4fc" strokeWidth="2" strokeLinecap="round" />
          </g>
          <g className="neko-fx fx-screen" transform="translate(166 24)">
            <rect className="neko-glow" width="50" height="34" rx="5" fill="#60a5fa" opacity=".35" transform="translate(-3 -3) scale(1.12)" />
            <rect width="50" height="34" rx="5" fill="#1e3a8a" />
            <path d="M20 9 L35 17 L20 25 Z" fill="#bfdbfe" />
          </g>
          <g className="neko-fx fx-hearts">
            <g transform="translate(176 52)"><path className="neko-rise" d="M0 4 C-7 -5 -14 5 0 14 C14 5 7 -5 0 4Z" fill="#fb7185" /></g>
            <g transform="translate(200 30) scale(.7)"><path className="neko-rise r2" d="M0 4 C-7 -5 -14 5 0 14 C14 5 7 -5 0 4Z" fill="#f472b6" /></g>
          </g>
          <g className="neko-fx fx-angry">
            <path d="M124 60 L132 66 M132 60 L124 66 M120 66 L128 72 M128 66 L120 72" stroke="#ef4444" strokeWidth="3" strokeLinecap="round" transform="translate(14 -2)" />
            <circle className="neko-puff" cx="178" cy="60" r="7" fill="#cbd5e1" />
            <circle className="neko-puff p2" cx="194" cy="44" r="5" fill="#cbd5e1" />
          </g>
          <g className="neko-fx fx-zzz" fontFamily="system-ui, sans-serif" fontWeight="700" fill="#818cf8">
            <text className="neko-rise" x="168" y="60" fontSize="24">Z</text>
            <text className="neko-rise r2" x="188" y="38" fontSize="17">z</text>
            <text className="neko-rise r3" x="202" y="22" fontSize="12">z</text>
          </g>
          <g className="fx-confetti neko-fx">
            {CONFETTI.map(([x, y, c], i) => (
              <rect key={i} className="neko-piece" style={{ "--i": i }} x={x} y={y} width="7" height="11" rx="1.5" fill={c} />
            ))}
          </g>
          <g className="neko-fx fx-water" transform="translate(-16 152)">
            <path d="M0 0 L36 0 L32 42 L4 42 Z" fill="#e0f2fe" stroke="#38bdf8" strokeWidth="2.5" strokeLinejoin="round" />
            <path d="M2 16 L34 16 L32 42 L4 42 Z" fill="#7dd3fc" />
            <path className="neko-drop" d="M18 -16 C12 -6 12 -2 18 -2 C24 -2 24 -6 18 -16Z" fill="#38bdf8" />
          </g>
        </g>
      </svg>
    </div>
  );
}