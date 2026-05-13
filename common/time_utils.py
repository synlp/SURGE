"""
Unified time parsing utilities.

Consolidates duplicated parse_time() logic from 6+ modules into a single source.
Handles all timestamp formats found across Twitter, Reddit, and Threads data.
"""

from datetime import datetime
from typing import Optional


# All timestamp formats encountered across raw data and SA output,
# ordered from most specific to least specific for efficient matching.
_TIME_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f%z",   # 2025-05-10T11:15:00.000+00:00
    "%Y-%m-%dT%H:%M:%S%z",       # 2025-05-10T11:15:00+00:00
    "%Y-%m-%dT%H:%M:%S.%fZ",     # 2025-05-10T11:15:00.000Z
    "%Y-%m-%dT%H:%M:%SZ",        # 2025-05-10T11:15:00Z
    "%Y-%m-%dT%H:%M:%S.%f",      # 2025-05-10T11:15:00.000
    "%Y-%m-%dT%H:%M:%S",         # 2025-05-10T11:15:00
    "%Y-%m-%d %H:%M:%S.%f%z",    # 2025-05-10 11:15:00.000+00:00
    "%Y-%m-%d %H:%M:%S%z",       # 2025-05-10 11:15:00+00:00
    "%Y-%m-%d %H:%M:%S",         # 2025-05-10 11:15:00
    "%Y-%m-%d",                   # 2025-05-10
]


def parse_time(time_str: str) -> Optional[datetime]:
    """Parse a timestamp string into a timezone-naive datetime.

    Tries all known formats. Timezone info is stripped to ensure
    consistent comparison across platforms (Twitter uses UTC 'Z',
    Reddit uses '+00:00', Threads uses ISO with tz).

    Args:
        time_str: Raw timestamp string from any platform/format.

    Returns:
        Timezone-naive datetime, or None if parsing fails or input is empty.
    """
    if not time_str or not isinstance(time_str, str):
        return None

    time_str = time_str.strip()
    if not time_str:
        return None

    for fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(time_str, fmt)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    return None


def format_time(dt: Optional[datetime], fmt: str = "%Y-%m-%dT%H:%M:%S") -> str:
    """Format a datetime to a standard string representation.

    Args:
        dt: Datetime to format.
        fmt: Output format string.

    Returns:
        Formatted string, or empty string if dt is None.
    """
    if dt is None:
        return ""
    return dt.strftime(fmt)
