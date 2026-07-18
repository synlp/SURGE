from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from event_pipeline.adapters import Data9ZipAdapter
from event_pipeline.adapters.base import SourceAdapter
from event_pipeline.pipeline import convert_source
from event_pipeline.validate import validate_unified


@dataclass(frozen=True, slots=True)
class EventSpec:
    event_id: str
    start: str | None = None
    end: str | None = None
    enabled: bool = True


def load_event_specs(path: Path) -> list[EventSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    specs: list[EventSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(raw.get("events", [])):
        event_id = str(item.get("event_id") or "").strip()
        if not event_id:
            raise ValueError(f"events[{index}] has no event_id")
        if event_id in seen:
            raise ValueError(f"duplicate event_id in config: {event_id}")
        seen.add(event_id)
        start = item.get("start") or None
        end = item.get("end") or None
        if start and end:
            start_time = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
            if start_time >= end_time:
                raise ValueError(f"invalid window for {event_id}: start must be before end")
        specs.append(EventSpec(event_id, start, end, bool(item.get("enabled", True))))
    if not specs:
        raise ValueError("config contains no events")
    return specs


def run_batch(
    source: Path,
    output_dir: Path,
    specs: list[EventSpec],
    *,
    dedupe_text: bool = False,
    adapter: SourceAdapter | None = None,
) -> dict:
    adapter = adapter or Data9ZipAdapter()
    enabled = [spec for spec in specs if spec.enabled]
    report = convert_source(
        adapter,
        source,
        output_dir,
        selected_events={spec.event_id for spec in enabled},
        dedupe_text=dedupe_text,
        event_windows={spec.event_id: (spec.start, spec.end) for spec in enabled},
    )

    validation = validate_unified(output_dir)
    totals = dict(report["totals"])
    result = {
        "pipeline_version": "0.2.0",
        "processed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_name": source.name,
        "dedupe_text": dedupe_text,
        "totals": totals,
        "event_reports": report["events"],
        "validation": {
            "valid": validation["valid"],
            "event_count": validation["event_count"],
            "post_count": validation["post_count"],
            "edge_count": validation["edge_count"],
            "error_count": validation["error_count"],
        },
    }
    reports_dir = output_dir.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{source.stem}_batch_quality.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["report_path"] = str(report_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run data9 conversion with per-event windows")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dedupe-text", action="store_true")
    args = parser.parse_args(argv)
    result = run_batch(args.input, args.output, load_event_specs(args.config), dedupe_text=args.dedupe_text)
    print(json.dumps({"totals": result["totals"], "validation": result["validation"]}, ensure_ascii=False, indent=2))
    print(f"quality_report={result['report_path']}")
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
