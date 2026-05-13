# Schema: Per-event reply / repost edge list

A ready-to-inspect example record lives at
`data/synthetic_examples/events/synthetic_tech_keynote/edges.jsonl`.

## Coverage

The edge list is the unsampled interaction graph for the event over
its released active period. Both endpoints of each edge are sampled
posts that appear in the bin-level text views, or unsampled posts
that participate in the reply / repost chain of a sampled post.

The edge list is released once per event and does not depend on
temporal granularity.

## File layout

```
data/events/<event_name>/edges.jsonl
```

One JSON object per line, one line per edge.

## Per-edge record

```json
{
  "event": "<event_name>",
  "edge_type": "reply",
  "source_post_id": "<anonymized id>",
  "target_post_id": "<anonymized id>",
  "source_time":   "2026-03-04T01:18:09",
  "target_time":   "2026-03-04T01:14:30",
  "platform": "twitter"
}
```

`edge_type` is one of `reply`, `retweet`, `quote`, or `comment`.
`source_*` describes the responding post; `target_*` describes the
post being responded to. Both timestamps are tz-naive ISO-8601 and
are bin-alignable via the same temporal binning used for the
numerical series.

## Anonymization

`source_post_id` and `target_post_id` are the same stable post-id
hashes used in [`text_view.md`](text_view.md), so an edge can be
joined against the bin-level text view directly. No user-identifying
field appears in the edge record.

## Bin alignment

To weight an edge into a per-bin metric, take `source_time` and
locate the bin whose `[bin_start, bin_end)` contains it. The
`MAE_reply` metric implementation in `benchmark/mae_reply_utils.py`
shows the canonical binning logic.
