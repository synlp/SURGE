from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol

from event_pipeline.models import AdaptedRecord


class SourceAdapter(Protocol):
    name: str

    def iter_records(
        self,
        source: Path,
        selected_events: set[str] | None = None,
    ) -> Iterable[AdaptedRecord]: ...

