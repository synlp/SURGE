from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable


POST_REQUIRED = {
    "schema_version",
    "post_id",
    "external_id",
    "platform",
    "event_id",
    "content_type",
    "text",
    "post_time",
    "source_adapter",
    "source_file",
    "source_record_id",
    "content_hash",
}

EDGE_REQUIRED = {
    "schema_version",
    "edge_id",
    "event_id",
    "platform",
    "interaction_type",
    "source_post_id",
    "target_post_id",
    "source_time",
    "target_time",
}


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record is not an object")
            yield line_number, value


def validate_event(event_dir: Path) -> dict:
    event_id = event_dir.name
    errors: list[str] = []
    warnings: list[str] = []
    post_ids: set[str] = set()
    edge_ids: set[str] = set()
    content_types: Counter = Counter()
    interaction_types: Counter = Counter()

    posts_path = event_dir / "posts.jsonl"
    edges_path = event_dir / "interactions.jsonl"
    if not posts_path.exists():
        errors.append("missing posts.jsonl")
    else:
        try:
            for line_number, post in iter_jsonl(posts_path):
                missing = POST_REQUIRED - post.keys()
                if missing:
                    errors.append(f"posts.jsonl:{line_number}: missing {sorted(missing)}")
                post_id = str(post.get("post_id") or "")
                if not post_id:
                    errors.append(f"posts.jsonl:{line_number}: blank post_id")
                elif post_id in post_ids:
                    errors.append(f"posts.jsonl:{line_number}: duplicate post_id {post_id}")
                post_ids.add(post_id)
                if post.get("event_id") != event_id:
                    errors.append(f"posts.jsonl:{line_number}: event_id mismatch")
                content_types[str(post.get("content_type") or "missing")] += 1
                if not str(post.get("text") or "").strip():
                    errors.append(f"posts.jsonl:{line_number}: blank text")
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))

    if not edges_path.exists():
        errors.append("missing interactions.jsonl")
    else:
        try:
            for line_number, edge in iter_jsonl(edges_path):
                missing = EDGE_REQUIRED - edge.keys()
                if missing:
                    errors.append(f"interactions.jsonl:{line_number}: missing {sorted(missing)}")
                edge_id = str(edge.get("edge_id") or "")
                if edge_id in edge_ids:
                    errors.append(f"interactions.jsonl:{line_number}: duplicate edge_id {edge_id}")
                edge_ids.add(edge_id)
                if edge.get("event_id") != event_id:
                    errors.append(f"interactions.jsonl:{line_number}: event_id mismatch")
                source = str(edge.get("source_post_id") or "")
                target = str(edge.get("target_post_id") or "")
                if source not in post_ids:
                    errors.append(f"interactions.jsonl:{line_number}: missing source post {source}")
                if target not in post_ids:
                    errors.append(f"interactions.jsonl:{line_number}: missing target post {target}")
                if source == target:
                    errors.append(f"interactions.jsonl:{line_number}: self edge")
                interaction_types[str(edge.get("interaction_type") or "missing")] += 1
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))

    if not post_ids:
        warnings.append("event contains no accepted posts")
    return {
        "event_id": event_id,
        "valid": not errors,
        "post_count": len(post_ids),
        "edge_count": len(edge_ids),
        "content_types": dict(content_types),
        "interaction_types": dict(interaction_types),
        "errors": errors,
        "warnings": warnings,
    }


def validate_unified(root: Path) -> dict:
    events = []
    if root.exists():
        for event_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            events.append(validate_event(event_dir))
    error_count = sum(len(event["errors"]) for event in events)
    return {
        "valid": bool(events) and error_count == 0,
        "event_count": len(events),
        "post_count": sum(event["post_count"] for event in events),
        "edge_count": sum(event["edge_count"] for event in events),
        "error_count": error_count,
        "events": events,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Unified event JSONL outputs")
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = validate_unified(args.root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

