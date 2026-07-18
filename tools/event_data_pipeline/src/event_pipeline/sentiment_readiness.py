from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from event_pipeline.validate_release import validate_release

FIELDS = {"post_id", "event_id", "platform", "text", "lang", "post_time"}
CATEGORIES = {"natural_disaster", "political", "social_movement", "technology", "sports_entertainment"}
GRANULARITIES = ["6H", "12H", "1D"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(release: Path, windows_path: Path, catalog_path: Path, input_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    base = validate_release(release)
    errors.extend(f"release: {item}" for item in base["errors"])
    windows = json.loads(windows_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    by_window = {item["event_id"]: item for item in windows["events"] if "error" not in item}
    by_catalog = {item["event_id"]: item for item in catalog["events"]}
    if set(by_window) != set(by_catalog):
        errors.append("catalog and window event sets differ")
    if set(manifest.get("event_counts", {})) != set(by_window):
        errors.append("manifest and window event sets differ")

    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for shard in manifest.get("shards", []):
        path = input_dir / shard["file"]
        if not path.exists():
            errors.append(f"missing shard: {shard['file']}")
            continue
        if path.stat().st_size != shard["bytes"] or sha256(path) != shard["sha256"]:
            errors.append(f"hash/size mismatch: {shard['file']}")
        rows = 0
        with path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                rows += 1
                value = json.loads(line)
                if set(value) != FIELDS:
                    errors.append(f"{shard['file']}:{number}: unexpected fields")
                key = (str(value.get("event_id", "")), str(value.get("post_id", "")))
                if key in seen:
                    errors.append(f"{shard['file']}:{number}: duplicate event/post key")
                seen.add(key)
                counts[key[0]] = counts.get(key[0], 0) + 1
        if rows != shard["records"]:
            errors.append(f"record count mismatch: {shard['file']}")
    if len(seen) != manifest.get("total_records"):
        errors.append("manifest total does not match unique records")
    if counts != manifest.get("event_counts"):
        errors.append("manifest event counts do not match shards")

    metadata_events = []
    for event_id, item in sorted(by_window.items()):
        info = by_catalog[event_id]
        if info["category"] not in CATEGORIES:
            errors.append(f"invalid category: {event_id}")
        window = item["recommended_window"]
        if window["post_count"] < 10000:
            warnings.append(f"{event_id}: selected window has {window['post_count']} posts (<10000)")
        note = "Automatic densest 28-day active period; semantic review recommended."
        if info.get("notes"):
            note += " " + info["notes"]
        metadata_events.append({
            "name": event_id,
            "display_name": info["display_name"],
            "category": info["category"],
            "start_time": window["start"].replace("Z", ""),
            "end_time": window["end"].replace("Z", ""),
            "available_granularities": GRANULARITIES,
            "notes": note,
        })
    metadata = {"events": metadata_events, "note": "Independent data9 release; category mappings and automatic windows should receive editorial review."}
    metadata_path = release / "event_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    missing_series = sum(
        not (release / f"{event_id}_{granularity}" / filename).exists()
        for event_id in by_window for granularity in GRANULARITIES
        for filename in ("sentiment_polarity.csv", "sentiment_polarity_normalized.csv")
    )
    return {
        "ready_for_sentiment_annotation": not errors,
        "pipeline_blockers_before_sentiment": errors,
        "only_unproduced_processing_stage": "sentiment annotation and deterministic aggregation" if not errors else None,
        "sentiment_input_records": len(seen),
        "sentiment_input_shards": len(manifest.get("shards", [])),
        "event_count": len(metadata_events),
        "event_granularity_count": len(metadata_events) * 3,
        "missing_sentiment_series_files_expected_before_labeling": missing_series,
        "non_sentiment_release": base,
        "privacy_minimized_input_fields": sorted(FIELDS),
        "research_quality_warnings": warnings,
        "editorial_review_status": catalog.get("category_status"),
        "metadata_path": str(metadata_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    result = audit(args.release, args.windows, args.catalog, args.input)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_sentiment_annotation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
