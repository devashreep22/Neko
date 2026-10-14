"""Canonical activity categories shared by the whole backend.

Every module (classifier, state engine, database, API) must use these names.
Older logs contain labels such as "DSA" and "Other"; normalize_category()
maps them forward. Callers should keep the original label in a separate
raw_category field so nothing is lost.
"""
from __future__ import annotations

from typing import Optional

CODING = "Coding"
LEARNING = "Learning"
WORK = "Work"
BROWSING = "Browsing"
ENTERTAINMENT = "Entertainment"
MUSIC = "Music"
SOCIAL_MEDIA = "Social Media"
COMMUNICATION = "Communication"
BREAK = "Break"
SYSTEM = "System"
UNKNOWN = "Unknown"

CATEGORIES = (
    CODING, LEARNING, WORK, BROWSING, ENTERTAINMENT, MUSIC,
    SOCIAL_MEDIA, COMMUNICATION, BREAK, SYSTEM, UNKNOWN,
)

# Default meaning of "productive time". Will become a user setting.
DEFAULT_PRODUCTIVE = frozenset({CODING, LEARNING, WORK})

_BY_KEY = {c.lower(): c for c in CATEGORIES}

# Labels used by earlier versions of NekoAI, plus a few likely variants.
LEGACY_ALIASES = {
    "dsa": CODING,
    "other": UNKNOWN,
    "social": SOCIAL_MEDIA,
    "productivity": WORK,
    "work/productivity": WORK,
}


def normalize_category(raw: Optional[str]) -> str:
    """Return a canonical category; anything unrecognized becomes Unknown."""
    if not isinstance(raw, str):
        return UNKNOWN
    key = raw.strip().lower()
    return _BY_KEY.get(key) or LEGACY_ALIASES.get(key) or UNKNOWN