from __future__ import annotations

from datetime import datetime, timezone

from event_pipeline.adapters.generic_jsonl import GenericJsonlAdapter


def _reddit_id(value: object) -> str:
    raw = str(value or "")
    return raw.split("_", 1)[-1] if raw.startswith(("t1_", "t3_")) else raw


class RedditJsonlAdapter(GenericJsonlAdapter):
    """Adapt common Reddit submission/comment JSONL exports."""

    name = "reddit_jsonl_v1"

    def __init__(self) -> None:
        super().__init__("reddit")

    def adapt_row(self, row: dict, source_file: str, source_record_id: str):
        normalized = dict(row)
        kind = str(row.get("kind") or row.get("type") or "").lower()
        is_comment = kind in {"comment", "t1"} or bool(row.get("parent_id"))
        normalized["content_type"] = "comment" if is_comment else "root"
        normalized["external_id"] = _reddit_id(row.get("id") or row.get("name"))
        if is_comment:
            normalized["text"] = row.get("body") or row.get("text") or ""
            normalized["parent_id"] = _reddit_id(row.get("parent_id"))
            normalized["root_post_id"] = _reddit_id(row.get("link_id"))
        else:
            normalized["text"] = row.get("selftext") or row.get("title") or row.get("text") or ""
        created = row.get("created_utc")
        if isinstance(created, (int, float)):
            normalized["post_time"] = datetime.fromtimestamp(created, timezone.utc).isoformat().replace("+00:00", "Z")
        normalized["post_url"] = row.get("url") or row.get("permalink") or ""
        normalized["like_count"] = row.get("score", 0)
        normalized["reply_count"] = row.get("num_comments", 0)
        normalized["user_id"] = row.get("author_fullname") or row.get("author") or ""
        return super().adapt_row(normalized, source_file, source_record_id)
