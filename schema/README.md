# SURGE Schema Documentation

Field-level documentation for every artifact type in the SURGE release.

| Artifact | Schema file |
|---|---|
| Per-event numerical time series | [`numerical_ts.md`](numerical_ts.md) |
| Per-event normalization statistics | [`normalization.md`](normalization.md) |
| Event metadata registry | [`event_metadata.md`](event_metadata.md) |
| Sampled bin-aligned text views | [`text_view.md`](text_view.md) |
| Per-event reply / repost edge list | [`edges.md`](edges.md) |

The two synthetic mini-events under `data/synthetic_examples/`
instantiate every schema in this directory at all three temporal
granularities.
