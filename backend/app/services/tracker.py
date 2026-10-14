"""Activity tracker service: polls the foreground window and builds sessions.

Controllable (start / stop / pause / resume) so the web server can own its
lifecycle. All OS access goes through an injected probe, and all timing through
injected clocks, so the logic is fully testable.

Session rules:
  * A session is one continuous run on the same (app, category). Title changes
    inside the same app (switching VS Code files, YouTube videos of the same
    category) do not start a new session.
  * Only *active* time counts. Idle time, paused time and sleep/suspend gaps are
    excluded, and any of them closes the open session.
  * Windows with no title and system windows (Alt+Tab) are ignored.
  * Sessions shorter than min_session_seconds are discarded as noise.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

from app.utils.activity_classifier import classify
from app.utils.categories import DEFAULT_PRODUCTIVE, ENTERTAINMENT, SYSTEM

log = logging.getLogger("neko.tracker")


@dataclass
class _Open:
    key: tuple
    category: str
    source: str
    confidence: str
    title: str
    process: Optional[str]
    start_wall: datetime
    last_wall: datetime
    active: float = 0.0


@dataclass(frozen=True)
class Snapshot:
    tracking: str                      # "running" | "paused" | "unavailable"
    category: Optional[str]
    source: Optional[str]
    confidence: Optional[str]
    app: Optional[str]
    window_title: Optional[str]
    session_seconds: float
    entertainment_today_seconds: float
    continuous_work_seconds: float
    user_idle: bool
    totals: Dict[str, float]


class ActivityTracker:
    def __init__(
        self,
        probe,
        sink: Callable[[dict], None],
        *,
        available: bool = True,
        poll_interval: float = 1.0,
        idle_threshold: float = 300.0,
        max_gap: Optional[float] = None,
        min_session_seconds: float = 2.0,
        break_reset_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], datetime] = datetime.now,
        sample_sink: Optional[Callable[[Optional[str], Optional[str], Optional[str], datetime, float, bool], None]] = None,
    ) -> None:
        self._probe = probe
        self._sink = sink
        self._available = available
        self.poll_interval = poll_interval
        self.idle_threshold = idle_threshold
        # Longer than this between polls means suspend/resume or a stall.
        self.max_gap = max_gap if max_gap is not None else max(5.0, poll_interval * 5)
        self.min_session_seconds = min_session_seconds
        self.break_reset_seconds = break_reset_seconds
        self._clock = clock
        self._wall = wall
        self._sample_sink = sample_sink

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._paused = False
        self._open: Optional[_Open] = None
        self._last_tick: Optional[float] = None
        self._totals: Dict[str, float] = {}
        self._day = wall().date()
        self._work = 0.0
        self._away = 0.0
        self._user_idle = False
        self._errors = 0

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="neko-tracker", daemon=True)
            self._thread.start()
        log.info("Tracker started (poll %.1fs, idle after %.0fs)", self.poll_interval, self.idle_threshold)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
        with self._lock:
            self._flush()          # never lose the session in progress
        log.info("Tracker stopped")

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            self._user_idle = False
            self._flush()

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._last_tick = None  # do not count the time we were paused

    def _run(self) -> None:
        while not self._stop.wait(self.poll_interval):
            try:
                self.tick()
            except Exception:  # keep the thread alive no matter what
                log.exception("Tracker tick failed")

    # ---- core step (called by the thread, and directly by tests) ----------
    def tick(self) -> None:
        with self._lock:
            now, wall = self._clock(), self._wall()
            delta = 0.0 if self._last_tick is None else now - self._last_tick
            self._last_tick = now
            if wall.date() != self._day:        # new day: daily totals restart
                self._day = wall.date()
                self._totals.clear()

            if self._paused or not self._available:
                self._emit_sample(None, None, None, wall, 0.0, True)
                self._flush()
                return
            if delta < 0 or delta > self.max_gap:  # suspend/resume or clock jump
                self._emit_sample(None, None, None, wall, 0.0, True)
                self._flush()
                return

            info = self._read(self._probe.foreground, None)
            idle = self._read(self._probe.idle_seconds, 0.0)
            self._user_idle = idle >= self.idle_threshold
            if self._user_idle:
                self._emit_sample(info.process_name if info else None, info.title if info else None,
                                  None, wall, delta, True)
                self._flush()
                self._note_away(delta)
                return
            if info is None or not info.title.strip():
                self._emit_sample(None, None, None, wall, 0.0, False)
                return                           # transient window; ignore
            result = classify(info.title, info.process_name)
            if result.category == SYSTEM:
                self._emit_sample(info.process_name, info.title, result.category, wall, 0.0, True)
                return                           # Alt+Tab etc.

            self._emit_sample(info.process_name, info.title, result.category, wall, delta, False)

            key = ((info.process_name or info.title).lower(), result.category)
            if self._open is None or self._open.key != key:
                self._flush()
                self._open = _Open(
                    key=key, category=result.category, source=result.source,
                    confidence=result.confidence, title=info.title,
                    process=info.process_name,
                    start_wall=wall - timedelta(seconds=delta), last_wall=wall,
                )
            opened = self._open
            opened.active += delta
            opened.last_wall = wall
            opened.title = info.title
            self._totals[result.category] = self._totals.get(result.category, 0.0) + delta
            if result.category in DEFAULT_PRODUCTIVE:
                self._work += delta
                self._away = 0.0
            else:
                self._note_away(delta)

    # ---- queries ----------------------------------------------------------
    def snapshot(self) -> Snapshot:
        with self._lock:
            o = self._open
            if not self._available:
                status = "unavailable"
            else:
                status = "paused" if self._paused else "running"
            return Snapshot(
                tracking=status,
                category=o.category if o else None,
                source=o.source if o else None,
                confidence=o.confidence if o else None,
                app=o.process if o else None,
                window_title=o.title if o else None,
                session_seconds=o.active if o else 0.0,
                entertainment_today_seconds=self._totals.get(ENTERTAINMENT, 0.0),
                continuous_work_seconds=self._work,
                user_idle=self._user_idle,
                totals=dict(self._totals),
            )

    # ---- internals --------------------------------------------------------
    def _read(self, fn, default):
        try:
            value = fn()
            self._errors = 0
            return value
        except Exception as exc:
            self._errors += 1
            if self._errors == 1 or self._errors % 60 == 0:  # avoid log spam
                log.warning("Probe failed (%s x%d)", type(exc).__name__, self._errors)
            return default

    def _emit_sample(self, app, title, category, wall, delta, idle) -> None:
        if not self._sample_sink:
            return
        try:
            self._sample_sink(app, title, category, wall, delta, idle)
        except Exception:
            log.exception("Focus activity sample handling failed")

    def _note_away(self, delta: float) -> None:
        self._away += delta
        if self._away >= self.break_reset_seconds:
            self._work = 0.0

    def _flush(self) -> None:
        o, self._open = self._open, None
        if o is None or o.active < self.min_session_seconds:
            return
        record = {
            "start_time": o.start_wall.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": o.last_wall.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(o.active, 1),
            "category": o.category,
            "window_title": o.title,
            "app": o.process,
            "classification_source": o.source,
        }
        try:
            self._sink(record)
        except Exception:
            log.exception("Saving a session failed")


def default_sink(record: dict) -> None:
    """Write sessions with the project's existing JSON logger."""
    from app.utils.activity_logger import log_activity
    log_activity(record)


def build_default_tracker(settings, sample_sink=None) -> ActivityTracker:
    from app.system.foreground import create_probe
    probe, available = create_probe()
    return ActivityTracker(
        probe, default_sink, available=available,
        poll_interval=settings.poll_interval, idle_threshold=settings.idle_threshold,
        sample_sink=sample_sink,
    )
