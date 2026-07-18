from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.sentiment import validate_annotation, validate_sentiment_file


class SentimentTests(unittest.TestCase):
    def test_label_score_contract(self) -> None:
        value = {
            "post_id": "p", "event_id": "e", "platform": "twitter",
            "sentiment": "positive", "sentiment_score": 1,
            "model_name": "m", "model_version": "1", "prompt_version": "1",
            "processed_at": "2026-01-01T00:00:00Z", "schema_version": "1.0.0",
        }
        self.assertEqual(validate_annotation(value), [])
        value["sentiment_score"] = -1
        self.assertTrue(validate_annotation(value))

    def test_duplicate_annotations_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sentiments.jsonl"
            value = {
                "post_id": "p", "event_id": "e", "platform": "twitter",
                "sentiment": "neutral", "sentiment_score": 0,
                "model_name": "m", "model_version": "1", "prompt_version": "1",
                "processed_at": "2026-01-01T00:00:00Z", "schema_version": "1.0.0",
            }
            path.write_text(json.dumps(value) + "\n" + json.dumps(value) + "\n", encoding="utf-8")
            self.assertFalse(validate_sentiment_file(path)["valid"])


if __name__ == "__main__":
    unittest.main()

