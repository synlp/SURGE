from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from event_pipeline.adapters import Data9ZipAdapter
from event_pipeline.normalization import parse_count, parse_time
from event_pipeline.pipeline import convert_source


def record(post_id: str, text: str, when: str, *, view: str = "1.2K") -> dict:
    return {
        "nickname": "example",
        "user_id": "user-1",
        "post_time": when,
        "ip_location": "",
        "hash_tag": ["Event"],
        "post_text": text,
        "reply_count": 1,
        "retweet_count": 2,
        "like_count": 3,
        "quote_count": 4,
        "view": view,
        "lang": "en",
        "post_url": f"https://x.com/example/status/{post_id}",
        "emojis": [],
    }


class NormalizationTests(unittest.TestCase):
    def test_compact_counts(self) -> None:
        self.assertEqual(parse_count("1.2K"), (1200, None))
        self.assertEqual(parse_count("2M"), (2_000_000, None))
        self.assertEqual(parse_count(""), (None, None))

    def test_time_is_utc(self) -> None:
        self.assertEqual(parse_time("2026-06-01T12:30:00.000Z")[0], "2026-06-01T12:30:00Z")


class Data9PipelineTests(unittest.TestCase):
    def test_nested_records_are_flattened_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "sample.zip"
            payload = record("100", "Root post", "2026-06-01T00:00:00.000Z")
            payload["replies"] = [record("101", "Reply", "2026-06-01T01:00:00.000Z")]
            payload["quotes"] = [record("102", "Quote", "2026-06-01T02:00:00.000Z")]
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("data9/TestEvent/tweet/100.json", json.dumps(payload))
                archive.writestr("data9/TestEvent/tweet/duplicate.json", json.dumps(payload))

            report = convert_source(Data9ZipAdapter(), archive_path, root / "unified")
            totals = report["totals"]
            self.assertEqual(totals["input_records"], 6)
            self.assertEqual(totals["accepted_posts"], 3)
            self.assertEqual(totals["duplicate_posts"], 3)
            self.assertEqual(totals["accepted_interactions"], 2)

            posts = (root / "unified" / "TestEvent" / "posts.jsonl").read_text(encoding="utf-8").splitlines()
            edges = (root / "unified" / "TestEvent" / "interactions.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(posts), 3)
            self.assertEqual(len(edges), 2)
            parsed = [json.loads(line) for line in posts]
            self.assertEqual({row["content_type"] for row in parsed}, {"root", "reply", "quote"})
            self.assertEqual(parsed[0]["view_count"], 1200)


if __name__ == "__main__":
    unittest.main()

