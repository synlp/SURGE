from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from event_pipeline.batch import EventSpec, load_event_specs, run_batch


def post(post_id: str, when: str) -> dict:
    return {
        "nickname": "n", "user_id": "u", "post_time": when,
        "ip_location": "", "hash_tag": [], "post_text": f"text-{post_id}",
        "reply_count": 0, "retweet_count": 0, "like_count": 0,
        "quote_count": 0, "view": "1", "lang": "en",
        "post_url": f"https://x.com/n/status/{post_id}", "emojis": [],
        "replies": [], "quotes": [],
    }


class BatchTests(unittest.TestCase):
    def test_config_rejects_duplicate_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"events": [{"event_id": "A"}, {"event_id": "A"}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_event_specs(path)

    def test_batch_applies_individual_windows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "batch.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data9/A/tweet/1.json", json.dumps(post("1", "2026-06-01T00:00:00.000Z")))
                archive.writestr("data9/B/tweet/2.json", json.dumps(post("2", "2026-07-01T00:00:00.000Z")))
            result = run_batch(
                archive_path,
                root / "unified",
                [
                    EventSpec("A", "2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z"),
                    EventSpec("B", "2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z"),
                ],
            )
            self.assertEqual(result["totals"]["accepted_posts"], 1)
            self.assertEqual(result["totals"]["rejected_posts"], 1)
            self.assertTrue(result["validation"]["valid"])


if __name__ == "__main__":
    unittest.main()

