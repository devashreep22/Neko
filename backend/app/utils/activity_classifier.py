"""Rule-based activity classifier.

classify() returns a category plus the evidence used, so the UI and tests can
see *why* something was classified. classify_activity() keeps the old
signature (title in, category string out).

Evidence order (first match wins):
  1. Process name (most reliable, when the tracker supplies it)
  2. Empty / system windows
  3. YouTube video titles (keyword scoring; never "YouTube = Learning")
  4. Editors and known sites/apps
  5. Generic browser window -> Browsing
  6. Otherwise Unknown (we do not guess)

Window titles are imperfect evidence. When the evidence is weak or conflicting
the result is Browsing or Unknown with confidence "low".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.utils.categories import (
    BROWSING, CODING, COMMUNICATION, ENTERTAINMENT, LEARNING, MUSIC,
    SOCIAL_MEDIA, SYSTEM, UNKNOWN, WORK,
)


@dataclass(frozen=True)
class Classification:
    category: str
    source: str      # what matched, e.g. "process:code.exe", "youtube:learning"
    confidence: str  # "high" | "medium" | "low"


PROCESS_RULES = {
    "code.exe": CODING, "pycharm64.exe": CODING, "idea64.exe": CODING,
    "webstorm64.exe": CODING, "studio64.exe": CODING, "devenv.exe": CODING,
    "sublime_text.exe": CODING,
    "spotify.exe": MUSIC,
    "discord.exe": COMMUNICATION, "whatsapp.exe": COMMUNICATION,
    "telegram.exe": COMMUNICATION, "slack.exe": COMMUNICATION,
    "teams.exe": COMMUNICATION, "ms-teams.exe": COMMUNICATION,
    "zoom.exe": COMMUNICATION, "outlook.exe": COMMUNICATION,
    "winword.exe": WORK, "excel.exe": WORK, "powerpnt.exe": WORK,
    "onenote.exe": WORK, "notion.exe": WORK, "obsidian.exe": WORK,
}
BROWSER_PROCESSES = frozenset(
    {"chrome.exe", "brave.exe", "msedge.exe", "firefox.exe", "opera.exe", "vivaldi.exe"}
)
SYSTEM_TITLES = frozenset(
    {"task switching", "task view", "program manager", "windows default lock screen"}
)

# "Page title - [Profile -] Browser". Matches the browser name at the END only,
# so a page that merely mentions "edge" or "brave" is not mistaken for a browser.
# Edge appends the profile name; only well-known profile names are stripped,
# because a generic "any text" profile pattern would swallow real page titles.
_BROWSER_SUFFIX = re.compile(
    r"(?:\s[-–—]\s(?:personal|work|school|guest|inprivate|profile \d+))?"
    r"\s[-–—]\s(?:brave|google chrome|microsoft edge|mozilla firefox|opera|vivaldi)\s*$"
)
_YOUTUBE_TITLE = re.compile(r"^(?:\(\d+\)\s*)?(?P<video>.*?)\s*[-–]\s*youtube$")


def _rules(*items: Tuple[str, str, str]):
    return [(cat, src, re.compile(rx)) for cat, src, rx in items]


# Specific desktop editors first: a file *named* "netflix_clone.py" opened in
# VS Code must stay Coding.
EDITOR_RULES = _rules(
    (CODING, "visual-studio", r"\bvisual studio( code)?\b"),
    (CODING, "jetbrains", r"\b(pycharm|intellij|webstorm|android studio)\b"),
)
SITE_RULES = _rules(
    (MUSIC, "youtube-music", r"\byoutube music\b"),
    (MUSIC, "spotify", r"\bspotify\b"),
    (ENTERTAINMENT, "netflix", r"\bnetflix\b"),
    (ENTERTAINMENT, "prime-video", r"\bprime video\b"),
    (ENTERTAINMENT, "hotstar", r"\bhotstar\b"),
    (CODING, "coding-site", r"\b(leetcode|codeforces|codechef|hackerrank|github|stack overflow)\b"),
    (LEARNING, "learning-site",
     r"\b(takeuforward|geeksforgeeks|udemy|coursera|nptel|khan academy|edx|freecodecamp|w3schools|codecademy)\b"),
    (COMMUNICATION, "communication",
     r"\b(whatsapp|discord|telegram|slack|microsoft teams|zoom|gmail|outlook)\b"),
    (SOCIAL_MEDIA, "social",
     r"\b(instagram|facebook|reddit|twitter|linkedin|snapchat|pinterest)\b"),
    (WORK, "office", r"\b(google docs|google sheets|google slides|notion)\b|\s-\s(word|excel|powerpoint)$"),
)

# YouTube video-title keywords: (regex, weight). Strong = 2, weak = 1.
def _kw(strong: List[str], weak: List[str]):
    return [(re.compile(r"\b(?:%s)\b" % p), 2) for p in strong] + \
           [(re.compile(r"\b(?:%s)\b" % p), 1) for p in weak]


YOUTUBE_KEYWORDS = {
    LEARNING: _kw(
        ["tutorials?", "lectures?", "courses?", "explained", "for beginners", "data structures?",
         "dsa", "algorithms?", "dynamic programming", "system design", "leetcode",
         "interview preparation", "lessons?", "chapter", "syllabus", "revision", "machine learning"],
        ["learn", "learning", "python", "java", "javascript", "react", "sql", "physics",
         "chemistry", "maths?", "mathematics", "calculus", "biology", "jee", "neet", "upsc",
         "how to", "step by step", "interview"],
    ),
    MUSIC: _kw(
        ["official music video", "music video", "lyrics?", "lyric video", "official audio",
         "full album", "lofi", "lo-fi", "remix", "soundtrack", "karaoke", "mashup", "unplugged"],
        ["songs?", "playlist", "live concert", "bgm", "official video"],
    ),
    ENTERTAINMENT: _kw(
        ["comedy", "stand-?up", "funny", "pranks?", "vlogs?", "trailer", "reactions?",
         "gameplay", "full movie", "episodes?", "web series", "roast", "memes?", "shorts", "highlights"],
        ["movie", "season", "challenge", "unboxing", "hilarious"],
    ),
}


def _score(video_title: str, category: str) -> int:
    return sum(w for rx, w in YOUTUBE_KEYWORDS[category] if rx.search(video_title))


def _classify_youtube(page: str) -> Optional[Classification]:
    if page.strip() == "youtube":
        return Classification(BROWSING, "youtube:home", "low")
    m = _YOUTUBE_TITLE.match(page)
    if not m:
        return None
    video = m.group("video")
    ranked = sorted(((c, _score(video, c)) for c in YOUTUBE_KEYWORDS),
                    key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top < 2:
        return Classification(BROWSING, "youtube:unrecognized", "low")
    if top == second:
        return Classification(BROWSING, "youtube:ambiguous", "low")
    return Classification(best, f"youtube:{best.lower()}", "medium")


def classify(window_title: Optional[str], process_name: Optional[str] = None) -> Classification:
    proc = (process_name or "").strip().lower()
    if proc in PROCESS_RULES:
        return Classification(PROCESS_RULES[proc], f"process:{proc}", "high")

    title = window_title.strip() if isinstance(window_title, str) else ""
    low = title.lower()
    if not title or low == "unknown":
        return Classification(UNKNOWN, "no-title", "low")
    if low in SYSTEM_TITLES:
        return Classification(SYSTEM, "system-window", "high")

    m = _BROWSER_SUFFIX.search(low)
    is_browser = bool(m) or proc in BROWSER_PROCESSES
    page = low[: m.start()] if m else low

    youtube = _classify_youtube(page)
    if youtube:
        return youtube
    for category, source, rx in EDITOR_RULES:
        if rx.search(page):
            return Classification(category, f"app:{source}", "high")
    for category, source, rx in SITE_RULES:
        if rx.search(page):
            return Classification(category, f"title:{source}", "medium")
    if is_browser:
        return Classification(BROWSING, "browser", "medium")
    return Classification(UNKNOWN, "no-rule", "low")


def classify_activity(window_title: str) -> str:
    """Backward-compatible wrapper: returns just the category name."""
    return classify(window_title).category