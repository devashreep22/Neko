import time
import win32gui
from datetime import datetime
from app.utils.activity_logger import log_activity
from app.utils.activity_classifier import classify_activity

def get_active_window():
    window = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(window)

    if title.strip() == "":
        return "Unknown"

    return title

if __name__ == "__main__":
    print("NekoAI Activity Tracker Started...")
    print("Press Ctrl + C to stop\\n")

    previous_window = None
    previous_time = time.time()

    while True:
        active_window = get_active_window()

        if active_window != previous_window:

            current_time = time.time()

            if previous_window is not None:
                duration = current_time - previous_time
                category = classify_activity(previous_window)

                # Ignore system events like Alt+Tab
                if category == "System":
                    previous_window = active_window
                    previous_time = current_time
                    continue


                record = {
                "start_time": datetime.fromtimestamp(previous_time).strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": round(duration, 1),
                "category": category,
                "window_title": previous_window
                }

                log_activity(record)

                print(
                    f"{category:15} | {duration:6.1f}s | {previous_window}"
        )

            previous_window = active_window
            previous_time = current_time

        time.sleep(1)