from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from event_pipeline.adapters import create_adapter
from event_pipeline.batch import EventSpec, load_event_specs, run_batch
from event_pipeline.sentiment_finalize import finalize
from event_pipeline.sentiment_prepare import prepare_sentiment_input
from event_pipeline.surge_graph import export_corpus_graphs
from event_pipeline.text_view import export_corpus_text_views
from event_pipeline.timeseries import build_corpus_series
from event_pipeline.validate_release import validate_release


WORKFLOW_VERSION = "1.0.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _windows_report(specs: list[EventSpec], path: Path) -> dict:
    events = []
    for spec in specs:
        if not spec.enabled:
            continue
        if not spec.start or not spec.end:
            raise ValueError(f"end-to-end release requires start and end for {spec.event_id}")
        events.append({
            "event_id": spec.event_id,
            "recommended_window": {"start": spec.start, "end": spec.end, "source": "workflow_config"},
        })
    report = {"event_count": len(events), "window_policy": "[start, end), UTC", "events": events}
    _write_json_atomic(path, report)
    return report


def run_release_workflow(
    *,
    source: Path,
    config: Path,
    run_dir: Path,
    adapter_name: str,
    adapter_platform: str | None = None,
    dedupe_text: bool = False,
    annotations: Path | None = None,
    resume: bool = False,
    shard_size: int = 10_000,
) -> dict:
    """Run conversion through a validated SURGE release in an isolated run directory."""
    state_path = run_dir / "run_state.json"
    if run_dir.exists() and any(run_dir.iterdir()) and not state_path.exists():
        raise ValueError(f"run directory is non-empty and has no workflow state: {run_dir}")
    if state_path.exists() and not resume:
        raise ValueError("run already exists; pass --resume to continue from completed stages")

    fingerprint = {
        "source_sha256": _sha256(source),
        "config_sha256": _sha256(config),
        "adapter": adapter_name,
        "adapter_platform": adapter_platform or "",
        "dedupe_text": dedupe_text,
        "shard_size": shard_size,
        "workflow_version": WORKFLOW_VERSION,
    }
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("fingerprint") != fingerprint:
            raise ValueError("resume fingerprint mismatch; source, config, adapter or options changed")
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
        state = {"fingerprint": fingerprint, "completed_stages": [], "status": "running"}
        _write_json_atomic(state_path, state)

    unified = run_dir / "unified"
    reports = run_dir / "reports"
    release = run_dir / "release" / "surge" / "events"
    sentiment_input = run_dir / "sentiment" / "input"
    windows_path = reports / "event_windows.json"
    specs = load_event_specs(config)

    def stage(name: str, action: Callable[[], object]) -> object | None:
        if name in state["completed_stages"]:
            return None
        result = action()
        state["completed_stages"].append(name)
        state["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _write_json_atomic(state_path, state)
        return result

    adapter = create_adapter(adapter_name, platform=adapter_platform)
    stage("convert", lambda: run_batch(source, unified, specs, dedupe_text=dedupe_text, adapter=adapter))
    stage("windows", lambda: _windows_report(specs, windows_path))
    stage("comment_timeseries", lambda: build_corpus_series(unified, release, windows_path))
    stage("text_views", lambda: export_corpus_text_views(unified, release, windows_path))
    stage("graphs", lambda: export_corpus_graphs(unified, release, windows_path))
    stage("sentiment_input", lambda: prepare_sentiment_input(unified, windows_path, sentiment_input, shard_size=shard_size))
    base_validation = validate_release(release, require_sentiment=False)
    if not base_validation["valid"]:
        raise ValueError(f"base release validation failed with {base_validation['error_count']} errors")

    if annotations is None:
        state["status"] = "awaiting_sentiment"
    else:
        stage("sentiment_finalize", lambda: finalize(unified, release, windows_path, sentiment_input, annotations))
        final_validation = validate_release(release, require_sentiment=True)
        if not final_validation["valid"]:
            raise ValueError(f"final release validation failed with {final_validation['error_count']} errors")
        state["status"] = "complete"
        state["validation"] = final_validation
    state["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _write_json_atomic(state_path, state)
    return state
