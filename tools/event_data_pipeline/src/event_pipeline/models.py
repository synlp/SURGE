from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "1.0.0"


@dataclass(slots=True)
class UnifiedPost:
    post_id: str
    external_id: str
    platform: str
    event_id: str
    content_type: str
    text: str
    post_time: str
    post_time_raw: str
    user_id: str
    nickname: str
    parent_id: str = ""
    root_post_id: str = ""
    conversation_id: str = ""
    title: str = ""
    like_count: int = 0
    reply_count: int = 0
    retweet_count: int = 0
    quote_count: int = 0
    view_count: int | None = None
    view_count_raw: str = ""
    lang: str = ""
    lang_raw: str = ""
    hashtags: list[str] = field(default_factory=list)
    emojis: list[str] = field(default_factory=list)
    post_url: str = ""
    ip_location: str = ""
    source_adapter: str = ""
    source_file: str = ""
    source_record_id: str = ""
    content_hash: str = ""
    is_main_post: bool = False
    parse_warnings: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UnifiedInteraction:
    edge_id: str
    event_id: str
    platform: str
    interaction_type: str
    source_post_id: str
    target_post_id: str
    source_time: str
    target_time: str
    source_file: str
    source_adapter: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AdaptedRecord:
    post: UnifiedPost
    interaction: UnifiedInteraction | None = None

