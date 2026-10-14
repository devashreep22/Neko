import pytest
from app.services.neko_state import (
    NEKO_STATES, StateConfig, StateDecision, StateStabilizer, decide_state, get_neko_state,
)


def test_entertainment_under_limit_is_watching():
    # Regression: the old code returned "idle" for entertainment under 60 minutes.
    assert get_neko_state("Entertainment", 30 * 60) == "watching"
    assert decide_state("Entertainment", entertainment_today_seconds=30 * 60).state == "watching"


def test_entertainment_over_limit_is_angry():
    d = decide_state("Entertainment", entertainment_today_seconds=90 * 60)
    assert d.state == "angry" and "90" in d.reason


def test_limit_is_configurable():
    cfg = StateConfig(entertainment_limit_minutes=30)
    assert decide_state("Entertainment", entertainment_today_seconds=31 * 60, config=cfg).state == "angry"


def test_angry_only_applies_while_on_entertainment():
    assert decide_state("Coding", entertainment_today_seconds=10 * 3600).state == "coding"


def test_legacy_dsa_label_is_coding():
    # Regression: "DSA" used to fall through to "idle".
    assert get_neko_state("DSA", 100) == "coding"
    assert get_neko_state("Other", 100) == "idle"


@pytest.mark.parametrize("cat, state", [
    ("Coding", "coding"), ("Learning", "learning"), ("Work", "learning"),
    ("Music", "idle"), ("Browsing", "idle"), ("Communication", "idle"),
    ("System", "idle"), ("Unknown", "idle"), (None, "idle"), ("Banana", "idle"),
])
def test_category_mapping(cat, state):
    assert decide_state(cat).state == state


def test_long_work_makes_sleepy():
    assert decide_state("Coding", continuous_work_seconds=3 * 3600).state == "sleepy"
    assert decide_state("Entertainment", continuous_work_seconds=3 * 3600).state == "watching"


def test_priorities():
    assert decide_state("Coding", tracking_paused=True, goal_completed=True).state == "idle"
    assert decide_state("Coding", user_idle=True).state == "idle"
    assert decide_state("Coding", goal_completed=True).state == "celebrating"
    assert decide_state("Learning", hydration_due=True).state == "drink"


def test_every_decision_is_a_known_state():
    for cat in (None, "Coding", "Music", "Social Media", "Break", "???"):
        assert decide_state(cat).state in NEKO_STATES


class FakeClock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def mk(state): return StateDecision(state, "test")


def test_stabilizer_holds_brief_changes():
    clock = FakeClock(); s = StateStabilizer(hold_seconds=5, clock=clock)
    assert s.update(mk("coding")).state == "coding"
    clock.t = 1; assert s.update(mk("idle")).state == "coding"
    clock.t = 3; assert s.update(mk("idle")).state == "coding"
    clock.t = 6; assert s.update(mk("idle")).state == "idle"


def test_stabilizer_resets_when_activity_returns():
    clock = FakeClock(); s = StateStabilizer(hold_seconds=5, clock=clock)
    s.update(mk("coding"))
    clock.t = 1; s.update(mk("idle"))
    clock.t = 2; s.update(mk("coding"))        # came back: pending change cancelled
    clock.t = 3; s.update(mk("idle"))
    clock.t = 7; assert s.update(mk("idle")).state == "coding"   # only 4s since restart
    clock.t = 8; assert s.update(mk("idle")).state == "idle"


def test_celebration_is_immediate():
    clock = FakeClock(); s = StateStabilizer(hold_seconds=5, clock=clock)
    s.update(mk("coding"))
    assert s.update(mk("celebrating")).state == "celebrating"


def test_forced_update_skips_the_hold():
    clock = FakeClock(); s = StateStabilizer(hold_seconds=5, clock=clock)
    s.update(mk("coding"))
    assert s.update(mk("idle")).state == "coding"
    assert s.update(mk("idle"), force=True).state == "idle"