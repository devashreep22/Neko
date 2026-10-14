import json
import os
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parents[1] / "data" / "activity_log.json"

def log_activity(record):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError as exc:
                # Preserve malformed history rather than silently replacing it.
                raise RuntimeError(f"Activity log is not valid JSON: {LOG_FILE}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"Activity log root must be a JSON list: {LOG_FILE}")
    else:
        data = []

    data.append(record)

    with open(LOG_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
