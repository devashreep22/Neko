import threading
import time
from datetime import datetime, timedelta

from app.services.tracker import ActivityTracker
from app.system.foreground import WindowInfo


class FakeProbe:
    def __init__(self):
        self.window = None
        self.idle = 0.0
        self.fail = False

    def foreground(self):
        if self.fail:
            raise RuntimeError("win32 error")
        return self.window

    def idle_seconds(self):
        return self.idle


class Clock:
    """Controls monotonic time and wall time together."""
    def __init__(self):
        self.t = 1000.0
        self.dt = datetime(2026, 10, 11, 9, 0, 0)

    def mono(self):
        return self.t

    def wall(self):
        return self.dt

    def advance(self, seconds):
        self.t += seconds
        self.dt += timedelta(seconds=seconds)


def make(**kw):
    probe, clock, sink = FakeProbe(), Clock(), []
    tracker = ActivityTracker(probe, sink.append, clock=clock.mono, wall=clock.wall, **kw)
    return tracker, probe, clock, sink


def run(tracker, clock, seconds, step=1.0):
    for _ in range(int(seconds / step)):
        clock.advance(step)
        tracker.tick()


CODE = WindowInfo("main.py - Neko - Visual Studio Code", "Code.exe")


def test_title_changes_inside_one_app_are_one_session():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 5)
    p.window = WindowInfo("tracker.py - Neko - Visual Studio Code", "Code.exe"); run(t, c, 5)
    t.pause()
    assert len(sink) == 1
    assert sink[0]["category"] == "Coding" and sink[0]["app"] == "Code.exe"
    assert sink[0]["duration_seconds"] == 10.0
    assert sink[0]["window_title"].startswith("tracker.py")


def test_switching_apps_closes_previous_session():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 10)
    p.window = WindowInfo("Stranger Things | Netflix - Brave", "brave.exe"); run(t, c, 5)
    assert len(sink) == 1 and sink[0]["category"] == "Coding" and sink[0]["duration_seconds"] == 10.0
    assert t.snapshot().category == "Entertainment"


def test_same_app_different_category_is_a_new_session():
    t, p, c, sink = make()
    p.window = WindowInfo("Python Tutorial - YouTube - Brave", "brave.exe"); t.tick(); run(t, c, 5)
    p.window = WindowInfo("Stand-up Comedy - YouTube - Brave", "brave.exe"); run(t, c, 5)
    assert [r["category"] for r in sink] == ["Learning"]
    assert t.snapshot().category == "Entertainment"


def test_sleep_gap_is_not_counted():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 5)
    c.advance(3600); t.tick()                 # laptop slept for an hour
    assert len(sink) == 1 and sink[0]["duration_seconds"] == 5.0
    run(t, c, 5)
    assert sum(t.snapshot().totals.values()) <= 11.0   # nothing like 3600


def test_clock_going_backwards_is_safe():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 5)
    c.t -= 500; t.tick()
    assert all(r["duration_seconds"] >= 0 for r in sink)


def test_idle_time_is_excluded_and_closes_session():
    t, p, c, sink = make(idle_threshold=300)
    p.window = CODE; t.tick(); run(t, c, 10)
    p.idle = 400; run(t, c, 5)
    assert len(sink) == 1 and sink[0]["duration_seconds"] == 10.0
    s = t.snapshot()
    assert s.user_idle and s.category is None
    p.idle = 0; run(t, c, 5)
    assert not t.snapshot().user_idle and t.snapshot().category == "Coding"


def test_pause_stops_counting_and_resume_starts_fresh():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 10)
    t.pause()
    assert len(sink) == 1 and t.snapshot().tracking == "paused"
    run(t, c, 30)
    assert sum(t.snapshot().totals.values()) == 10.0
    t.resume(); run(t, c, 6)
    assert t.snapshot().tracking == "running" and t.snapshot().session_seconds == 5.0


