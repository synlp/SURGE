from __future__ import annotations

import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

from event_pipeline.models import AdaptedRecord, UnifiedInteraction, UnifiedPost
from event_pipeline.normalization import (
    content_hash,
    extract_external_id,
    make_post_id,
    normalize_language,
    normalize_text,
    parse_count,
    parse_time,
    stable_hash,
)


class Data9ZipAdapter:
    """Stream data9's nested X JSON files from a ZIP archive."""

    name = "data9_zip_v1"
    platform = "twitter"

    def iter_records(
        self,
        source: Path,
        selected_events: set[str] | None = None,
    ) -> Iterable[AdaptedRecord]:
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".json"):
                    continue
                path = PurePosixPath(info.filename)
                if len(path.parts) < 4 or path.parts[0] != "data9":
                    continue
                event_id = path.parts[1]
                if selected_events and event_id not in selected_events:
                    continue
                payload = json.loads(archive.read(info).decode("utf-8-sig"))
                if not isinstance(payload, dict):
                    raise ValueError(f"Root JSON is not an object: {info.filename}")

                root = self._to_post(
                    payload,
                    event_id=event_id,
                    content_type="root",
                    source_file=info.filename,
                    source_record_id="root",
                    filename_id=path.stem,
                )
                root.root_post_id = root.post_id
                root.conversation_id = root.post_id
                yield AdaptedRecord(root)

                for relation_key, content_type in (("replies", "reply"), ("quotes", "quote")):
                    children = payload.get(relation_key) or []
                    if not isinstance(children, list):
                        raise ValueError(f"{relation_key} is not an array: {info.filename}")
                    for index, child in enumerate(children):
                        if not isinstance(child, dict):
                            raise ValueError(f"{relation_key}[{index}] is not an object: {info.filename}")
                        post = self._to_post(
                            child,
                            event_id=event_id,
                            content_type=content_type,
                            source_file=info.filename,
                            source_record_id=f"{relation_key}[{index}]",
                            filename_id="",
                        )
                        post.parent_id = root.post_id
                        post.root_post_id = root.post_id
                        post.conversation_id = root.post_id
                        edge = UnifiedInteraction(
                            edge_id=stable_hash(event_id, content_type, post.post_id, root.post_id),
                            event_id=event_id,
                            platform=self.platform,
                            interaction_type=content_type,
                            source_post_id=post.post_id,
                            target_post_id=root.post_id,
                            source_time=post.post_time,
                            target_time=root.post_time,
                            source_file=info.filename,
                            source_adapter=self.name,
                        )
                        yield AdaptedRecord(post, edge)

    def _to_post(
        self,
        item: dict,
        *,
        event_id: str,
        content_type: str,
        source_file: str,
        source_record_id: str,
        filename_id: str,
    ) -> UnifiedPost:
        warnings: list[str] = []
        text = normalize_text(item.get("post_text"))
        raw_time = item.get("post_time") if isinstance(item.get("post_time"), str) else ""
        post_time, time_warning = parse_time(raw_time)
        if time_warning:
            warnings.append(time_warning)

        url = item.get("post_url") if isinstance(item.get("post_url"), str) else ""
        external_id = extract_external_id(url) or filename_id
        user_id = str(item.get("user_id") or "")
        post_id = make_post_id(
            self.platform,
            external_id,
            url,
            (event_id, user_id, raw_time, text[:200], source_record_id),
        )
        lang, lang_raw = normalize_language(item.get("lang"))

        counts: dict[str, int] = {}
        for key in ("like_count", "reply_count", "retweet_count", "quote_count"):
            value, warning = parse_count(item.get(key))
            counts[key] = value or 0
            if warning:
                warnings.append(f"{key}:{warning}")
        view_count, view_warning = parse_count(item.get("view"))
        if view_warning:
            warnings.append(f"view:{view_warning}")

        hashtags = item.get("hash_tag") if isinstance(item.get("hash_tag"), list) else []
        emojis = item.get("emojis") if isinstance(item.get("emojis"), list) else []
        return UnifiedPost(
            post_id=post_id,
            external_id=external_id,
            platform=self.platform,
            event_id=event_id,
            content_type=content_type,
            text=text,
            post_time=post_time,
            post_time_raw=raw_time,
            user_id=user_id,
            nickname=str(item.get("nickname") or ""),
            like_count=counts["like_count"],
            reply_count=counts["reply_count"],
            retweet_count=counts["retweet_count"],
            quote_count=counts["quote_count"],
            view_count=view_count,
            view_count_raw=str(item.get("view") or ""),
            lang=lang,
            lang_raw=lang_raw,
            hashtags=[str(value) for value in hashtags],
            emojis=[str(value) for value in emojis],
            post_url=url,
            ip_location=str(item.get("ip_location") or ""),
            source_adapter=self.name,
            source_file=source_file,
            source_record_id=source_record_id,
            content_hash=content_hash(text),
            is_main_post=content_type == "root",
            parse_warnings=warnings,
        )

