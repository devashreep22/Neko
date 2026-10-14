import pytest
from app.utils.activity_classifier import classify, classify_activity
from app.utils.categories import normalize_category


@pytest.mark.parametrize("title, expected", [
    ("main.py - Neko - Visual Studio Code", "Coding"),
    ("netflix_clone.py - Neko - Visual Studio Code", "Coding"),   # file name must not win
    ("Problems - LeetCode - Brave", "Coding"),
    ("Python Tutorial for Beginners - YouTube - Brave", "Learning"),
    ("(3) Python tutorial - YouTube - Brave", "Learning"),
    ("DSA Lecture 5: Binary Trees - YouTube - Google Chrome", "Learning"),
    ("LeetCode solution explained - YouTube - Brave", "Learning"),  # not Coding
    ("Funny python tutorial - YouTube - Brave", "Learning"),
    ("Best Stand-up Comedy 2024 - YouTube - Brave", "Entertainment"),
    ("My Daily Vlog in Pune - YouTube - Brave", "Entertainment"),
    ("Song X | Official Music Video - YouTube - Personal - Microsoft Edge", "Music"),
    ("Stranger Things | Netflix - Brave", "Entertainment"),
    ("Inbox (3) - me@gmail.com - Gmail - Brave", "Communication"),
    ("Quarterly plan - Google Docs - Brave", "Work"),
    ("New Tab - Brave", "Browsing"),
    ("YouTube - Brave", "Browsing"),
    ("Kitten falls off sofa - YouTube - Brave", "Browsing"),   # no evidence: neutral
    ("Funny tutorial - YouTube - Brave", "Browsing"),          # conflicting evidence
    ("Task Switching", "System"),
    ("", "Unknown"),
    ("Unknown", "Unknown"),
])
def test_titles(title, expected):
    assert classify(title).category == expected


def test_youtube_is_never_automatically_learning():
    assert classify("Anything at all - YouTube - Brave").category != "Learning"


def test_old_substring_bugs_are_gone():
    # "edge" and "brave" inside ordinary words used to mean Browsing.
    assert classify("Knowledge graphs intro").category == "Unknown"
    assert classify("Brave New World summary").category == "Unknown"


def test_process_name_beats_title():
    r = classify("Artist - Song", process_name="Spotify.exe")
    assert (r.category, r.confidence) == ("Music", "high")


def test_browser_process_makes_generic_window_browsing():
    assert classify("Some page", process_name="chrome.exe").category == "Browsing"


def test_result_explains_itself():
    r = classify("Python Tutorial - YouTube - Brave")
    assert r.source == "youtube:learning" and r.confidence == "medium"


@pytest.mark.parametrize("bad", [None, 42, [], {}])
def test_bad_input_is_unknown(bad):
    assert classify(bad).category == "Unknown"


def test_legacy_wrapper_returns_string():
    assert classify_activity("Problems - LeetCode - Brave") == "Coding"


def test_normalize_legacy_labels():
    assert normalize_category("DSA") == "Coding"
    assert normalize_category("Other") == "Unknown"
    assert normalize_category("coding") == "Coding"
    assert normalize_category(None) == "Unknown"
    assert normalize_category("Banana") == "Unknown"