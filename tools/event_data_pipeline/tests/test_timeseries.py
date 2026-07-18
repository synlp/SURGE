from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.timeseries import build_event_series, normalization_stats


class TimeSeriesTests(unittest.TestCase):
    def test_train_only_normalization(self) -> None:
        stats = normalization_stats([1, None, 3, 100, 100])
        self.assertEqual(stats["n_train"], 3)
        self.assertAlmostEqual(stats["mean"], (1 + 1 + 3) / 3)

    def test_empty_bins_are_blank_and_counts_conserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_dir = root / "Event"
            event_dir.mkdir()
            posts = [
                {"post_time": "2026-01-01T01:00:00Z"},
                {"post_time": "2026-01-01T02:00:00Z"},
                {"post_time": "2026-01-01T13:00:00Z"},
            ]
            (event_dir / "posts.jsonl").write_text(
                "".join(json.dumps(post) + "\n" for post in posts), encoding="utf-8"
            )
            result = build_event_series(
                event_dir, root / "release",
                "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z",
                granularities=("6H",),
            )
            self.assertEqual(result["posts_in_window"], 3)
            self.assertEqual(result["granularities"]["6H"]["bins"], 4)
            self.assertEqual(result["granularities"]["6H"]["empty_bins"], 2)
            with (root / "release" / "Event_6H" / "comment_count.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["count"] for row in rows], ["2", "", "1", ""])


if __name__ == "__main__":
    unittest.main()

