from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone


_STATUS_RE = re.compile(r"/(?:status|statuses)/(\d+)", re.IGNORECASE)
_COMPACT_COUNT_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*([KMB]?)$", re.IGNORECASE)
_LANG_ALIASES = {"iw": "he", "in": "id", "ji": "yi"}
_SPACE_RE = re.compile(r"\s+")


def stable_hash(*parts: object, length: int = 32) -> str:
    value = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def extract_external_id(url: str) -> str:
    if not url:
        return ""
    match = _STATUS_RE.search(url)
    return match.group(1) if match else ""


def normalize_text(text: object) -> str:
    if not isinstance(text, str):
        return ""
    return _SPACE_RE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    normalized = normalize_text(text).casefold()
    return stable_hash(normalized, length=40) if normalized else ""


def normalize_language(value: object) -> tuple[str, str]:
    raw = value.strip() if isinstance(value, str) else ""
    lowered = raw.lower()
    return _LANG_ALIASES.get(lowered, lowered), raw


def parse_count(value: object) -> tuple[int | None, str | None]:
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, "boolean_count"
    if isinstance(value, int):
        return (value, None) if value >= 0 else (None, "negative_count")
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            return None, "invalid_numeric_count"
        return int(value), None
    if not isinstance(value, str):
        return None, "unsupported_count_type"
    compact = value.strip().replace(",", "").upper()
    if not compact:
        return None, None
    match = _COMPACT_COUNT_RE.fullmatch(compact)
    if not match:
        return None, "unparseable_count"
    number = float(match.group(1))
    if number < 0:
        return None, "negative_count"
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2)]
    return int(number * multiplier), None


def parse_time(value: object) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value.strip():
        return "", "missing_time"
    raw = value.strip()
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return "", "unparseable_time"
    warning = None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
        warning = "naive_time_assumed_utc"
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z"), warning


def make_post_id(platform: str, external_id: str, url: str, fallback_parts: tuple[object, ...]) -> str:
    if external_id:
        return stable_hash(platform, external_id)
    if url:
        return stable_hash(platform, url)
    return stable_hash(platform, *fallback_parts)

