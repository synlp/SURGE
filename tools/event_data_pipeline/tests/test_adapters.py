from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.adapters import GenericJsonlAdapter, RedditJsonlAdapter, create_adapter


class AdapterTests(unittest.TestCase):
    def test_registry(self) -> None:
        self.assertEqual(create_adapter("generic-jsonl", platform="x").platform, "x")
        self.assertEqual(create_adapter("reddit-jsonl").platform, "reddit")
        with self.assertRaises(ValueError):
            create_adapter("missing")

    def test_generic_jsonl_aliases_and_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            rows = [
                {"event": "E", "id": "root", "text": "Root", "created_at": "2026-01-01T00:00:00Z"},
                {"event": "E", "id": "reply", "body": "Reply", "timestamp": "2026-01-01T01:00:00Z", "type": "comment", "parent_id": "root"},
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            records = list(GenericJsonlAdapter("x").iter_records(path))
            self.assertEqual([item.post.content_type for item in records], ["root", "comment"])
            self.assertEqual(records[1].interaction.target_post_id, records[0].post.post_id)

    def test_reddit_epoch_and_fullname_ids(self) -> None:
        adapter = RedditJsonlAdapter()
        root = adapter.adapt_row({"event_id": "E", "kind": "t3", "id": "abc", "title": "Title", "created_utc": 0}, "r", "1")
        comment = adapter.adapt_row({"event_id": "E", "kind": "t1", "id": "def", "body": "Body", "created_utc": 3600, "parent_id": "t3_abc", "link_id": "t3_abc"}, "r", "2")
        self.assertEqual(root.post.post_time, "1970-01-01T00:00:00Z")
        self.assertEqual(comment.post.parent_id, root.post.post_id)
        self.assertEqual(comment.post.content_type, "comment")


if __name__ == "__main__":
    unittest.main()
