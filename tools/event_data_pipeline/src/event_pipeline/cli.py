from __future__ import annotations

import argparse
import json
from pathlib import Path

from event_pipeline.adapters import ADAPTER_NAMES, create_adapter
from event_pipeline.pipeline import convert_source
from event_pipeline.workflow import run_release_workflow


def _add_convert_arguments(parser: argparse.ArgumentParser, *, adapter: bool) -> None:
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    if adapter:
        parser.add_argument("--adapter", choices=ADAPTER_NAMES, required=True)
        parser.add_argument("--platform", help="Platform name for generic-jsonl")
    parser.add_argument("--event", action="append", dest="events")
    parser.add_argument("--start", help="Inclusive ISO-8601 UTC timestamp")
    parser.add_argument("--end", help="Exclusive ISO-8601 UTC timestamp")
    parser.add_argument("--dedupe-text", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="event-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    convert = subparsers.add_parser("convert", help="Convert one supported source to the unified layer")
    _add_convert_arguments(convert, adapter=True)
    legacy = subparsers.add_parser("convert-data9", help="Backward-compatible data9 conversion")
    _add_convert_arguments(legacy, adapter=False)

    workflow = subparsers.add_parser("run-release", help="Run or resume an isolated end-to-end SURGE release")
    workflow.add_argument("--input", required=True, type=Path)
    workflow.add_argument("--config", required=True, type=Path)
    workflow.add_argument("--run-dir", required=True, type=Path)
    workflow.add_argument("--adapter", choices=ADAPTER_NAMES, required=True)
    workflow.add_argument("--platform", help="Platform name for generic-jsonl")
    workflow.add_argument("--dedupe-text", action="store_true")
    workflow.add_argument("--annotations", type=Path)
    workflow.add_argument("--resume", action="store_true")
    workflow.add_argument("--shard-size", type=int, default=10_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"convert", "convert-data9"}:
        adapter_name = args.adapter if args.command == "convert" else "data9"
        report = convert_source(
            create_adapter(adapter_name, platform=getattr(args, "platform", None)),
            args.input,
            args.output,
            selected_events=set(args.events) if args.events else None,
            start=args.start,
            end=args.end,
            dedupe_text=args.dedupe_text,
        )
        print(json.dumps(report["totals"], ensure_ascii=False, indent=2))
        print(f"quality_report={report['report_path']}")
        return 0
    if args.command == "run-release":
        state = run_release_workflow(
            source=args.input,
            config=args.config,
            run_dir=args.run_dir,
            adapter_name=args.adapter,
            adapter_platform=args.platform,
            dedupe_text=args.dedupe_text,
            annotations=args.annotations,
            resume=args.resume,
            shard_size=args.shard_size,
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0 if state["status"] in {"awaiting_sentiment", "complete"} else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
