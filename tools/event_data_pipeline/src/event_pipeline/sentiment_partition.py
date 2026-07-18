from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from event_pipeline.sentiment import validate_annotation
from event_pipeline.sentiment_finalize import expected_keys


def partition_annotations(
    annotations: Path,
    groups: dict[str, Path],
    output_root: Path,
) -> dict:
    expected = {name: expected_keys(path) for name, path in groups.items()}
    owners: dict[tuple[str, str], str] = {}
    for name, keys in expected.items():
        overlap = set(owners).intersection(keys)
        if overlap:
            raise ValueError(f"input groups overlap: {name} has {len(overlap)} duplicate keys")
        owners.update((key, name) for key in keys)

    sources = sorted(annotations.glob("worker-*.jsonl"))
    if not sources:
        raise FileNotFoundError("no worker-*.jsonl annotation files found")
    if output_root.exists():
        raise FileExistsError(f"partition output already exists: {output_root}")
    temporary = output_root.with_name(output_root.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    for name in groups:
        (temporary / name).mkdir(parents=True, exist_ok=True)

    seen: set[tuple[str, str]] = set()
    counts = {name: 0 for name in groups}
    try:
        for source in sources:
            handles = {
                name: (temporary / name / source.name).open("w", encoding="utf-8", newline="\n")
                for name in groups
            }
            try:
                with source.open("r", encoding="utf-8") as input_handle:
                    for line_number, line in enumerate(input_handle, 1):
                        if not line.strip():
                            continue
                        value = json.loads(line)
                        errors = validate_annotation(value)
                        if errors:
                            raise ValueError(f"{source}:{line_number}: {'; '.join(errors)}")
                        key = (str(value["event_id"]), str(value["post_id"]))
                        if key in seen:
                            raise ValueError(f"duplicate annotation key: {key}")
                        seen.add(key)
                        owner = owners.get(key)
                        if owner is None:
                            raise ValueError(f"annotation is not present in any input group: {key}")
                        handles[owner].write(line if line.endswith("\n") else line + "\n")
                        counts[owner] += 1
            finally:
                for handle in handles.values():
                    handle.close()
        missing = set(owners) - seen
        if missing:
            raise ValueError(f"annotations are missing {len(missing)} expected keys")
        for name, keys in expected.items():
            if counts[name] != len(keys):
                raise AssertionError(f"partition count mismatch for {name}")
        temporary.replace(output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "valid": True,
        "annotation_records": len(seen),
        "groups": {name: {"records": counts[name], "path": str(output_root / name)} for name in groups},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Partition a validated annotation run by input key sets")
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--group", action="append", required=True, metavar="NAME=INPUT_DIR")
    args = parser.parse_args(argv)
    groups: dict[str, Path] = {}
    for item in args.group:
        name, separator, raw_path = item.partition("=")
        if not separator or not name or not raw_path:
            parser.error(f"invalid --group value: {item!r}")
        if name in groups:
            parser.error(f"duplicate group name: {name}")
        groups[name] = Path(raw_path)
    report = partition_annotations(args.annotations, groups, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
