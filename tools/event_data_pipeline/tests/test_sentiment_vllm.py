import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.sentiment_vllm import iter_records, load_completed, normalize_label


class SentimentVllmTests(unittest.TestCase):
    def test_normalize_label(self):
        self.assertEqual(normalize_label(" Positive "), "positive")
        self.assertEqual(normalize_label("label: negative"), "negative")
        self.assertIsNone(normalize_label("unknown"))

    def test_partition_and_limit_are_global(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "posts-00000.jsonl"
            rows = [{"post_id": str(index)} for index in range(7)]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            selected = list(iter_records([path], worker_index=1, worker_count=3, limit=5))
            self.assertEqual([row["post_id"] for row in selected], ["1", "4"])

    def test_load_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            path.write_text(json.dumps({"event_id": "e", "post_id": "p"}) + "\n", encoding="utf-8")
            self.assertEqual(load_completed(path), {("e", "p")})


if __name__ == "__main__":
    unittest.main()
