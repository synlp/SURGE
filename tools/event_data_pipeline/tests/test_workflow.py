from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from event_pipeline.validate_release import validate_release
from event_pipeline.workflow import run_release_workflow


class WorkflowTests(unittest.TestCase):
    def test_end_to_end_wait_resume_and_strict_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text("".join(json.dumps(row) + "\n" for row in [
                {"event_id": "Event", "id": "1", "text": "Root", "post_time": "2026-01-01T01:00:00Z"},
                {"event_id": "Event", "id": "2", "text": "Reply", "post_time": "2026-01-01T02:00:00Z", "type": "reply", "parent_id": "1"},
            ]), encoding="utf-8")
            config = root / "events.json"
            config.write_text(json.dumps({"events": [{"event_id": "Event", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}]}), encoding="utf-8")
            run_dir = root / "run"
            first = run_release_workflow(source=source, config=config, run_dir=run_dir, adapter_name="generic-jsonl", adapter_platform="x")
            self.assertEqual(first["status"], "awaiting_sentiment")
            self.assertTrue(validate_release(run_dir / "release/surge/events", require_sentiment=False)["valid"])
            annotations = root / "annotations.jsonl"
            rows = []
            for shard in (run_dir / "sentiment/input").glob("posts-*.jsonl"):
                for line in shard.read_text(encoding="utf-8").splitlines():
                    item = json.loads(line)
                    rows.append({
                        "post_id": item["post_id"], "event_id": item["event_id"], "platform": item["platform"],
                        "sentiment": "neutral", "sentiment_score": 0, "model_name": "test", "model_version": "1",
                        "prompt_version": "1", "processed_at": "2026-01-02T00:00:00Z", "schema_version": "1.0.0",
                    })
            annotations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            final = run_release_workflow(source=source, config=config, run_dir=run_dir, adapter_name="generic-jsonl", adapter_platform="x", annotations=annotations, resume=True)
            self.assertEqual(final["status"], "complete")
            self.assertTrue(final["validation"]["valid"])

            count_path = run_dir / "release/surge/events/Event_6H/comment_count.csv"
            count_path.write_text(count_path.read_text(encoding="utf-8").replace(",2\n", ",-2\n"), encoding="utf-8")
            self.assertFalse(validate_release(run_dir / "release/surge/events", require_sentiment=True)["valid"])

    def test_nonempty_unmanaged_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, config, run_dir = root / "source.jsonl", root / "config.json", root / "run"
            source.write_text("", encoding="utf-8")
            config.write_text(json.dumps({"events": [{"event_id": "E", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}]}), encoding="utf-8")
            run_dir.mkdir()
            (run_dir / "keep.txt").write_text("do not overwrite", encoding="utf-8")
            with self.assertRaises(ValueError):
                run_release_workflow(source=source, config=config, run_dir=run_dir, adapter_name="generic-jsonl")


if __name__ == "__main__":
    unittest.main()
