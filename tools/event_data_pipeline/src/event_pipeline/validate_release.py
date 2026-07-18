from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


GRANULARITY_HOURS = {"6H": 6, "12H": 12, "1D": 24}
FORBIDDEN_IDENTITY_KEYS = {"user_id", "nickname", "username", "author", "author_id", "ip_location"}


def _jsonl_rows(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path.name}:{line_number}: record is not an object")
                yield line_number, value


def _identity_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        found = {str(key) for key in value if str(key).lower() in FORBIDDEN_IDENTITY_KEYS}
        for child in value.values():
            found.update(_identity_keys(child))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found.update(_identity_keys(child))
        return found
    return set()


def _read_csv(path: Path, expected_header: list[str], errors: list[str], prefix: str) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != expected_header:
                errors.append(f"{prefix}: header {reader.fieldnames!r}, expected {expected_header!r}")
            return list(reader)
    except (OSError, csv.Error) as exc:
        errors.append(f"{prefix}: unreadable CSV: {exc}")
        return []


def _timestamps(rows: list[dict], errors: list[str], prefix: str, hours: int) -> list[datetime]:
    values: list[datetime] = []
    for index, row in enumerate(rows, 2):
        try:
            instant = datetime.strptime(str(row.get("time") or ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            errors.append(f"{prefix}:{index}: invalid UTC timestamp")
            continue
        if values and instant - values[-1] != timedelta(hours=hours):
            errors.append(f"{prefix}:{index}: timestamp is not a strict {hours}H continuation")
        values.append(instant)
    return values


def _numeric_column(
    rows: list[dict], column: str, errors: list[str], prefix: str, *, raw_count: bool = False, polarity: bool = False
) -> None:
    for index, row in enumerate(rows, 2):
        raw = str(row.get(column) or "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            errors.append(f"{prefix}:{index}: non-numeric {column}")
            continue
        if not math.isfinite(value):
            errors.append(f"{prefix}:{index}: non-finite {column}")
        if raw_count and (value < 0 or not value.is_integer()):
            errors.append(f"{prefix}:{index}: count must be a non-negative integer")
        if polarity and not -1.0 <= value <= 1.0:
            errors.append(f"{prefix}:{index}: polarity outside [-1, 1]")


def validate_release(root: Path, *, require_sentiment: bool | None = None) -> dict:
    errors: list[str] = []
    if not root.exists():
        return {"valid": False, "event_count": 0, "event_granularity_count": 0, "lookup_posts": 0,
                "edges": 0, "text_view_bins": 0, "error_count": 1, "errors": ["release root does not exist"]}
    event_dirs = sorted(path for path in root.iterdir() if path.is_dir() and not path.name.endswith(tuple(f"_{g}" for g in GRANULARITY_HOURS)))
    granularity_dirs = sorted(path for path in root.iterdir() if path.is_dir() and path.name.endswith(tuple(f"_{g}" for g in GRANULARITY_HOURS)))
    if require_sentiment is None:
        require_sentiment = any((path / "sentiment_polarity.csv").exists() for path in granularity_dirs)
    lookup_ids: dict[str, set[str]] = {}
    total_lookup = total_edges = total_text_bins = 0

    for event_dir in event_dirs:
        event_id = event_dir.name
        lookup_path, edge_path = event_dir / "post_id_lookup.jsonl", event_dir / "edges.jsonl"
        if not lookup_path.exists() or not edge_path.exists():
            errors.append(f"{event_id}: missing lookup or edges file")
            continue
        ids: set[str] = set()
        try:
            for line_number, row in _jsonl_rows(lookup_path):
                post_id = str(row.get("post_id") or "")
                if not post_id or post_id in ids:
                    errors.append(f"{event_id}/post_id_lookup.jsonl:{line_number}: blank or duplicate post_id")
                forbidden = _identity_keys(row)
                if forbidden:
                    errors.append(f"{event_id}/post_id_lookup.jsonl:{line_number}: forbidden identity keys {sorted(forbidden)}")
                ids.add(post_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{event_id}/post_id_lookup.jsonl: {exc}")
        lookup_ids[event_id] = ids
        total_lookup += len(ids)
        edge_ids: set[tuple[str, str, str]] = set()
        try:
            for line_number, edge in _jsonl_rows(edge_path):
                source, target = str(edge.get("source_post_id") or ""), str(edge.get("target_post_id") or "")
                key = (str(edge.get("edge_type") or ""), source, target)
                if not key[0] or source not in ids or target not in ids or source == target:
                    errors.append(f"{event_id}/edges.jsonl:{line_number}: invalid type or endpoint")
                if key in edge_ids:
                    errors.append(f"{event_id}/edges.jsonl:{line_number}: duplicate edge")
                forbidden = _identity_keys(edge)
                if forbidden:
                    errors.append(f"{event_id}/edges.jsonl:{line_number}: forbidden identity keys {sorted(forbidden)}")
                edge_ids.add(key)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{event_id}/edges.jsonl: {exc}")
        total_edges += len(edge_ids)

    expected_gran_dirs = {f"{event.name}_{gran}" for event in event_dirs for gran in GRANULARITY_HOURS}
    actual_gran_dirs = {path.name for path in granularity_dirs}
    for missing in sorted(expected_gran_dirs - actual_gran_dirs):
        errors.append(f"{missing}: missing granularity directory")
    for orphan in sorted(actual_gran_dirs - expected_gran_dirs):
        errors.append(f"{orphan}: has no matching event directory")

    for gran_dir in granularity_dirs:
        event_id, granularity = gran_dir.name.rsplit("_", 1)
        required = ["comment_count.csv", "comment_count_normalized.csv", "normalization.json", "text_view.jsonl"]
        if require_sentiment:
            required += ["sentiment_polarity.csv", "sentiment_polarity_normalized.csv"]
        for filename in required:
            if not (gran_dir / filename).exists():
                errors.append(f"{gran_dir.name}: missing {filename}")
        raw_path, normalized_path = gran_dir / "comment_count.csv", gran_dir / "comment_count_normalized.csv"
        if not raw_path.exists() or not normalized_path.exists():
            continue
        raw_rows = _read_csv(raw_path, ["time", "count"], errors, f"{gran_dir.name}/comment_count.csv")
        normalized_rows = _read_csv(normalized_path, ["time", "count"], errors, f"{gran_dir.name}/comment_count_normalized.csv")
        raw_times = _timestamps(raw_rows, errors, f"{gran_dir.name}/comment_count.csv", GRANULARITY_HOURS[granularity])
        normalized_times = _timestamps(normalized_rows, errors, f"{gran_dir.name}/comment_count_normalized.csv", GRANULARITY_HOURS[granularity])
        if raw_times != normalized_times:
            errors.append(f"{gran_dir.name}: raw/normalized count timestamps differ")
        _numeric_column(raw_rows, "count", errors, f"{gran_dir.name}/comment_count.csv", raw_count=True)
        _numeric_column(normalized_rows, "count", errors, f"{gran_dir.name}/comment_count_normalized.csv")

        normalization_path = gran_dir / "normalization.json"
        if normalization_path.exists():
            try:
                normalization = json.loads(normalization_path.read_text(encoding="utf-8"))
                if normalization.get("event") != event_id or normalization.get("granularity") != granularity:
                    errors.append(f"{gran_dir.name}/normalization.json: metadata mismatch")
                ratios = normalization.get("split_ratios", {})
                if set(ratios) != {"train", "val", "test"} or not math.isclose(sum(float(v) for v in ratios.values()), 1.0):
                    errors.append(f"{gran_dir.name}/normalization.json: invalid split ratios")
                variables = normalization.get("variables", {})
                required_variables = {"comment_count"} | ({"sentiment_polarity"} if require_sentiment else set())
                for variable in required_variables:
                    stats = variables.get(variable)
                    if not isinstance(stats, dict) or float(stats.get("std", 0)) <= 0 or int(stats.get("n_train", -1)) != int(len(raw_rows) * 0.7):
                        errors.append(f"{gran_dir.name}/normalization.json: invalid {variable} statistics")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                errors.append(f"{gran_dir.name}/normalization.json: {exc}")

        if require_sentiment and (gran_dir / "sentiment_polarity.csv").exists() and (gran_dir / "sentiment_polarity_normalized.csv").exists():
            sentiment = _read_csv(gran_dir / "sentiment_polarity.csv", ["time", "polarity"], errors, f"{gran_dir.name}/sentiment_polarity.csv")
            sentiment_norm = _read_csv(gran_dir / "sentiment_polarity_normalized.csv", ["time", "polarity"], errors, f"{gran_dir.name}/sentiment_polarity_normalized.csv")
            sentiment_times = _timestamps(sentiment, errors, f"{gran_dir.name}/sentiment_polarity.csv", GRANULARITY_HOURS[granularity])
            sentiment_norm_times = _timestamps(sentiment_norm, errors, f"{gran_dir.name}/sentiment_polarity_normalized.csv", GRANULARITY_HOURS[granularity])
            if sentiment_times != raw_times or sentiment_norm_times != raw_times:
                errors.append(f"{gran_dir.name}: sentiment/count timestamps differ")
            _numeric_column(sentiment, "polarity", errors, f"{gran_dir.name}/sentiment_polarity.csv", polarity=True)
            _numeric_column(sentiment_norm, "polarity", errors, f"{gran_dir.name}/sentiment_polarity_normalized.csv")

        text_path = gran_dir / "text_view.jsonl"
        if text_path.exists():
            ids = lookup_ids.get(event_id, set())
            seen_bins: list[datetime] = []
            try:
                for line_number, record in _jsonl_rows(text_path):
                    if record.get("event") != event_id or record.get("granularity") != granularity:
                        errors.append(f"{gran_dir.name}/text_view.jsonl:{line_number}: metadata mismatch")
                    forbidden = _identity_keys(record)
                    if forbidden:
                        errors.append(f"{gran_dir.name}/text_view.jsonl:{line_number}: forbidden identity keys {sorted(forbidden)}")
                    try:
                        seen_bins.append(datetime.fromisoformat(str(record.get("bin_start") or "").replace("Z", "+00:00")))
                    except ValueError:
                        errors.append(f"{gran_dir.name}/text_view.jsonl:{line_number}: invalid bin_start")
                    if len(record.get("main_posts", [])) > 3:
                        errors.append(f"{gran_dir.name}/text_view.jsonl:{line_number}: too many main posts")
                    for main in record.get("main_posts", []):
                        if main.get("post_id") not in ids or len(main.get("replies", [])) > 2:
                            errors.append(f"{gran_dir.name}/text_view.jsonl:{line_number}: invalid main post or reply count")
                        for reply in main.get("replies", []):
                            if reply.get("post_id") not in ids:
                                errors.append(f"{gran_dir.name}/text_view.jsonl:{line_number}: unresolved reply")
                    total_text_bins += 1
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{gran_dir.name}/text_view.jsonl: {exc}")
            if seen_bins != raw_times:
                errors.append(f"{gran_dir.name}: text-view/count bins differ")

    return {
        "valid": bool(event_dirs) and not errors,
        "sentiment_required": require_sentiment,
        "event_count": len(event_dirs),
        "event_granularity_count": len(granularity_dirs),
        "lookup_posts": total_lookup,
        "edges": total_edges,
        "text_view_bins": total_text_bins,
        "error_count": len(errors),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strictly validate SURGE-compatible derived artifacts")
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path)
    sentiment = parser.add_mutually_exclusive_group()
    sentiment.add_argument("--require-sentiment", action="store_true")
    sentiment.add_argument("--allow-missing-sentiment", action="store_true")
    args = parser.parse_args(argv)
    require = True if args.require_sentiment else False if args.allow_missing_sentiment else None
    report = validate_release(args.root, require_sentiment=require)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
