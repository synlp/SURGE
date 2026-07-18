from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup_latest(source: Path, destination: Path) -> dict:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"backup destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for plane in sorted(path for path in source.iterdir() if (path / "event_backups").is_dir()):
        for event_dir in sorted(path for path in (plane / "event_backups").iterdir() if path.is_dir()):
            latest_path = event_dir / "latest.json"
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            if not latest.get("verified"):
                raise ValueError(f"latest snapshot is not verified: {plane.name}/{event_dir.name}")
            snapshot_name = Path(latest["path"]).name
            source_snapshot = event_dir / snapshot_name
            target_event = destination / plane.name / "event_backups" / event_dir.name
            target_snapshot = target_event / snapshot_name
            shutil.copytree(source_snapshot, target_snapshot, copy_function=shutil.copy2)
            shutil.copy2(latest_path, target_event / "latest.json")

            manifest = json.loads((target_snapshot / "backup_manifest.json").read_text(encoding="utf-8"))
            issues = []
            copied_bytes = 0
            for item in manifest["files"]:
                path = target_snapshot / item["path"]
                if not path.exists():
                    issues.append(f"missing:{item['path']}")
                    continue
                copied_bytes += path.stat().st_size
                if sha256(path) != item["sha256"]:
                    issues.append(f"hash:{item['path']}")
            if issues:
                raise ValueError(f"backup verification failed for {event_dir.name}: {issues}")
            records.append({
                "plane": plane.name,
                "event_id": event_dir.name,
                "snapshot": snapshot_name,
                "verified": True,
                "file_count": len(manifest["files"]),
                "bytes": copied_bytes,
                "relative_path": str(target_snapshot.relative_to(destination)).replace("\\", "/"),
            })
    index = {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "snapshot_policy": "latest.json verified snapshot only",
        "event_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "events": records,
    }
    (destination / "backup_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy and verify each crawler event's latest immutable snapshot")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = backup_latest(args.source, args.destination)
    print(json.dumps({"event_count": result["event_count"], "total_bytes": result["total_bytes"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
