"""
Reconstruct text views from anonymized post IDs.

The release ships ``text_view.jsonl`` and ``edges.jsonl`` with post-ID
references only. This script reads those records together with the
matching ``post_id_lookup.jsonl`` (which maps ``post_id`` → originating
platform + URL when available) and populates each record's ``text``,
``user_id``, ``post_time``, and engagement-count fields by fetching
from the originating platforms.

Each platform requires its own credentials and SDK. The fetchers below
raise :class:`NotImplementedError` with the upstream library and
authentication scope to plug in. Once a fetcher is implemented for a
platform, ``hydrate_event`` uses it transparently to enrich every
``text_view.jsonl`` record whose lookup entry points at that platform.

Usage::

    python scripts/hydrate.py --event gpt_release --granularity 1D \\
        --data-dir data/events --output-dir data/events_hydrated
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


# ---------------------------------------------------------------------------
# Platform fetchers
# ---------------------------------------------------------------------------

def fetch_twitter(
    post_ids: Iterable[str], url_lookup: Dict[str, str],
) -> Dict[str, dict]:
    """Resolve Twitter / X post IDs to payload dicts.

    Plug in :mod:`tweepy` (or ``requests`` against the v2 endpoint) with a
    bearer token in environment variable ``X_BEARER_TOKEN``. Return a dict
    keyed by ``post_id`` with at least ``text``, ``user_id``,
    ``post_time``, ``like_count``, ``reply_count``, ``retweet_count``.
    """
    raise NotImplementedError(
        "Plug in tweepy.Client with X_BEARER_TOKEN; see Twitter API v2 docs."
    )


def fetch_reddit(
    post_ids: Iterable[str], url_lookup: Dict[str, str],
) -> Dict[str, dict]:
    """Resolve Reddit submission / comment IDs to payload dicts.

    Plug in :mod:`praw` with credentials in environment variables
    ``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``, and ``REDDIT_USER_AGENT``.
    """
    raise NotImplementedError(
        "Plug in praw.Reddit with REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET; "
        "see PRAW docs."
    )


def fetch_threads(
    post_ids: Iterable[str], url_lookup: Dict[str, str],
) -> Dict[str, dict]:
    """Resolve Threads post IDs to payload dicts.

    Plug in the Meta Graph API for Threads with a long-lived user access
    token in ``THREADS_ACCESS_TOKEN``.
    """
    raise NotImplementedError(
        "Plug in Meta Threads Graph API with THREADS_ACCESS_TOKEN."
    )


PLATFORM_FETCHERS = {
    "twitter": fetch_twitter,
    "x": fetch_twitter,
    "reddit": fetch_reddit,
    "threads": fetch_threads,
}


# ---------------------------------------------------------------------------
# Lookup + enrichment
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _load_lookup(event_dir: Path) -> Dict[str, dict]:
    """Load ``post_id_lookup.jsonl`` into ``{post_id: {platform, url}}``."""
    rows = _read_jsonl(event_dir / "post_id_lookup.jsonl")
    return {r["post_id"]: {"platform": r.get("platform", ""), "url": r.get("url", "")}
            for r in rows}


def _resolve_payloads(
    pids: List[str], lookup: Dict[str, dict],
) -> Dict[str, dict]:
    by_platform: Dict[str, List[str]] = defaultdict(list)
    for pid in pids:
        plat = lookup.get(pid, {}).get("platform", "").lower()
        by_platform[plat].append(pid)

    payloads: Dict[str, dict] = {}
    for platform, ids in by_platform.items():
        fetcher = PLATFORM_FETCHERS.get(platform)
        if fetcher is None:
            continue
        url_lookup = {pid: lookup[pid].get("url", "") for pid in ids if pid in lookup}
        payloads.update(fetcher(ids, url_lookup))
    return payloads


def _enrich_record(record: dict, payloads: Dict[str, dict]) -> dict:
    out = dict(record)
    for mp in out.get("main_posts", []):
        mp.update(payloads.get(mp.get("post_id", ""), {}))
        for rp in mp.get("replies", []):
            rp.update(payloads.get(rp.get("post_id", ""), {}))
    return out


def hydrate_event(
    data_dir: Path, event: str, granularity: str, output_dir: Path,
) -> Path:
    """Hydrate the text view of one ``(event, granularity)`` pair.

    Reads ``<data_dir>/<event>_<granularity>/text_view.jsonl`` plus
    ``<data_dir>/<event>/post_id_lookup.jsonl``; writes
    ``<output_dir>/<event>_<granularity>/text_view_hydrated.jsonl``.
    """
    event_dir = data_dir / event
    bin_dir = data_dir / f"{event}_{granularity}"
    if not (bin_dir / "text_view.jsonl").exists():
        raise FileNotFoundError(
            f"Missing text_view.jsonl at {bin_dir}; cannot hydrate."
        )

    lookup = _load_lookup(event_dir)
    records = _read_jsonl(bin_dir / "text_view.jsonl")

    pids: List[str] = []
    for rec in records:
        for mp in rec.get("main_posts", []):
            pids.append(mp.get("post_id", ""))
            for rp in mp.get("replies", []):
                pids.append(rp.get("post_id", ""))
    pids = [p for p in set(pids) if p]

    payloads = _resolve_payloads(pids, lookup)

    out_dir = output_dir / f"{event}_{granularity}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "text_view_hydrated.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(_enrich_record(rec, payloads), ensure_ascii=False) + "\n")
    return out_path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--event", required=True)
    parser.add_argument("--granularity", required=True, choices=["1D", "12H", "6H"])
    parser.add_argument("--data-dir", type=Path, default=Path("data/events"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/events_hydrated"))
    args = parser.parse_args(argv)

    out = hydrate_event(args.data_dir, args.event, args.granularity, args.output_dir)
    print(f"Hydrated text view written to {out}")


if __name__ == "__main__":
    main()
