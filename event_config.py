"""
SURGE event registry.

Provides the :class:`EventConfig` schema and utility functions for
loading the 102-event registry from the per-corpus metadata JSON. The
canonical list of events lives in ``data/events/event_metadata.json``
(real events) and ``data/synthetic_examples/event_metadata.json``
(synthetic demo events), both following the same schema.

The five paper categories are: ``natural_disaster``, ``political``,
``social_movement``, ``technology``, ``sports_entertainment``. The
synthetic demo events use ``synthetic`` so that any analysis filtering
by paper category excludes them by default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAPER_CATEGORIES: tuple[str, ...] = (
    "natural_disaster",
    "political",
    "social_movement",
    "technology",
    "sports_entertainment",
)

VALID_CATEGORIES: tuple[str, ...] = PAPER_CATEGORIES + ("synthetic",)

VALID_GRANULARITIES: tuple[str, ...] = ("6H", "12H", "1D")

DEFAULT_REAL_METADATA = Path("data/events/event_metadata.json")
DEFAULT_SYNTHETIC_METADATA = Path("data/synthetic_examples/event_metadata.json")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EventConfig:
    """One registry entry per released event.

    Attributes:
        name: Stable identifier used in folder names ``<name>_<granularity>``
            and in metric-aggregation outputs. Lowercase, snake_case, no
            punctuation.
        display_name: Human-readable event title used in the paper's tables
            and figures.
        category: One of :data:`VALID_CATEGORIES`.
        start_time: ISO-8601 string for the bin-start of the first bin in
            the released active period. May be the empty string when the
            real-event time series have not yet been generated.
        end_time: ISO-8601 string for the bin-end of the last bin in the
            released active period. Same caveat as ``start_time``.
        available_granularities: Subset of :data:`VALID_GRANULARITIES`
            for which the event has at least one released CSV directory.
        notes: Optional maintainer notes.
    """

    name: str
    display_name: str
    category: str
    start_time: str = ""
    end_time: str = ""
    available_granularities: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:  # type: ignore[misc]
        if self.category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}' for event '{self.name}'. "
                f"Must be one of {VALID_CATEGORIES}."
            )
        for g in self.available_granularities:
            if g not in VALID_GRANULARITIES:
                raise ValueError(
                    f"Invalid granularity '{g}' for event '{self.name}'. "
                    f"Must be one of {VALID_GRANULARITIES}."
                )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_events_from_metadata(metadata_path: Path | str) -> list[EventConfig]:
    """Load events from a metadata JSON file.

    The JSON file is expected to follow the schema:

        {"events": [<EventConfig dict>, ...], "note": "<optional>"}

    Returns:
        List of :class:`EventConfig` parsed from the file.

    Raises:
        FileNotFoundError: when the file does not exist.
    """
    p = Path(metadata_path)
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    out: list[EventConfig] = []
    for entry in raw.get("events", []):
        out.append(
            EventConfig(
                name=entry["name"],
                display_name=entry["display_name"],
                category=entry["category"],
                start_time=entry.get("start_time", ""),
                end_time=entry.get("end_time", ""),
                available_granularities=tuple(entry.get("available_granularities", ())),
                notes=entry.get("notes", ""),
            )
        )
    return out


def get_real_events(
    metadata_path: Path | str = DEFAULT_REAL_METADATA,
) -> list[EventConfig]:
    """Return the 102 real events. Empty list if metadata file is absent."""
    p = Path(metadata_path)
    if not p.exists():
        return []
    return load_events_from_metadata(p)


def get_synthetic_events(
    metadata_path: Path | str = DEFAULT_SYNTHETIC_METADATA,
) -> list[EventConfig]:
    """Return the synthetic demo events. Empty list if metadata file is absent."""
    p = Path(metadata_path)
    if not p.exists():
        return []
    return load_events_from_metadata(p)


def get_all_events() -> list[EventConfig]:
    """Return real events first, then synthetic demo events."""
    return get_real_events() + get_synthetic_events()


def get_events_by_category(category: str) -> list[EventConfig]:
    """Return all (real + synthetic) events whose ``category`` matches."""
    return [e for e in get_all_events() if e.category == category]
