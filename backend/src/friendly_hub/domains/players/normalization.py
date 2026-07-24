from __future__ import annotations

import re
import unicodedata

VALID_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN"}
VALID_STATUSES = {"active", "inactive", "injured", "reserve", "unknown"}
SUFFIXES = {"JR": "Jr.", "SR": "Sr.", "II": "II", "III": "III", "IV": "IV"}


def normalize_search_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip()).casefold()
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    alphanumeric = re.sub(r"[^a-z0-9]+", " ", without_marks)
    return " ".join(alphanumeric.split())


def normalize_position(value: str | None) -> str:
    normalized = (value or "").strip().upper().replace("DST", "DEF")
    return normalized if normalized in VALID_POSITIONS else "UNKNOWN"


def normalize_status(value: str | None) -> str:
    normalized = (value or "unknown").strip().casefold()
    aliases = {
        "active": "active",
        "inactive": "inactive",
        "injured": "injured",
        "ir": "injured",
        "reserve": "reserve",
        "pup": "reserve",
    }
    return aliases.get(normalized, "unknown")


def normalize_team(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper()
    return normalized[:8] or None


def split_name(value: str) -> tuple[str, str | None, str | None, str]:
    display_name = " ".join(value.strip().split())
    parts = display_name.split()
    suffix = None
    if parts:
        suffix_key = parts[-1].rstrip(".").upper()
        if suffix_key in SUFFIXES:
            suffix = SUFFIXES[suffix_key]
            parts = parts[:-1]
    first_name = parts[0] if parts else display_name
    last_name = " ".join(parts[1:]) or None
    if suffix:
        display_name = f"{' '.join(parts)} {suffix}".strip()
    return first_name, last_name, suffix, display_name
