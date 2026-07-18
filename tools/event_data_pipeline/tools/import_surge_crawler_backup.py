from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def import_backup(backup: Path, destination: Path, target_posts: int = 50_000) -> dict:
    unified_root = destination / "unified"
    reports_root = destination / "reports"
    if unified_root.exists() and any(unified_root.iterdir()):
        raise ValueError(f"processing destination is not empty: {unified_root}")
    unified_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)
    index = json.loads((backup / "backup_index.json").read_text(encoding="utf-8"))
    events = []
    source_catalog = []
    for record in sorted(index["events"], key=lambda item: item["event_id"]):
        event_id = record["event_id"]
        snapshot = backup / record["relative_path"]
        manifest = json.loads((snapshot / "collection_manifest.json").read_text(encoding="utf-8"))
        source_unified = snapshot / "unified" / event_id
        target_unified = unified_root / event_id
        shutil.copytree(source_unified, target_unified, copy_function=shutil.copy2)

        start = parse_time(manifest["since"] + "T00:00:00Z")
        end = parse_time(manifest["until"] + "T00:00:00Z")
        day_counts: Counter[str] = Counter()
        content_types: Counter[str] = Counter()
        first = None
        last = None
        in_window = 0
        with (target_unified / "posts.jsonl").open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                post = json.loads(line)
                instant = parse_time(post["post_time"])
                first = instant if first is None or instant < first else first
                last = instant if last is None or instant > last else last
                content_types[str(post.get("content_type") or "unknown")] += 1
                if start <= instant < end:
                    in_window += 1
                    day_counts[instant.date().isoformat()] += 1
        peak_day, peak_count = max(day_counts.items(), key=lambda item: item[1]) if day_counts else ("", 0)
        total = sum(content_types.values())
        selected = {
            "days": (end - start).days,
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "post_count": in_window,
            "retained_fraction": in_window / total if total else 0,
            "source": "crawler_catalog",
        }
        events.append({
            "event_id": event_id,
            "total_posts": total,
            "content_types": dict(content_types),
            "first_time": first.isoformat().replace("+00:00", "Z") if first else "",
            "last_time": last.isoformat().replace("+00:00", "Z") if last else "",
            "calendar_days": (last.date() - first.date()).days + 1 if first and last else 0,
            "active_days": len(day_counts),
            "peak_day": peak_day,
            "peak_day_posts": peak_count,
            "windows": {"28": selected},
            "recommended_window": selected,
            "target_posts": target_posts,
            "meets_target_full": total >= target_posts,
            "meets_target_28d": in_window >= target_posts,
            "target_gap_28d": max(0, target_posts - in_window),
        })
        source_catalog.append({
            "event_id": event_id,
            "display_name": manifest["display_name"],
            "source_category": manifest["category"],
            "platform": manifest["platform"],
            "since": manifest["since"],
            "until": manifest["until"],
            "snapshot": record["snapshot"],
            "plane": record["plane"],
        })
    report = {
        "event_count": len(events),
        "target_posts": target_posts,
        "events_meeting_target_full": sum(item["meets_target_full"] for item in events),
        "events_meeting_target_28d": sum(item["meets_target_28d"] for item in events),
        "total_posts": sum(item["total_posts"] for item in events),
        "total_posts_in_selected_windows": sum(item["recommended_window"]["post_count"] for item in events),
        "window_policy": "crawler catalog [since, until), UTC",
        "events": events,
    }
    (reports_root / "event_window_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "source_event_catalog.json").write_text(json.dumps({"events": source_catalog}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Import verified crawler backup Unified snapshots")
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--target-posts", type=int, default=50_000)
    args = parser.parse_args()
    result = import_backup(args.backup, args.destination, args.target_posts)
    print(json.dumps({key: value for key, value in result.items() if key != "events"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
