from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from event_pipeline.models import AdaptedRecord, UnifiedInteraction, UnifiedPost
from event_pipeline.normalization import (
    content_hash,
    make_post_id,
    normalize_language,
    normalize_text,
    parse_count,
    parse_time,
    stable_hash,
)


def _first(row: dict, *names: str, default=None):
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    return default


class GenericJsonlAdapter:
    """Adapt common flat social-media JSONL records to the unified schema.

    Required semantic fields are event, text and time. Common aliases are
    accepted; source-specific ambiguity remains visible through parse warnings.
    """

    name = "generic_jsonl_v1"

    def __init__(self, platform: str = "generic") -> None:
        platform = platform.strip().lower()
        if not platform:
            raise ValueError("platform must not be blank")
        self.platform = platform

    def iter_records(
        self,
        source: Path,
        selected_events: set[str] | None = None,
    ) -> Iterable[AdaptedRecord]:
        with source.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"{source}:{line_number}: record is not an object")
                adapted = self.adapt_row(row, source.name, str(line_number))
                if selected_events and adapted.post.event_id not in selected_events:
                    continue
                yield adapted

    def adapt_row(self, row: dict, source_file: str, source_record_id: str) -> AdaptedRecord:
        event_id = str(_first(row, "event_id", "event", "topic", default="")).strip()
        if not event_id:
            raise ValueError(f"{source_file}:{source_record_id}: missing event_id")
        text = normalize_text(_first(row, "text", "body", "content", "post_text", default=""))
        raw_time = str(_first(row, "post_time", "created_at", "timestamp", "time", default=""))
        post_time, time_warning = parse_time(raw_time)
        warnings = [time_warning] if time_warning else []
        external_id = str(_first(row, "external_id", "post_id", "id", default=""))
        url = str(_first(row, "post_url", "url", "permalink", default=""))
        post_id = make_post_id(
            self.platform,
            external_id,
            url,
            (event_id, raw_time, text[:200], source_record_id),
        )
        raw_type = str(_first(row, "content_type", "type", "kind", default="root")).lower()
        content_type = {
            "post": "root", "submission": "root", "tweet": "root",
            "response": "reply", "repost": "retweet",
        }.get(raw_type, raw_type or "root")
        parent_external = str(_first(row, "parent_id", "in_reply_to_id", "reply_to_id", default=""))
        root_external = str(_first(row, "root_post_id", "conversation_id", "thread_id", default=""))
        parent_id = make_post_id(self.platform, parent_external, "", ()) if parent_external else ""
        root_post_id = make_post_id(self.platform, root_external, "", ()) if root_external else ""
        lang, lang_raw = normalize_language(_first(row, "lang", "language", default=""))

        counts: dict[str, int] = {}
        aliases = {
            "like_count": ("like_count", "likes", "score"),
            "reply_count": ("reply_count", "replies", "num_comments"),
            "retweet_count": ("retweet_count", "retweets", "reposts"),
            "quote_count": ("quote_count", "quotes"),
        }
        for target, names in aliases.items():
            value, warning = parse_count(_first(row, *names, default=0))
            counts[target] = value or 0
            if warning:
                warnings.append(f"{target}:{warning}")
        view_count, view_warning = parse_count(_first(row, "view_count", "views"))
        if view_warning:
            warnings.append(f"view_count:{view_warning}")

        post = UnifiedPost(
            post_id=post_id,
            external_id=external_id,
            platform=self.platform,
            event_id=event_id,
            content_type=content_type,
            text=text,
            post_time=post_time,
            post_time_raw=raw_time,
            user_id=str(_first(row, "user_id", "author_id", "author", default="")),
            nickname=str(_first(row, "nickname", "username", "author_name", default="")),
            parent_id=parent_id,
            root_post_id=root_post_id or (post_id if content_type == "root" else parent_id),
            conversation_id=root_post_id or (post_id if content_type == "root" else parent_id),
            title=str(_first(row, "title", default="")),
            like_count=counts["like_count"],
            reply_count=counts["reply_count"],
            retweet_count=counts["retweet_count"],
            quote_count=counts["quote_count"],
            view_count=view_count,
            view_count_raw=str(_first(row, "view_count", "views", default="")),
            lang=lang,
            lang_raw=lang_raw,
            hashtags=[str(value) for value in (_first(row, "hashtags", "hash_tag", default=[]) or [])],
            emojis=[str(value) for value in (_first(row, "emojis", default=[]) or [])],
            post_url=url,
            source_adapter=self.name,
            source_file=source_file,
            source_record_id=source_record_id,
            content_hash=content_hash(text),
            is_main_post=content_type == "root",
            parse_warnings=warnings,
        )
        interaction = None
        if parent_id and parent_id != post_id:
            interaction_type = content_type if content_type in {"reply", "quote", "retweet", "comment"} else "reply"
            interaction = UnifiedInteraction(
                edge_id=stable_hash(event_id, interaction_type, post_id, parent_id),
                event_id=event_id,
                platform=self.platform,
                interaction_type=interaction_type,
                source_post_id=post_id,
                target_post_id=parent_id,
                source_time=post_time,
                target_time="",
                source_file=source_file,
                source_adapter=self.name,
            )
        return AdaptedRecord(post, interaction)
