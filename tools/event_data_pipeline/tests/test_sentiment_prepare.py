from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.sentiment_prepare import ALLOWED_FIELDS, prepare_sentiment_input


class SentimentPrepareTests(unittest.TestCase):
    def test_shards_are_windowed_and_privacy_minimized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "unified" / "Event"
            event.mkdir(parents=True)
            posts = [
                {"post_id": "a", "event_id": "Event", "platform": "twitter", "text": "x", "lang": "en", "post_time": "2026-01-01T01:00:00Z", "user_id": "secret"},
                {"post_id": "b", "event_id": "Event", "platform": "twitter", "text": "y", "lang": "en", "post_time": "2026-02-01T01:00:00Z", "nickname": "secret"},
            ]
            (event / "posts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in posts), encoding="utf-8")
            windows = {"events": [{"event_id": "Event", "recommended_window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}}]}
            window_path = root / "windows.json"
            window_path.write_text(json.dumps(windows), encoding="utf-8")
            result = prepare_sentiment_input(root / "unified", window_path, root / "input", shard_size=1)
            self.assertEqual(result["total_records"], 1)
            record = json.loads((root / "input" / "posts-00000.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(set(record), set(ALLOWED_FIELDS))
            self.assertNotIn("user_id", record)


if __name__ == "__main__":
    unittest.main()

