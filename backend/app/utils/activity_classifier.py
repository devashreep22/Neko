def classify_activity(window_title: str):
    title = window_title.lower()

    # Coding
    if "visual studio code" in title or "pycharm" in title or "intellij" in title:
        return "Coding"

    # DSA
    if "leetcode" in title or "takeuforward" in title or "codeforces" in title:
        return "DSA"

    # Learning
    if "youtube" in title or "udemy" in title or "coursera" in title:
        return "Learning"

    # Entertainment
    if "netflix" in title or "spotify" in title or "prime video" in title:
        return "Entertainment"

    # Communication
    if "whatsapp" in title or "discord" in title or "telegram" in title:
        return "Communication"

    # Browser
    if "brave" in title or "chrome" in title or "edge" in title:
        return "Browsing"

    # System
    if "task switching" in title:
        return "System"

    
    return "Other"
