"""Neko state engine: decides which state the cat should show, and why.

Pure logic with no OS or database access, so it is easy to test. The caller
supplies the facts (category, cumulative entertainment time, ...).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.utils.categories import (
    BREAK, BROWSING, CODING, COMMUNICATION, DEFAULT_PRODUCTIVE, ENTERTAINMENT,
    LEARNING, MUSIC, SOCIAL_MEDIA, SYSTEM, UNKNOWN, WORK, normalize_category,
)

NEKO_STATES = (
    "idle", "coding", "learning", "watching", "happy",
    "angry", "sleepy", "celebrating", "drink",
)

# Category -> state when no special rule applies.
# Work uses "learning" (attentive look) because there is no dedicated working
# state yet; Music uses "idle" until a music expression exists.
CATEGORY_STATE = {
    CODING: "coding", LEARNING: "learning", WORK: "learning",
    ENTERTAINMENT: "watching", MUSIC: "idle", BROWSING: "idle",
    SOCIAL_MEDIA: "idle", COMMUNICATION: "idle", BREAK: "idle",
    SYSTEM: "idle", UNKNOWN: "idle",
}


@dataclass(frozen=True)
class StateConfig:
    entertainment_limit_minutes: float = 90.0  # cumulative today, not per session
    long_work_minutes: float = 120.0           # continuous work before "sleepy"


DEFAULT_CONFIG = StateConfig()


@dataclass(frozen=True)
class StateDecision:
    state: str
    reason: str


def decide_state(
    category: Optional[str],
    *,
    entertainment_today_seconds: float = 0.0,
    continuous_work_seconds: float = 0.0,
    tracking_paused: bool = False,
    user_idle: bool = False,
    goal_completed: bool = False,
    hydration_due: bool = False,
    config: StateConfig = DEFAULT_CONFIG,
) -> StateDecision:
    cat = normalize_category(category)

    if tracking_paused:
        return StateDecision("idle", "Tracking is paused")
    if user_idle:
        return StateDecision("idle", "No recent keyboard or mouse activity")
    if goal_completed:
        return StateDecision("celebrating", "A goal was completed")
    if cat == ENTERTAINMENT and entertainment_today_seconds >= config.entertainment_limit_minutes * 60:
        return StateDecision(
            "angry",
            f"Entertainment time today passed {config.entertainment_limit_minutes:g} minutes",
        )
    if cat in DEFAULT_PRODUCTIVE and continuous_work_seconds >= config.long_work_minutes * 60:
        return StateDecision("sleepy", f"{config.long_work_minutes:g}+ minutes of continuous work; time for a break")
    if hydration_due:
        return StateDecision("drink", "Hydration reminder is due")
    return StateDecision(CATEGORY_STATE[cat], f"Current activity: {cat}")


class StateStabilizer:
    """Stops the cat flickering: a new state must persist for hold_seconds
    before it is shown. States in `immediate` (celebrations) skip the wait."""

    def __init__(self, hold_seconds: float = 5.0,
                 immediate=frozenset({"celebrating"}),
                 clock: Callable[[], float] = time.monotonic):
        self._hold = hold_seconds
        self._immediate = immediate
        self._clock = clock
        self._current: Optional[StateDecision] = None
        self._candidate: Optional[StateDecision] = None
        self._since = 0.0

    def update(self, decision: StateDecision, force: bool = False) -> StateDecision:
        now = self._clock()
        if force or self._current is None or decision.state in self._immediate:
            self._current, self._candidate = decision, None
            return decision
        if decision.state == self._current.state:
            self._current, self._candidate = decision, None  # refresh the reason
            return decision
        if self._candidate is None or self._candidate.state != decision.state:
            self._candidate, self._since = decision, now
        if now - self._since >= self._hold:
            self._current, self._candidate = decision, None
        return self._current


def get_neko_state(category, duration_seconds):
    """Backward-compatible wrapper. For Entertainment, duration_seconds is
    treated as the cumulative entertainment time."""
    cat = normalize_category(category)
    seconds = duration_seconds if cat == ENTERTAINMENT else 0.0
    return decide_state(cat, entertainment_today_seconds=seconds).state