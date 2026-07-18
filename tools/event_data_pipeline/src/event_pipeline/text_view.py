from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from event_pipeline.timeseries import GRANULARITIES, floor_bin, iter_bins, parse_utc


def export_event_text_views(event_dir: Path, output_root: Path, start: str, end: str) -> dict:
    start_time = parse_utc(start)
    end_time = parse_utc(end)
    posts: list[dict] = []
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
                post["_instant"] = instant
                posts.append(post)

    outputs = {}
    for granularity in GRANULARITIES:
        posts_by_bin: dict[datetime, list[dict]] = defaultdict(list)
        roots_by_bin: dict[datetime, list[dict]] = defaultdict(list)
        replies_by_bin_parent: dict[tuple[datetime, str], list[dict]] = defaultdict(list)
        for post in posts:
            bin_start = floor_bin(post["_instant"], granularity)
            posts_by_bin[bin_start].append(post)
            if post.get("content_type") == "root":
                roots_by_bin[bin_start].append(post)
            elif post.get("content_type") == "reply" and post.get("parent_id"):
                replies_by_bin_parent[(bin_start, str(post["parent_id"]))].append(post)

        target_dir = output_root / f"{event_dir.name}_{granularity}"
        target_dir.mkdir(parents=True, exist_ok=True)
        step = timedelta(hours=GRANULARITIES[granularity])
        bin_count = 0
        selected_main = 0
        selected_replies = 0
        with (target_dir / "text_view.jsonl").open("w", encoding="utf-8") as target:
            for bin_start in iter_bins(start_time, end_time, granularity):
                bin_posts = sorted(
                    posts_by_bin.get(bin_start, []),
                    key=lambda post: (post["_instant"], post["post_id"]),
                )
                roots = roots_by_bin.get(bin_start, [])
                if roots:
                    ranked = sorted(
                        roots,
                        key=lambda post: (
                            -len(replies_by_bin_parent.get((bin_start, str(post["post_id"])), [])),
                            post["_instant"],
                            post["post_id"],
                        ),
                    )[:3]
                else:
                    ranked = bin_posts[:3]

                main_posts = []
                for main in ranked:
                    replies = sorted(
                        replies_by_bin_parent.get((bin_start, str(main["post_id"])), []),
                        key=lambda post: (post["_instant"], post["post_id"]),
                    )[:2]
                    main_posts.append({
                        "post_id": main["post_id"],
                        "replies": [{"post_id": reply["post_id"]} for reply in replies],
                    })
                    selected_replies += len(replies)
                selected_main += len(main_posts)
                record = {
                    "event": event_dir.name,
                    "granularity": granularity,
                    "bin_start": bin_start.isoformat().replace("+00:00", "Z"),
                    "bin_end": (bin_start + step).isoformat().replace("+00:00", "Z"),
                    "n_posts_in_bin": len(bin_posts),
                    "main_posts": main_posts,
                }
                target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                bin_count += 1
        outputs[granularity] = {
            "bins": bin_count,
            "selected_main_posts": selected_main,
            "selected_replies": selected_replies,
        }
    return {
        "event_id": event_dir.name,
        "posts_in_window": len(posts),
        "granularities": outputs,
    }


def export_corpus_text_views(unified_root: Path, output_root: Path, window_report: Path) -> dict:
    windows = json.loads(window_report.read_text(encoding="utf-8"))
    results = []
    for event in windows["events"]:
        if "error" in event:
            continue
        window = event["recommended_window"]
        results.append(export_event_text_views(
            unified_root / event["event_id"], output_root,
            window["start"], window["end"],
        ))
    report = {
        "event_count": len(results),
        "posts_in_windows": sum(item["posts_in_window"] for item in results),
        "selected_main_posts": sum(
            data["selected_main_posts"] for item in results for data in item["granularities"].values()
        ),
        "selected_replies": sum(
            data["selected_replies"] for item in results for data in item["granularities"].values()
        ),
        "events": results,
    }
    report_path = output_root.parent.parent / "reports" / "text_view_export.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SURGE-compatible sampled per-bin post/reply views")
    parser.add_argument("--unified", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = export_corpus_text_views(args.unified, args.output, args.windows)
    print(json.dumps({key: value for key, value in report.items() if key != "events"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

