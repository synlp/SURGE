from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.text_view import export_event_text_views


class TextViewTests(unittest.TestCase):
    def test_top_root_by_in_bin_replies_and_earliest_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "Event"
            event.mkdir()
            posts = [
                {"post_id": "r1", "content_type": "root", "parent_id": "", "post_time": "2026-01-01T00:10:00Z"},
                {"post_id": "r2", "content_type": "root", "parent_id": "", "post_time": "2026-01-01T00:20:00Z"},
                {"post_id": "a", "content_type": "reply", "parent_id": "r2", "post_time": "2026-01-01T00:22:00Z"},
                {"post_id": "b", "content_type": "reply", "parent_id": "r2", "post_time": "2026-01-01T00:23:00Z"},
                {"post_id": "c", "content_type": "reply", "parent_id": "r2", "post_time": "2026-01-01T00:24:00Z"},
            ]
            (event / "posts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in posts), encoding="utf-8")
            export_event_text_views(
                event, root / "release",
                "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z",
            )
            first = json.loads((root / "release" / "Event_6H" / "text_view.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(first["n_posts_in_bin"], 5)
            self.assertEqual(first["main_posts"][0]["post_id"], "r2")
            self.assertEqual([row["post_id"] for row in first["main_posts"][0]["replies"]], ["a", "b"])


if __name__ == "__main__":
    unittest.main()

