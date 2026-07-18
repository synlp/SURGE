from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
from pathlib import Path

import paramiko


def main() -> int:
    parser = argparse.ArgumentParser(description="Download an authorized remote file with host-key and checksum verification")
    parser.add_argument("remote_path")
    parser.add_argument("local_path", type=Path)
    parser.add_argument("--host", default=os.environ.get("DATASET_SSH_HOST"))
    parser.add_argument("--user", default=os.environ.get("DATASET_SSH_USER"))
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--expected-host-key", default=os.environ.get("EXPECTED_SSH_HOST_KEY_SHA256"))
    args = parser.parse_args()
    password = os.environ.get("DATASET_SSH_PASSWORD")
    if not args.host or not args.user or password is None or not args.expected_host_key:
        raise SystemExit("host, user, password, and expected host-key fingerprint are required")

    args.local_path.parent.mkdir(parents=True, exist_ok=True)
    partial = args.local_path.with_name(args.local_path.name + ".part")
    digest = hashlib.sha256()
    downloaded = 0

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
            expected_size = sftp.stat(args.remote_path).st_size
            with sftp.open(args.remote_path, "rb") as source, partial.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
            if downloaded != expected_size:
                raise RuntimeError(f"download size mismatch: expected {expected_size}, got {downloaded}")
            partial.replace(args.local_path)
            print(json.dumps({
                "local_path": str(args.local_path),
                "bytes": downloaded,
                "sha256": digest.hexdigest(),
                "verified": True,
            }, ensure_ascii=False, indent=2))
            return 0
        finally:
            sftp.close()
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())

