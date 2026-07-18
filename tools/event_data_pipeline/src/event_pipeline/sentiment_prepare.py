from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from event_pipeline.timeseries import parse_utc


ALLOWED_FIELDS = ("post_id", "event_id", "platform", "text", "lang", "post_time")


def prepare_sentiment_input(
    unified_root: Path,
    window_report: Path,
    output_dir: Path,
    *,
    shard_size: int = 10_000,
) -> dict:
    windows = json.loads(window_report.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    shard_index = 0
    shard_count = 0
    shard_handle = None
    shard_path = None
    shard_hash = hashlib.sha256()
    shard_meta: list[dict] = []
    total = 0
    events: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()

    def close_shard() -> None:
        nonlocal shard_handle, shard_count, shard_hash, shard_path
        if shard_handle is None or shard_path is None:
            return
        shard_handle.close()
        shard_meta.append({
            "file": shard_path.name,
            "records": shard_count,
            "bytes": shard_path.stat().st_size,
            "sha256": shard_hash.hexdigest(),
        })
        shard_handle = None
        shard_count = 0
        shard_hash = hashlib.sha256()
        shard_path = None

    def write_record(record: dict) -> None:
        nonlocal shard_handle, shard_index, shard_count, shard_path
        if shard_handle is None:
            shard_path = output_dir / f"posts-{shard_index:05d}.jsonl"
            shard_handle = shard_path.open("w", encoding="utf-8")
            shard_index += 1
        rendered = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        shard_handle.write(rendered)
        shard_hash.update(rendered.encode("utf-8"))
        shard_count += 1
        if shard_count >= shard_size:
            close_shard()

    try:
        for event in windows["events"]:
            if "error" in event:
                continue
            event_id = event["event_id"]
            start = parse_utc(event["recommended_window"]["start"])
            end = parse_utc(event["recommended_window"]["end"])
            with (unified_root / event_id / "posts.jsonl").open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    post = json.loads(line)
                    raw_time = str(post.get("post_time") or "")
                    if not raw_time:
                        continue
                    instant = parse_utc(raw_time)
                    if not start <= instant < end:
                        continue
                    key = (event_id, str(post["post_id"]))
                    if key in seen:
                        raise ValueError(f"duplicate event/post key: {key}")
                    seen.add(key)
                    record = {field: post.get(field, "") for field in ALLOWED_FIELDS}
                    if set(record) != set(ALLOWED_FIELDS):
                        raise AssertionError("sentiment input field leak")
                    write_record(record)
                    total += 1
                    events[event_id] += 1
                    languages[str(post.get("lang") or "missing")] += 1
    finally:
        close_shard()

    manifest = {
        "schema_version": "1.0.0",
        "purpose": "post-level three-class sentiment annotation",
        "label_contract": {"negative": -1, "neutral": 0, "positive": 1},
        "required_output_fields": [
            "post_id", "event_id", "platform", "sentiment", "sentiment_score",
            "model_name", "model_version", "prompt_version", "processed_at", "schema_version",
        ],
        "input_fields": list(ALLOWED_FIELDS),
        "contains_user_id": False,
        "contains_nickname": False,
        "contains_location": False,
        "total_records": total,
        "event_count": len(events),
        "event_counts": dict(sorted(events.items())),
        "language_counts": dict(languages.most_common()),
        "shard_size": shard_size,
        "shards": shard_meta,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare privacy-minimized sharded sentiment input")
    parser.add_argument("--unified", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shard-size", type=int, default=10_000)
    args = parser.parse_args(argv)
    result = prepare_sentiment_input(
        args.unified, args.windows, args.output, shard_size=args.shard_size
    )
    print(json.dumps({
        "total_records": result["total_records"],
        "event_count": result["event_count"],
        "shards": len(result["shards"]),
        "manifest_path": result["manifest_path"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

