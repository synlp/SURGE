from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.sentiment_timeseries import build_sentiment_series


def annotation(post_id: str, score: int, label: str) -> dict:
    return {
        "post_id": post_id, "event_id": "Event", "platform": "twitter",
        "sentiment": label, "sentiment_score": score, "model_name": "model",
        "model_version": "1", "prompt_version": "1",
        "processed_at": "2026-01-02T00:00:00Z", "schema_version": "1.0.0",
    }


class SentimentTimeSeriesTests(unittest.TestCase):
    def test_complete_annotations_generate_all_granularities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "unified" / "Event"
            event.mkdir(parents=True)
            posts = [
                {"post_id": "a", "post_time": "2026-01-01T01:00:00Z"},
                {"post_id": "b", "post_time": "2026-01-01T02:00:00Z"},
            ]
            (event / "posts.jsonl").write_text("".join(json.dumps(row) + "\n" for row in posts), encoding="utf-8")
            windows = {"events": [{"event_id": "Event", "recommended_window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}}]}
            window_path = root / "windows.json"
            window_path.write_text(json.dumps(windows), encoding="utf-8")
            release = root / "release"
            for granularity in ("6H", "12H", "1D"):
                target = release / f"Event_{granularity}"
                target.mkdir(parents=True)
                (target / "normalization.json").write_text(json.dumps({"variables": {"comment_count": {}}}), encoding="utf-8")
            labels = root / "labels.jsonl"
            labels.write_text(json.dumps(annotation("a", 1, "positive")) + "\n" + json.dumps(annotation("b", -1, "negative")) + "\n", encoding="utf-8")
            result = build_sentiment_series(root / "unified", release, window_path, labels)
            self.assertTrue(result["valid"])
            self.assertTrue((release / "Event_1D" / "sentiment_polarity.csv").exists())
            normalization = json.loads((release / "Event_1D" / "normalization.json").read_text(encoding="utf-8"))
            self.assertIn("sentiment_polarity", normalization["variables"])

    def test_missing_annotation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = root / "unified" / "Event"
            event.mkdir(parents=True)
            (event / "posts.jsonl").write_text(json.dumps({"post_id": "a", "post_time": "2026-01-01T01:00:00Z"}) + "\n", encoding="utf-8")
            window_path = root / "windows.json"
            window_path.write_text(json.dumps({"events": [{"event_id": "Event", "recommended_window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}}]}), encoding="utf-8")
            labels = root / "labels.jsonl"
            labels.write_text("", encoding="utf-8")
            release = root / "release"
            for granularity in ("6H", "12H", "1D"):
                target = release / f"Event_{granularity}"
                target.mkdir(parents=True)
                (target / "normalization.json").write_text(json.dumps({"variables": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_sentiment_series(root / "unified", release, window_path, labels)


if __name__ == "__main__":
    unittest.main()

