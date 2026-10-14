import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from app.utils.categories import DEFAULT_PRODUCTIVE, normalize_category

LOG_FILE = Path(__file__).resolve().parents[1] / "data" / "activity_log.json"

def load_logs():
    with open(LOG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def generate_daily_report():
    logs = load_logs()

    totals = defaultdict(float)

    for record in logs:
        category = normalize_category(record.get("category"))
        duration = record["duration_seconds"]

        totals[category] += duration

    productive_time = sum(seconds for category, seconds in totals.items()
                          if category in DEFAULT_PRODUCTIVE)

    return {
        "category_totals": dict(totals),
        "productive_time_seconds": productive_time
    }


def generate_history_report(days=7, today=None):
    """Aggregate completed sessions from the existing local activity log."""
    days = min(31, max(1, int(days)))
    today = today or date.today()
    first_day = today - timedelta(days=days - 1)
    per_day = defaultdict(lambda: defaultdict(float))
    category_totals = defaultdict(float)
    application_totals = defaultdict(float)
    sessions = []
    data_status = "available"
    try:
        records = load_logs()
        if not isinstance(records, list):
            data_status = "invalid"
            records = []
    except FileNotFoundError:
        data_status = "missing"
        records = []
    except (OSError, json.JSONDecodeError):
        data_status = "unreadable"
        records = []

    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        raw_start = record.get("start_time")
        try:
            stamp = datetime.fromisoformat(raw_start) if isinstance(raw_start, str) else None
        except ValueError:
            try:
                stamp = datetime.strptime(raw_start, "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                continue
        if stamp is None or not first_day <= stamp.date() <= today:
            continue
        try:
            seconds = max(0.0, float(record.get("duration_seconds", 0)))
        except (TypeError, ValueError):
            continue
        category = normalize_category(record.get("category"))
        per_day[stamp.date()][category] += seconds
        category_totals[category] += seconds
        app_name = record.get("app")
        if app_name:
            application_totals[str(app_name)] += seconds
        sessions.append({
            "start_time": stamp.isoformat(timespec="seconds"),
            "date": stamp.date().isoformat(), "category": category,
            "app": str(app_name) if app_name else None,
            "duration_seconds": round(seconds, 1),
        })

    rows = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        values = per_day[day]
        total = sum(values.values())
        rows.append({
            "date": day.isoformat(), "label": day.strftime("%a"),
            "category_totals": {key: round(value, 1) for key, value in values.items()},
            "total_seconds": round(total, 1),
            "productive_seconds": round(sum(value for key, value in values.items()
                                               if key in DEFAULT_PRODUCTIVE), 1),
        })
    return {
        "scope": "saved_completed_sessions", "data_status": data_status, "days": rows,
        "category_totals": {key: round(value, 1) for key, value in category_totals.items()},
        "application_totals": {key: round(value, 1) for key, value in application_totals.items()},
        "sessions": sorted(sessions, key=lambda row: row["start_time"], reverse=True),
    }

if __name__ == "__main__":
    report = generate_daily_report()

    print("===== NekoAI Daily Report =====\n")

    for category, seconds in report["category_totals"].items():
        print(f"{category:15}: {seconds:.1f} seconds")

    print("\n------------------------------")
    print(
        f"Total Productive Time: {report['productive_time_seconds']:.1f} seconds"
    )