def test_system_and_blank_windows_are_ignored():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 5)
    p.window = WindowInfo("Task Switching", "explorer.exe"); run(t, c, 2)
    p.window = None; run(t, c, 1)
    p.window = WindowInfo("   ", None); run(t, c, 1)
    p.window = CODE; run(t, c, 5)
    t.pause()
    assert len(sink) == 1 and sink[0]["duration_seconds"] == 10.0


def test_very_short_sessions_are_dropped():
    t, p, c, sink = make(min_session_seconds=2.0)
    p.window = CODE; t.tick(); run(t, c, 5)
    p.window = WindowInfo("Quick glance - Brave", "brave.exe"); run(t, c, 1)
    p.window = CODE; run(t, c, 3)
    assert [r["category"] for r in sink] == ["Coding"]


def test_probe_errors_do_not_break_tracking():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 3)
    p.fail = True; run(t, c, 3)               # must not raise
    p.fail = False; run(t, c, 3)
    assert t.snapshot().category == "Coding"


def test_sink_errors_do_not_break_tracking():
    probe, clock = FakeProbe(), Clock()
    def bad_sink(record): raise OSError("disk full")
    t = ActivityTracker(probe, bad_sink, clock=clock.mono, wall=clock.wall)
    probe.window = CODE; t.tick(); run(t, clock, 5)
    t.pause()                                   # flush -> sink raises -> swallowed
    assert t.snapshot().tracking == "paused"


def test_entertainment_total_accumulates_and_resets_next_day():
    t, p, c, sink = make()
    net = WindowInfo("Stranger Things | Netflix - Brave", "brave.exe")
    p.window = net; t.tick(); run(t, c, 10)
    p.window = CODE; run(t, c, 3)
    p.window = net; run(t, c, 10)
    assert t.snapshot().entertainment_today_seconds >= 19
    c.dt = datetime(2026, 10, 12, 0, 0, 1); c.t += 1; t.tick()
    # yesterday's ~20s is gone; only this tick's own second belongs to the new day
    assert t.snapshot().entertainment_today_seconds == 1.0


def test_continuous_work_survives_short_distraction_but_not_a_real_break():
    t, p, c, sink = make(break_reset_seconds=20)
    p.window = CODE; t.tick(); run(t, c, 30)
    p.window = WindowInfo("Stranger Things | Netflix - Brave", "brave.exe"); run(t, c, 5)
    assert t.snapshot().continuous_work_seconds >= 30      # brief glance: streak kept
    run(t, c, 20)
    assert t.snapshot().continuous_work_seconds == 0.0     # 25s away >= 20s: reset


def test_unavailable_probe_reports_unavailable():
    probe, clock = FakeProbe(), Clock()
    t = ActivityTracker(probe, lambda r: None, available=False, clock=clock.mono, wall=clock.wall)
    probe.window = CODE; clock.advance(1); t.tick()
    assert t.snapshot().tracking == "unavailable" and t.snapshot().category is None


def test_record_shape():
    t, p, c, sink = make()
    p.window = CODE; t.tick(); run(t, c, 5); t.pause()
    r = sink[0]
    assert set(r) == {"start_time", "end_time", "duration_seconds", "category",
                      "window_title", "app", "classification_source"}
    assert r["start_time"] <= r["end_time"] and r["classification_source"].startswith("process:")


def test_thread_starts_and_stop_flushes_open_session():
    probe, sink = FakeProbe(), []
    probe.window = CODE
    t = ActivityTracker(probe, sink.append, poll_interval=0.02, min_session_seconds=0.05)
    t.start()
    time.sleep(0.4)
    assert any(th.name == "neko-tracker" and th.is_alive() for th in threading.enumerate())
    t.stop()
    assert not any(th.name == "neko-tracker" and th.is_alive() for th in threading.enumerate())
    assert len(sink) == 1 and sink[0]["category"] == "Coding"