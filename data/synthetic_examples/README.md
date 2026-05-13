# Synthetic mini-events

Two fully synthetic events. Their numerical series, text content, and
reply / repost edges are all fabricated and instantiate every artifact
type documented in `schema/` at all three temporal granularities.
**They must not be used for any quantitative evaluation.**

## Layout

```
synthetic_examples/
├── README.md
├── event_metadata.json
└── events/
    ├── synthetic_tech_keynote/
    │   └── edges.jsonl
    ├── synthetic_tech_keynote_6H/
    │   ├── comment_count.csv
    │   ├── ...
    │   ├── normalization.json
    │   └── text_view.jsonl              (1D only)
    ├── synthetic_tech_keynote_12H/
    ├── synthetic_tech_keynote_1D/
    ├── synthetic_storm_alert/
    ├── synthetic_storm_alert_6H/
    ├── synthetic_storm_alert_12H/
    └── synthetic_storm_alert_1D/
```

## Tagging

Every synthetic post / reply text begins with the literal token
`[SYNTHETIC]` and every synthetic post id starts with the prefix
`synthetic_`. The event metadata sets `category = "synthetic"` so
that any analysis filtering by category excludes these events by
default.
