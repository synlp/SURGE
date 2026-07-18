from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from event_pipeline.window_analysis import analyze_corpus, analyze_event


class WindowAnalysisTests(unittest.TestCase):
    def test_densest_window_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_dir = Path(directory) / "Event"
            event_dir.mkdir()
            path = event_dir / "posts.jsonl"
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            rows = []
            for day in range(40):
                count = 10 if 10 <= day < 38 else 1
                for index in range(count):
                    rows.append({
                        "post_time": (start + timedelta(days=day, seconds=index)).isoformat().replace("+00:00", "Z"),
                        "content_type": "root",
                    })
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            result = analyze_event(event_dir, target_posts=200)
            self.assertEqual(result["recommended_window"]["post_count"], 280)
            self.assertTrue(result["meets_target_28d"])
            self.assertEqual(result["calendar_days"], 40)

    def test_corpus_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            event_dir = Path(directory) / "Event"
            event_dir.mkdir()
            (event_dir / "posts.jsonl").write_text(
                json.dumps({"post_time": "2026-01-01T00:00:00Z", "content_type": "reply"}) + "\n",
                encoding="utf-8",
            )
            report = analyze_corpus(Path(directory), target_posts=1)
            self.assertEqual(report["event_count"], 1)
            self.assertEqual(report["events_meeting_target_full"], 1)


if __name__ == "__main__":
    unittest.main()

