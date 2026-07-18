from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def refresh_manifest(input_dir: Path) -> dict:
    path = input_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for shard in manifest["shards"]:
        shard_path = input_dir / shard["file"]
        shard["bytes"] = shard_path.stat().st_size
        shard["sha256"] = file_sha256(shard_path)
    manifest["hash_scope"] = "exact on-disk bytes"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh sentiment shard hashes from exact disk bytes")
    parser.add_argument("input_dir", type=Path)
    args = parser.parse_args(argv)
    result = refresh_manifest(args.input_dir)
    print(json.dumps({"records": result["total_records"], "shards": len(result["shards"]), "hash_scope": result["hash_scope"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
