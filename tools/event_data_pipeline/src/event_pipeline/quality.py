from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from event_pipeline.models import UnifiedPost


@dataclass
class EventQuality:
    event_id: str
    input_records: int = 0
    accepted_posts: int = 0
    accepted_interactions: int = 0
    duplicate_posts: int = 0
    rejected_posts: int = 0
    content_types: Counter = field(default_factory=Counter)
    languages: Counter = field(default_factory=Counter)
    warnings: Counter = field(default_factory=Counter)
    missing: Counter = field(default_factory=Counter)
    earliest_time: str = ""
    latest_time: str = ""

    def observe_input(self, post: UnifiedPost) -> None:
        self.input_records += 1
        self.content_types[post.content_type] += 1
        self.languages[post.lang or "missing"] += 1
        for warning in post.parse_warnings:
            self.warnings[warning] += 1
        for name, value in (
            ("text", post.text),
            ("post_time", post.post_time),
            ("post_url", post.post_url),
            ("external_id", post.external_id),
            ("user_id", post.user_id),
        ):
            if value in (None, ""):
                self.missing[name] += 1
        if post.post_time:
            if not self.earliest_time or post.post_time < self.earliest_time:
                self.earliest_time = post.post_time
            if not self.latest_time or post.post_time > self.latest_time:
                self.latest_time = post.post_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "input_records": self.input_records,
            "accepted_posts": self.accepted_posts,
            "accepted_interactions": self.accepted_interactions,
            "duplicate_posts": self.duplicate_posts,
            "rejected_posts": self.rejected_posts,
            "content_types": dict(self.content_types),
            "languages": dict(self.languages.most_common()),
            "warnings": dict(self.warnings.most_common()),
            "missing": dict(self.missing),
            "earliest_time": self.earliest_time,
            "latest_time": self.latest_time,
        }

