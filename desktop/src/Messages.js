/** Friendly, deterministic speech-bubble texts. Presentation only: the backend
 *  decides the state, this just words it. No bubble for idle. */
export const MESSAGES = {
  coding: "Deep focus. Nice!",
  learning: "Soaking it all in.",
  watching: "Enjoying a show?",
  happy: "Nice work! Keep going.",
  angry: "That's a lot of screen time...",
  sleepy: "A short break might help.",
  celebrating: "Daily goal reached!",
  drink: "Time for some water.",
};
export const BUBBLE_MS = 8000;          // how long a bubble stays
export const COOLDOWN_MS = 5 * 60_000;  // same bubble is not repeated sooner than this
export const messageFor = (state) => MESSAGES[state] ?? null;