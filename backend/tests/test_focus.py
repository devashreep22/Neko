from datetime import datetime, timedelta, timezone

import pytest

from app.services.focus import FocusStore, domain_allowed, normalize_domains


def test_domains_normalize_and_reject_deceptive_suffixes():
    domains = normalize_domains(["https://LeetCode.com/", "*.example.org"])
    assert domains == ["leetcode.com", "*.example.org"]
    assert domain_allowed("leetcode.com", domains)
    assert not domain_allowed("www.leetcode.com", domains)
    assert domain_allowed("docs.example.org", domains)
    assert not domain_allowed("example.org.attacker.example", domains)
    with pytest.raises(ValueError):
        normalize_domains(["leetcode.com.attacker.example/path"])
    with pytest.raises(ValueError):
        normalize_domains(["*leetcode.com"])


def test_focus_duration_pause_resume_and_end_are_authoritative(tmp_path):
    mono = [100.0]
    wall = [datetime(2026, 10, 14, 12, tzinfo=timezone.utc)]
    store = FocusStore(tmp_path, clock=lambda: mono[0], wall=lambda: wall[0])
    started = store.start("Solve problems", None, 25, ["leetcode.com"], "monitor")
    with pytest.raises(RuntimeError):
        store.start("Second", None, 25, [], "monitor")
    mono[0] += 90
    assert store.get_active()["active_seconds"] == 90
    paused = store.pause()
    assert paused["status"] == "paused" and paused["active_seconds"] == 90
    wall[0] += timedelta(minutes=2)
    assert store.get_active()["paused_seconds"] == 120
    resumed = store.resume()
    assert resumed["status"] == "active"
    mono[0] += 30
    ended = store.end()
    assert ended["status"] == "cancelled"
    assert ended["active_seconds"] == 120
    assert ended["paused_seconds"] == 120
    assert ended["completion_reason"] == "user_ended"
    assert started["id"] == ended["id"]


def test_active_session_recovers_as_interrupted_and_persists(tmp_path):
    wall = [datetime(2026, 10, 14, 12, tzinfo=timezone.utc)]
    mono = [5.0]
    store = FocusStore(tmp_path, clock=lambda: mono[0], wall=lambda: wall[0])
    session = store.start("Read", "chapter 4", 15, [], "monitor")
    wall[0] += timedelta(seconds=45)
    recovered = FocusStore(tmp_path, clock=lambda: 500.0, wall=lambda: wall[0])
    recovered.recover_after_restart()
    item = recovered.get(session["id"])
    assert item["status"] == "interrupted"
    assert item["active_seconds"] == 0
    assert item["completion_reason"] == "application_restarted"
    assert recovered.get_active() is None


def test_only_one_open_session_and_strict_mode_needs_allowlist(tmp_path):
    store = FocusStore(tmp_path)
    with pytest.raises(ValueError):
        store.start("Task", None, 25, [], "controlled_browser")
    store.start("Task", None, 25, [], "monitor")
    with pytest.raises(RuntimeError):
        store.start("Another", None, 25, [], "monitor")


def test_browser_enforcement_status_requires_recent_confirmed_heartbeat(tmp_path):
    now = [datetime(2026, 10, 14, 12, tzinfo=timezone.utc)]
    store = FocusStore(tmp_path, wall=lambda: now[0])
    session = store.start("Study", None, 25, ["example.com"], "controlled_browser")
    assert session["enforcement_status"] == "degraded"
    active = store.browser_heartbeat(True, "example.com")
    assert active["enforcement_status"] == "enforced"
    now[0] += timedelta(seconds=31)
    assert store.get_active()["enforcement_status"] == "degraded"


def test_focus_analytics_local_days_week_comparison_and_completion_rate(tmp_path):
    now = [datetime(2026, 10, 14, 12, tzinfo=timezone.utc)]
    mono = [10.0]
    store = FocusStore(tmp_path, clock=lambda: mono[0], wall=lambda: now[0])
    started = store.start("Completed task", None, 1, [], "monitor")
    mono[0] += 60
    store.get_active()  # completes at its authoritative planned duration
    report = store.analytics_report(days=7, today=datetime(2026, 10, 14).date())
    assert len(report["days"]) == 7
    assert report["weekly"]["completed_sessions"] == 1
    assert report["weekly"]["actual_completed_seconds"] == 60
    assert report["weekly"]["session_completion_rate"] == 1
    assert report["weekly"]["previous_focus_seconds"] == 0


def test_focus_session_records_category_time_without_window_titles(tmp_path):
    now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
    store = FocusStore(tmp_path, wall=lambda: now)
    session = store.start("Write tests", None, 25, [], "monitor")
    store.record_activity_sample("code.exe", "private document title", "Coding", now, 5, False)
    detail = store.get(session["id"])
    assert detail["activity_categories"] == [{"category": "Coding", "seconds": 5.0}]
    assert "private document title" not in str(detail)
