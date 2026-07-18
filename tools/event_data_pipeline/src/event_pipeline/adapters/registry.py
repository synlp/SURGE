from __future__ import annotations

from event_pipeline.adapters.base import SourceAdapter
from event_pipeline.adapters.data9 import Data9ZipAdapter
from event_pipeline.adapters.generic_jsonl import GenericJsonlAdapter
from event_pipeline.adapters.reddit import RedditJsonlAdapter


ADAPTER_NAMES = ("data9", "generic-jsonl", "reddit-jsonl")


def create_adapter(name: str, *, platform: str | None = None) -> SourceAdapter:
    if name == "data9":
        return Data9ZipAdapter()
    if name == "generic-jsonl":
        return GenericJsonlAdapter(platform or "generic")
    if name == "reddit-jsonl":
        return RedditJsonlAdapter()
    raise ValueError(f"unknown adapter {name!r}; choose one of {', '.join(ADAPTER_NAMES)}")
