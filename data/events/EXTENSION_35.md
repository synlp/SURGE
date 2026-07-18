# 35-event ID-only extension

This extension adds 35 events and 441,631 unique event/post records to the
repository release. Every event includes 6H, 12H, and 1D discussion-intensity
and sentiment-polarity series, normalization metadata, sampled bin views,
post-ID lookup records, and interaction edges.

## Public release mode

The extension follows the public repository's ID-only representation:

- `text_view.jsonl` contains anonymized `post_id` references and reply
  structure, not social-platform post text;
- `post_id_lookup.jsonl` contains `post_id`, platform, and URL when available;
- no user ID, author handle, nickname, profile data, contact details,
  geolocation, credentials, model weights, raw collection files, or full
  sentiment-annotation records are included.

The private processing layer retains source text for reproducibility and
authorized analysis, but it is deliberately outside this public Git release.

## Provenance and audit

`extension_35_manifest.json` records the source batch, original event ID,
public event name, post/edge/bin counts, privacy mode, and deterministic hash
of every event's released files. The 35 event names were checked against the
original registry, and their post IDs have zero overlap with the existing
public textual-artifact subset.
