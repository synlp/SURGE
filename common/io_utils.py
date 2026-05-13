"""
I/O utilities for reading/writing JSONL, JSON, and CSV files.
"""

import json
import csv
from pathlib import Path
from typing import Iterator


def read_jsonl(filepath: str) -> list[dict]:
    """Read a JSONL file (one JSON object per line)."""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(filepath: str, records: list[dict]) -> None:
    """Write records to a JSONL file (one JSON object per line)."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def iter_jsonl(filepath: str) -> Iterator[dict]:
    """Iterate over a JSONL file without loading all into memory."""
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_json(filepath: str) -> dict | list:
    """Read a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(filepath: str, data: dict | list, indent: int = 2) -> None:
    """Write data to a JSON file."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def write_csv(filepath: str, rows: list[dict], fieldnames: list[str] = None) -> None:
    """Write a list of dicts to a CSV file.

    Args:
        filepath: Output CSV path.
        rows: List of dicts to write.
        fieldnames: Column order. If None, uses keys from the first row.
    """
    if not rows:
        return
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(filepath: str) -> list[dict]:
    """Read a CSV file into a list of dicts."""
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)
