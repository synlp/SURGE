from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from event_pipeline.sentiment import validate_annotation
from event_pipeline.timeseries import GRANULARITIES, floor_bin, iter_bins, normalization_stats, parse_utc


def _annotation_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(candidate for candidate in path.rglob("*.jsonl") if candidate.is_file())


def load_annotations(path: Path) -> dict[tuple[str, str], float]:
    annotations: dict[tuple[str, str], float] = {}
    for file_path in _annotation_files(path):
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                errors = validate_annotation(value)
                if errors:
                    raise ValueError(f"{file_path}:{line_number}: {'; '.join(errors)}")
                key = (str(value["event_id"]), str(value["post_id"]))
                if key in annotations:
                    raise ValueError(f"duplicate annotation key: {key}")
                annotations[key] = float(value["sentiment_score"])
    return annotations


def _write_polarity(path: Path, timestamps: list, values: list[float | None]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "polarity"])
        for instant, value in zip(timestamps, values):
            writer.writerow([instant.strftime("%Y-%m-%d %H:%M:%S"), "" if value is None else value])


def build_sentiment_series(
    unified_root: Path,
    release_root: Path,
    window_report: Path,
    annotations_path: Path,
) -> dict:
    annotations = load_annotations(annotations_path)
    windows = json.loads(window_report.read_text(encoding="utf-8"))
    used_keys: set[tuple[str, str]] = set()
    results = []
    total_missing = 0

    for event in windows["events"]:
        if "error" in event:
            continue
        event_id = event["event_id"]
        start = parse_utc(event["recommended_window"]["start"])
        end = parse_utc(event["recommended_window"]["end"])
        scored_posts: list[tuple[object, float]] = []
        missing = 0
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
                score = annotations.get(key)
                if score is None:
                    missing += 1
                    continue
                used_keys.add(key)
                scored_posts.append((instant, score))
        total_missing += missing
        event_result = {"event_id": event_id, "required_posts": len(scored_posts) + missing, "scored_posts": len(scored_posts), "missing_posts": missing, "granularities": {}}

        for granularity in GRANULARITIES:
            sums = defaultdict(float)
            counts = defaultdict(int)
            for instant, score in scored_posts:
                bin_start = floor_bin(instant, granularity)
                sums[bin_start] += score
                counts[bin_start] += 1
            timestamps = list(iter_bins(start, end, granularity))
            raw_values = [
                sums[timestamp] / counts[timestamp] if counts[timestamp] else None
                for timestamp in timestamps
            ]
            stats = normalization_stats(raw_values)
            normalized = [
                None if value is None else (value - stats["mean"]) / stats["std"]
                for value in raw_values
            ]
            target_dir = release_root / f"{event_id}_{granularity}"
            target_dir.mkdir(parents=True, exist_ok=True)
            _write_polarity(target_dir / "sentiment_polarity.csv", timestamps, raw_values)
            _write_polarity(target_dir / "sentiment_polarity_normalized.csv", timestamps, normalized)
            normalization_path = target_dir / "normalization.json"
            normalization = json.loads(normalization_path.read_text(encoding="utf-8"))
            normalization.setdefault("variables", {})["sentiment_polarity"] = stats
            normalization_path.write_text(json.dumps(normalization, ensure_ascii=False, indent=2), encoding="utf-8")
            event_result["granularities"][granularity] = {
                "bins": len(timestamps),
                "observed_bins": sum(value is not None for value in raw_values),
                "empty_bins": sum(value is None for value in raw_values),
            }
        results.append(event_result)

    report = {
        "valid": total_missing == 0,
        "annotation_records": len(annotations),
        "used_annotations": len(used_keys),
        "extra_annotations": len(annotations) - len(used_keys),
        "missing_annotations": total_missing,
        "events": results,
    }
    report_path = release_root.parent.parent / "reports" / "sentiment_timeseries_export.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    if total_missing:
        raise ValueError(f"sentiment annotations incomplete: {total_missing} posts are missing; see {report_path}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate validated post sentiment into SURGE time series")
    parser.add_argument("--unified", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_sentiment_series(args.unified, args.release, args.windows, args.annotations)
    print(json.dumps({key: value for key, value in report.items() if key != "events"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

