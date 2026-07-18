from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from event_pipeline.adapters import Data9ZipAdapter
from event_pipeline.pipeline import convert_source
from event_pipeline.validate import validate_unified


def payload(post_id: str, text: str, when: str) -> dict:
    return {
        "nickname": "n",
        "user_id": "u",
        "post_time": when,
        "ip_location": "",
        "hash_tag": [],
        "post_text": text,
        "reply_count": 0,
        "retweet_count": 0,
        "like_count": 0,
        "quote_count": 0,
        "view": "10",
        "lang": "en",
        "post_url": f"https://x.com/n/status/{post_id}",
        "emojis": [],
        "replies": [],
        "quotes": [],
    }


class PipelineRuleTests(unittest.TestCase):
    def test_same_post_can_belong_to_two_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "events.zip"
            item = payload("500", "shared", "2026-06-01T00:00:00.000Z")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data9/EventA/tweet/500.json", json.dumps(item))
                archive.writestr("data9/EventB/tweet/500.json", json.dumps(item))
            report = convert_source(Data9ZipAdapter(), archive_path, root / "unified")
            self.assertEqual(report["totals"]["accepted_posts"], 2)
            self.assertEqual(report["totals"]["duplicate_posts"], 0)

    def test_window_is_start_inclusive_end_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "window.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data9/Event/tweet/1.json", json.dumps(payload("1", "in", "2026-06-01T00:00:00.000Z")))
                archive.writestr("data9/Event/tweet/2.json", json.dumps(payload("2", "out", "2026-06-02T00:00:00.000Z")))
            report = convert_source(
                Data9ZipAdapter(), archive_path, root / "unified",
                start="2026-06-01T00:00:00Z", end="2026-06-02T00:00:00Z",
            )
            self.assertEqual(report["totals"]["accepted_posts"], 1)
            self.assertEqual(report["totals"]["rejected_posts"], 1)

    def test_generated_output_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "valid.zip"
            item = payload("10", "root", "2026-06-01T00:00:00.000Z")
            reply = payload("11", "reply", "2026-06-01T01:00:00.000Z")
            reply.pop("replies")
            reply.pop("quotes")
            item["replies"] = [reply]
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data9/Event/tweet/10.json", json.dumps(item))
            convert_source(Data9ZipAdapter(), archive_path, root / "unified")
            validation = validate_unified(root / "unified")
            self.assertTrue(validation["valid"], validation)
            self.assertEqual(validation["post_count"], 2)
            self.assertEqual(validation["edge_count"], 1)


if __name__ == "__main__":
    unittest.main()

