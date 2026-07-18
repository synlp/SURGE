from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import tempfile
from pathlib import Path

import paramiko

from event_pipeline.adapters import Data9ZipAdapter
from event_pipeline.pipeline import convert_source
from event_pipeline.validate import validate_unified


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a remote data9 ZIP without retaining the raw archive")
    parser.add_argument("remote_zip")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--host", default=os.environ.get("DATASET_SSH_HOST"))
    parser.add_argument("--user", default=os.environ.get("DATASET_SSH_USER"))
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--expected-host-key", default=os.environ.get("EXPECTED_SSH_HOST_KEY_SHA256"))
    parser.add_argument("--dedupe-text", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("DATASET_SSH_PASSWORD")
    if not args.host or not args.user or password is None or not args.expected_host_key:
        raise SystemExit("host, user, password, and expected host-key fingerprint are required")

    sock = socket.create_connection((args.host, args.port), timeout=20)
    transport = paramiko.Transport(sock)
    try:
        transport.start_client(timeout=20)
        actual_key = hashlib.sha256(transport.get_remote_server_key().asbytes()).hexdigest()
        if actual_key.lower() != args.expected_host_key.lower():
            raise RuntimeError("SSH host-key fingerprint mismatch")
        transport.auth_password(args.user, password)
        if not transport.is_authenticated():
            raise RuntimeError("SSH authentication failed")
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                local_zip = Path(temp_dir) / "data9.zip"
                with sftp.open(args.remote_zip, "rb") as source, local_zip.open("wb") as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                source_size = local_zip.stat().st_size
                conversion = convert_source(
                    Data9ZipAdapter(), local_zip, args.output,
                    dedupe_text=args.dedupe_text,
                )
                validation = validate_unified(args.output)
                safe_result = {
                    "source_bytes": source_size,
                    "conversion": conversion["totals"],
                    "validation": {
                        "valid": validation["valid"],
                        "event_count": validation["event_count"],
                        "post_count": validation["post_count"],
                        "edge_count": validation["edge_count"],
                        "error_count": validation["error_count"],
                    },
                    "quality_report": conversion["report_path"],
                    "raw_archive_retained": False,
                }
                print(json.dumps(safe_result, ensure_ascii=False, indent=2))
                return 0 if validation["valid"] else 1
        finally:
            sftp.close()
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())

