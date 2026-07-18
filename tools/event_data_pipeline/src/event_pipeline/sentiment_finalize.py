from __future__ import annotations

import argparse
import json
from pathlib import Path

from event_pipeline.sentiment_timeseries import build_sentiment_series, load_annotations


def expected_keys(input_dir: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for path in sorted(input_dir.glob("posts-*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    key = (str(value["event_id"]), str(value["post_id"]))
                    if key in keys:
                        raise ValueError(f"duplicate input key: {key}")
                    keys.add(key)
    return keys


def finalize(unified: Path, release: Path, windows: Path, input_dir: Path, annotations: Path) -> dict:
    expected = expected_keys(input_dir)
    actual = set(load_annotations(annotations))
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise ValueError(f"annotation coverage mismatch: missing={len(missing)}, extra={len(extra)}; release was not modified")
    return build_sentiment_series(unified, release, windows, annotations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely finalize a complete sentiment batch")
    parser.add_argument("--unified", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    args = parser.parse_args(argv)
    report = finalize(args.unified, args.release, args.windows, args.input, args.annotations)
    print(json.dumps({key: value for key, value in report.items() if key != "events"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
