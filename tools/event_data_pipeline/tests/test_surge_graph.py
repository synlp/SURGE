from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.surge_graph import export_event_graph


class SurgeGraphTests(unittest.TestCase):
    def test_edges_require_both_endpoints_in_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "Event"
            event.mkdir()
            posts = [
                {"post_id": "a", "post_time": "2026-01-01T01:00:00Z", "platform": "twitter", "post_url": "u1"},
                {"post_id": "b", "post_time": "2026-01-01T02:00:00Z", "platform": "twitter", "post_url": "u2"},
                {"post_id": "c", "post_time": "2026-02-01T00:00:00Z", "platform": "twitter", "post_url": "u3"},
            ]
            edges = [
                {"source_post_id": "b", "target_post_id": "a", "source_time": "2026-01-01T02:00:00Z", "target_time": "2026-01-01T01:00:00Z", "interaction_type": "reply", "platform": "twitter"},
                {"source_post_id": "c", "target_post_id": "a", "source_time": "2026-02-01T00:00:00Z", "target_time": "2026-01-01T01:00:00Z", "interaction_type": "reply", "platform": "twitter"},
            ]
            (event / "posts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in posts), encoding="utf-8")
            (event / "interactions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in edges), encoding="utf-8")
            result = export_event_graph(
                event, root / "release",
                "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z",
            )
            self.assertEqual(result["lookup_posts"], 2)
            self.assertEqual(result["exported_edges"], 1)
            self.assertEqual(result["dropped_edges"], 1)
            exported = json.loads((root / "release" / "Event" / "edges.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(exported["event"], "Event")
            self.assertNotIn("source_user_id", exported)


if __name__ == "__main__":
    unittest.main()

