import win32gui

from app.utils.activity_classifier import classify_activity

def get_current_activity():
    window = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(window)

    if title.strip() == "":
        title = "Unknown"

    category = classify_activity(title)

    return {
        "window_title": title,
        "category": category
    }