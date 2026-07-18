import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from event_pipeline.sentiment_finalize import finalize


class SentimentFinalizeTests(unittest.TestCase):
    def test_incomplete_annotations_do_not_call_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / "input"
            outputs = root / "output"
            inputs.mkdir()
            outputs.mkdir()
            (inputs / "posts-00000.jsonl").write_text(
                json.dumps({"event_id": "event", "post_id": "1"}) + "\n" +
                json.dumps({"event_id": "event", "post_id": "2"}) + "\n",
                encoding="utf-8",
            )
            annotation = {
                "event_id": "event", "post_id": "1", "platform": "x",
                "sentiment": "neutral", "sentiment_score": 0,
                "model_name": "model", "model_version": "v1",
                "prompt_version": "p1", "processed_at": "2026-01-01T00:00:00Z",
                "schema_version": "1.0.0",
            }
            (outputs / "part.jsonl").write_text(json.dumps(annotation) + "\n", encoding="utf-8")
            with patch("event_pipeline.sentiment_finalize.build_sentiment_series") as writer:
                with self.assertRaisesRegex(ValueError, "missing=1"):
                    finalize(root, root, root, inputs, outputs)
                writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
