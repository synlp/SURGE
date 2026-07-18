from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import tempfile
import zipfile
from pathlib import Path

import paramiko

from event_pipeline.adapters import Data9ZipAdapter
from event_pipeline.pipeline import convert_source
from event_pipeline.validate import validate_unified


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one remote data9 event without retaining raw data")
    parser.add_argument("remote_zip")
    parser.add_argument("event")
    parser.add_argument("--host", default=os.environ.get("DATASET_SSH_HOST"))
    parser.add_argument("--user", default=os.environ.get("DATASET_SSH_USER"))
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--expected-host-key", default=os.environ.get("EXPECTED_SSH_HOST_KEY_SHA256"))
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
                temp = Path(temp_dir)
                sample_zip = temp / "event_sample.zip"
                prefix = f"data9/{args.event}/"
                copied_files = 0
                with sftp.open(args.remote_zip, "rb") as remote_file:
                    with zipfile.ZipFile(remote_file) as source_archive:
                        with zipfile.ZipFile(sample_zip, "w", compression=zipfile.ZIP_DEFLATED) as sample_archive:
                            for info in source_archive.infolist():
                                if info.is_dir() or not info.filename.startswith(prefix):
                                    continue
                                sample_archive.writestr(info.filename, source_archive.read(info))
                                copied_files += 1
                if copied_files == 0:
                    raise RuntimeError("No files found for selected event")

                unified = temp / "unified"
                conversion = convert_source(
                    Data9ZipAdapter(), sample_zip, unified,
                    selected_events={args.event},
                )
                validation = validate_unified(unified)
                safe_result = {
                    "event": args.event,
                    "source_json_files": copied_files,
                    "conversion": conversion["totals"],
                    "validation": {
                        "valid": validation["valid"],
                        "post_count": validation["post_count"],
                        "edge_count": validation["edge_count"],
                        "error_count": validation["error_count"],
                    },
                    "raw_data_retained": False,
                }
                print(json.dumps(safe_result, ensure_ascii=False, indent=2))
                return 0 if validation["valid"] else 1
        finally:
            sftp.close()
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())

