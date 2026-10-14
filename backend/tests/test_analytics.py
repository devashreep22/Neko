from datetime import date

from app.services import analytics


def test_history_aggregates_saved_sessions_and_fills_days(monkeypatch):
    monkeypatch.setattr(analytics, "load_logs", lambda: [
        {"start_time": "2026-10-12 09:00:00", "duration_seconds": 60,
         "category": "Coding", "app": "Code.exe"},
        {"start_time": "2026-10-12 10:00:00", "duration_seconds": 30,
         "category": "Browsing", "app": "brave.exe"},
        {"start_time": "2026-10-06 10:00:00", "duration_seconds": 900,
         "category": "Learning", "app": "old.exe"},
        {"start_time": "not-a-date", "duration_seconds": 5000, "category": "Coding"},
    ])

    report = analytics.generate_history_report(days=3, today=date(2026, 10, 13))

    assert report["scope"] == "saved_completed_sessions"
    assert [day["date"] for day in report["days"]] == [
        "2026-10-11", "2026-10-12", "2026-10-13"]
    assert report["days"][0]["total_seconds"] == 0
    assert report["days"][1]["category_totals"] == {"Coding": 60.0, "Browsing": 30.0}
    assert report["category_totals"] == {"Coding": 60.0, "Browsing": 30.0}
    assert report["application_totals"] == {"Code.exe": 60.0, "brave.exe": 30.0}
    assert report["sessions"][0]["app"] == "brave.exe"
    assert "window_title" not in report["sessions"][0]


def test_history_handles_missing_or_invalid_log(monkeypatch):
    monkeypatch.setattr(analytics, "load_logs", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    report = analytics.generate_history_report(days=1, today=date(2026, 10, 13))
    assert report["data_status"] == "missing"
    assert report["days"][0]["total_seconds"] == 0
    assert report["category_totals"] == {}

    monkeypatch.setattr(analytics, "load_logs", lambda: (_ for _ in ()).throw(__import__("json").JSONDecodeError("bad", "{", 0)))
    corrupt = analytics.generate_history_report(days=1, today=date(2026, 10, 13))
    assert corrupt["data_status"] == "unreadable"
    assert corrupt["days"][0]["total_seconds"] == 0


def test_productive_time_uses_shared_category_rules(monkeypatch):
    monkeypatch.setattr(analytics, "load_logs", lambda: [
        {"category": "DSA", "duration_seconds": 60},
        {"category": "Work", "duration_seconds": 10},
        {"category": "Browsing", "duration_seconds": 90},
    ])
    report = analytics.generate_daily_report()
    assert report["category_totals"] == {"Coding": 60.0, "Work": 10.0, "Browsing": 90.0}
    assert report["productive_time_seconds"] == 70.0
