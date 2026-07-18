from __future__ import annotations

import argparse
import json
from pathlib import Path

from event_pipeline.timeseries import parse_utc


def _write_jsonl(handle, value: dict) -> None:
    handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def export_event_graph(event_dir: Path, output_root: Path, start: str, end: str) -> dict:
    start_time = parse_utc(start)
    end_time = parse_utc(end)
    accepted_ids: set[str] = set()
    output_event_dir = output_root / event_dir.name
    output_event_dir.mkdir(parents=True, exist_ok=True)

    lookup_count = 0
    with (
        (event_dir / "posts.jsonl").open("r", encoding="utf-8") as source,
        (output_event_dir / "post_id_lookup.jsonl").open("w", encoding="utf-8") as target,
    ):
        for line in source:
            if not line.strip():
                continue
            post = json.loads(line)
            raw_time = str(post.get("post_time") or "")
            if not raw_time:
                continue
            instant = parse_utc(raw_time)
            if not start_time <= instant < end_time:
                continue
            post_id = str(post["post_id"])
            accepted_ids.add(post_id)
            _write_jsonl(target, {
                "post_id": post_id,
                "platform": post.get("platform", ""),
                "url": post.get("post_url", ""),
            })
            lookup_count += 1

    edge_count = 0
    dropped_edges = 0
    with (
        (event_dir / "interactions.jsonl").open("r", encoding="utf-8") as source,
        (output_event_dir / "edges.jsonl").open("w", encoding="utf-8") as target,
    ):
        for line in source:
            if not line.strip():
                continue
            edge = json.loads(line)
            source_id = str(edge.get("source_post_id") or "")
            target_id = str(edge.get("target_post_id") or "")
            source_time_raw = str(edge.get("source_time") or "")
            if not source_time_raw:
                dropped_edges += 1
                continue
            source_time = parse_utc(source_time_raw)
            if (
                source_id not in accepted_ids
                or target_id not in accepted_ids
                or not start_time <= source_time < end_time
            ):
                dropped_edges += 1
                continue
            _write_jsonl(target, {
                "event": event_dir.name,
                "edge_type": edge.get("interaction_type", ""),
                "source_post_id": source_id,
                "target_post_id": target_id,
                "source_time": edge.get("source_time", ""),
                "target_time": edge.get("target_time", ""),
                "platform": edge.get("platform", ""),
            })
            edge_count += 1

    return {
        "event_id": event_dir.name,
        "window": {"start": start, "end": end},
        "lookup_posts": lookup_count,
        "exported_edges": edge_count,
        "dropped_edges": dropped_edges,
    }


def export_corpus_graphs(unified_root: Path, output_root: Path, window_report: Path) -> dict:
    windows = json.loads(window_report.read_text(encoding="utf-8"))
    results = []
    for event in windows["events"]:
        if "error" in event:
            continue
        window = event["recommended_window"]
        results.append(export_event_graph(
            unified_root / event["event_id"],
            output_root,
            window["start"],
            window["end"],
        ))
    report = {
        "event_count": len(results),
        "lookup_posts": sum(item["lookup_posts"] for item in results),
        "exported_edges": sum(item["exported_edges"] for item in results),
        "dropped_edges": sum(item["dropped_edges"] for item in results),
        "events": results,
    }
    report_path = output_root.parent.parent / "reports" / "surge_graph_export.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export anonymized SURGE-compatible lookup and edge files")
    parser.add_argument("--unified", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = export_corpus_graphs(args.unified, args.output, args.windows)
    print(json.dumps({key: value for key, value in report.items() if key != "events"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

