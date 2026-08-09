import json
from collections import defaultdict

LOG_FILE = "app/data/activity_log.json"

def load_logs():
    with open(LOG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def generate_daily_report():
    logs = load_logs()

    totals = defaultdict(float)

    for record in logs:
        category = record["category"]
        duration = record["duration_seconds"]

        totals[category] += duration

    productive_categories = {"Coding", "DSA", "Learning"}
    productive_time = 0

    for category, seconds in totals.items():
        if category in productive_categories:
            productive_time += seconds

    return {
        "category_totals": dict(totals),
        "productive_time_seconds": productive_time
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