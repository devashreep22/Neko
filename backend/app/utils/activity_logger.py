import json
import os

LOG_FILE = "app/data/activity_log.json"

def log_activity(record):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    data.append(record)

    with open(LOG_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)