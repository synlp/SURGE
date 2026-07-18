from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


GRANULARITIES = {"6H": 6, "12H": 12, "1D": 24}


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def floor_bin(instant: datetime, granularity: str) -> datetime:
    hours = GRANULARITIES[granularity]
    instant = instant.astimezone(timezone.utc)
    floored_hour = (instant.hour // hours) * hours
    return instant.replace(hour=floored_hour, minute=0, second=0, microsecond=0)


def iter_bins(start: datetime, end: datetime, granularity: str):
    step = timedelta(hours=GRANULARITIES[granularity])
    cursor = floor_bin(start, granularity)
    while cursor < end:
        yield cursor
        cursor += step


def _fill_segment(values: list[int | None]) -> list[float]:
    if not values:
        return []
    first_value = next((float(value) for value in values if value is not None), 0.0)
    filled: list[float] = []
    current = first_value
    for value in values:
        if value is not None:
            current = float(value)
        filled.append(current)
    return filled


def normalization_stats(values: list[int | None]) -> dict:
    train_end = int(len(values) * 0.7)
    train = _fill_segment(values[:train_end])
    if not train:
        return {"mean": 0.0, "std": 1.0, "n_train": 0, "std_was_zero": True}
    mean = sum(train) / len(train)
    variance = sum((value - mean) ** 2 for value in train) / len(train)
    raw_std = math.sqrt(variance)
    return {
        "mean": mean,
        "std": raw_std if raw_std > 0 else 1.0,
        "n_train": len(train),
        "std_was_zero": raw_std == 0,
    }


def write_series(path: Path, timestamps: list[datetime], values: list[float | int | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "count"])
        for instant, value in zip(timestamps, values):
            writer.writerow([
                instant.strftime("%Y-%m-%d %H:%M:%S"),
                "" if value is None else value,
            ])


def build_event_series(
    event_dir: Path,
    output_root: Path,
    start: str,
    end: str,
    granularities: tuple[str, ...] = ("6H", "12H", "1D"),
) -> dict:
    start_time = parse_utc(start)
    end_time = parse_utc(end)
    if start_time >= end_time:
        raise ValueError("start must be before end")

    post_times: list[datetime] = []
    with (event_dir / "posts.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            post = json.loads(line)
            raw_time = str(post.get("post_time") or "")
            if not raw_time:
                continue
            instant = parse_utc(raw_time)
            if start_time <= instant < end_time:
                post_times.append(instant)

    outputs = {}
    for granularity in granularities:
        counts: Counter[datetime] = Counter(floor_bin(instant, granularity) for instant in post_times)
        timestamps = list(iter_bins(start_time, end_time, granularity))
        raw_values: list[int | None] = [counts.get(timestamp) or None for timestamp in timestamps]
        stats = normalization_stats(raw_values)
        normalized = [
            None if value is None else (value - stats["mean"]) / stats["std"]
            for value in raw_values
        ]
        target_dir = output_root / f"{event_dir.name}_{granularity}"
        write_series(target_dir / "comment_count.csv", timestamps, raw_values)
        write_series(target_dir / "comment_count_normalized.csv", timestamps, normalized)
        normalization = {
            "event": event_dir.name,
            "granularity": granularity,
            "split_ratios": {"train": 0.7, "val": 0.1, "test": 0.2},
            "variables": {"comment_count": stats},
        }
        (target_dir / "normalization.json").write_text(
            json.dumps(normalization, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        outputs[granularity] = {
            "bins": len(timestamps),
            "observed_bins": sum(value is not None for value in raw_values),
            "empty_bins": sum(value is None for value in raw_values),
            "post_count": sum(value or 0 for value in raw_values),
        }
    return {
        "event_id": event_dir.name,
        "window": {"start": start, "end": end},
        "posts_in_window": len(post_times),
        "granularities": outputs,
    }


def build_corpus_series(unified_root: Path, output_root: Path, window_report: Path) -> dict:
    windows = json.loads(window_report.read_text(encoding="utf-8"))
    results = []
    for event in windows["events"]:
        if "error" in event:
            continue
        event_id = event["event_id"]
        window = event["recommended_window"]
        results.append(build_event_series(
            unified_root / event_id,
            output_root,
            window["start"],
            window["end"],
        ))
    report = {
        "event_count": len(results),
        "granularities": list(GRANULARITIES),
        "total_posts_in_windows": sum(result["posts_in_window"] for result in results),
        "events": results,
    }
    report_path = output_root.parent.parent / "reports" / "timeseries_export.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SURGE-compatible discussion-intensity time series")
    parser.add_argument("--unified", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_corpus_series(args.unified, args.output, args.windows)
    print(json.dumps({key: value for key, value in report.items() if key != "events"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

