import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.sentiment_partition import partition_annotations


def input_row(event: str, post: str) -> dict:
    return {"event_id": event, "post_id": post}


def annotation(event: str, post: str) -> dict:
    return {
        "post_id": post,
        "event_id": event,
        "platform": "twitter",
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "model_name": "model",
        "model_version": "version",
        "prompt_version": "prompt",
        "processed_at": "2026-07-18T00:00:00Z",
        "schema_version": "1.0.0",
    }


class SentimentPartitionTests(unittest.TestCase):
    def test_partition_is_complete_and_disjoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annotations = root / "annotations"
            group_a = root / "input-a"
            group_b = root / "input-b"
            for path in (annotations, group_a, group_b):
                path.mkdir()
            (group_a / "posts-00000.jsonl").write_text(json.dumps(input_row("a", "1")) + "\n", encoding="utf-8")
            (group_b / "posts-00000.jsonl").write_text(json.dumps(input_row("b", "2")) + "\n", encoding="utf-8")
            rows = [annotation("b", "2"), annotation("a", "1")]
            (annotations / "worker-0.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            output = root / "split"
            report = partition_annotations(annotations, {"a": group_a, "b": group_b}, output)

            self.assertTrue(report["valid"])
            self.assertEqual(report["annotation_records"], 2)
            self.assertIn('"event_id": "a"', (output / "a" / "worker-0.jsonl").read_text(encoding="utf-8"))
            self.assertIn('"event_id": "b"', (output / "b" / "worker-0.jsonl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
