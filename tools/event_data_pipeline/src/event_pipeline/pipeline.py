from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import TextIO

from event_pipeline.adapters.base import SourceAdapter
from event_pipeline.models import UnifiedInteraction
from event_pipeline.normalization import stable_hash
from event_pipeline.quality import EventQuality


def _write_jsonl(handle: TextIO, value: dict) -> None:
    handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _inside_window(post_time: str, start: str | None, end: str | None) -> bool:
    if not start and not end:
        return True
    if not post_time:
        return False
    instant = datetime.fromisoformat(post_time.replace("Z", "+00:00"))
    if start and instant < datetime.fromisoformat(start.replace("Z", "+00:00")):
        return False
    if end and instant >= datetime.fromisoformat(end.replace("Z", "+00:00")):
        return False
    return True


class EventWriters:
    def __init__(self, root: Path, event_id: str, stack: ExitStack):
        event_dir = root / event_id
        event_dir.mkdir(parents=True, exist_ok=True)
        self.posts = stack.enter_context((event_dir / "posts.jsonl").open("w", encoding="utf-8"))
        self.interactions = stack.enter_context((event_dir / "interactions.jsonl").open("w", encoding="utf-8"))
        self.duplicates = stack.enter_context((event_dir / "duplicates.jsonl").open("w", encoding="utf-8"))
        self.rejects = stack.enter_context((event_dir / "rejects.jsonl").open("w", encoding="utf-8"))


def convert_source(
    adapter: SourceAdapter,
    source: Path,
    output_dir: Path,
    *,
    selected_events: set[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    dedupe_text: bool = False,
    event_windows: dict[str, tuple[str | None, str | None]] | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    qualities: dict[str, EventQuality] = {}
    seen_post_ids: dict[tuple[str, str], str] = {}
    seen_text: dict[tuple[str, str], str] = {}
    canonical_ids: dict[tuple[str, str], str] = {}
    accepted_ids: set[tuple[str, str]] = set()

    with ExitStack() as stack:
        writers: dict[str, EventWriters] = {}

        def event_state(event_id: str) -> tuple[EventQuality, EventWriters]:
            quality = qualities.setdefault(event_id, EventQuality(event_id))
            writer = writers.get(event_id)
            if writer is None:
                writer = EventWriters(output_dir, event_id, stack)
                writers[event_id] = writer
            return quality, writer

        for adapted in adapter.iter_records(source, selected_events):
            post = adapted.post
            quality, writer = event_state(post.event_id)
            quality.observe_input(post)

            window_start, window_end = (event_windows or {}).get(post.event_id, (start, end))
            if not post.text or not _inside_window(post.post_time, window_start, window_end):
                quality.rejected_posts += 1
                _write_jsonl(writer.rejects, {
                    "reason": "blank_text" if not post.text else "outside_window_or_missing_time",
                    "post": post.to_dict(),
                })
                continue

            event_post_key = (post.event_id, post.post_id)
            duplicate_of = seen_post_ids.get(event_post_key)
            if duplicate_of is None and dedupe_text and post.content_hash:
                duplicate_of = seen_text.get((post.event_id, post.content_hash))
            if duplicate_of:
                canonical_ids[event_post_key] = duplicate_of
                quality.duplicate_posts += 1
                _write_jsonl(writer.duplicates, {
                    "duplicate_post_id": post.post_id,
                    "duplicate_of": duplicate_of,
                    "source_file": post.source_file,
                    "source_record_id": post.source_record_id,
                    "match": "post_id" if event_post_key in seen_post_ids else "content_hash",
                })
                continue

            seen_post_ids[event_post_key] = post.post_id
            canonical_ids[event_post_key] = post.post_id
            if dedupe_text and post.content_hash:
                seen_text[(post.event_id, post.content_hash)] = post.post_id
            accepted_ids.add(event_post_key)
            quality.accepted_posts += 1
            _write_jsonl(writer.posts, post.to_dict())

            edge = adapted.interaction
            if edge is not None:
                source_id = canonical_ids.get((edge.event_id, edge.source_post_id), edge.source_post_id)
                target_id = canonical_ids.get((edge.event_id, edge.target_post_id), edge.target_post_id)
                if (
                    (edge.event_id, source_id) in accepted_ids
                    and (edge.event_id, target_id) in accepted_ids
                    and source_id != target_id
                ):
                    normalized_edge = UnifiedInteraction(
                        edge_id=stable_hash(edge.event_id, edge.interaction_type, source_id, target_id),
                        event_id=edge.event_id,
                        platform=edge.platform,
                        interaction_type=edge.interaction_type,
                        source_post_id=source_id,
                        target_post_id=target_id,
                        source_time=edge.source_time,
                        target_time=edge.target_time,
                        source_file=edge.source_file,
                        source_adapter=edge.source_adapter,
                    )
                    quality.accepted_interactions += 1
                    _write_jsonl(writer.interactions, normalized_edge.to_dict())

    reports_dir = output_dir.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    event_reports = {event: quality.to_dict() for event, quality in sorted(qualities.items())}
    totals = {
        "events": len(event_reports),
        "input_records": sum(q.input_records for q in qualities.values()),
        "accepted_posts": sum(q.accepted_posts for q in qualities.values()),
        "accepted_interactions": sum(q.accepted_interactions for q in qualities.values()),
        "duplicate_posts": sum(q.duplicate_posts for q in qualities.values()),
        "rejected_posts": sum(q.rejected_posts for q in qualities.values()),
    }
    report = {
        "pipeline_version": "0.2.0",
        "adapter": adapter.name,
        "source_name": source.name,
        "window": {"start": start, "end": end},
        "event_windows": event_windows or {},
        "dedupe_text": dedupe_text,
        "totals": totals,
        "events": event_reports,
    }
    report_path = reports_dir / f"{source.stem}_quality.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
