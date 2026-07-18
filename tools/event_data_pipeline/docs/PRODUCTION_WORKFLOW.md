# Production workflow v0.2

## Supported source adapters

- `data9`: the nested X/Twitter ZIP layout used by the original 20-event batch.
- `generic-jsonl`: flat social-media JSONL using common field aliases; pass
  `--platform` to record the actual source platform.
- `reddit-jsonl`: common Reddit submission/comment JSONL records, including
  epoch timestamps and `t1_`/`t3_` identifiers.

Adapters implement `SourceAdapter` and are selected through the registry in
`event_pipeline.adapters.registry`. A new platform format should be added as a
new adapter and test, not as source-specific branches in the core pipeline.

## One-command staged release

```bash
event-pipeline run-release \
  --input /path/to/source.jsonl \
  --config configs/events.json \
  --run-dir /path/to/new-versioned-run \
  --adapter generic-jsonl \
  --platform x
```

The run directory must be empty or absent. The command writes `run_state.json`
atomically and records an input/config fingerprint. It performs conversion,
unified validation, event windows, discussion time series, text views, graph
export, strict base-release validation, and privacy-minimized sentiment shards.
It then exits successfully with `status=awaiting_sentiment`.

After annotation, resume the same immutable input/config combination:

```bash
event-pipeline run-release \
  --input /path/to/source.jsonl \
  --config configs/events.json \
  --run-dir /path/to/new-versioned-run \
  --adapter generic-jsonl \
  --platform x \
  --annotations /path/to/annotations.jsonl \
  --resume
```

Completed stages are skipped. A changed source, config, adapter or deduplication
policy causes a fingerprint mismatch rather than silently mixing runs.

## Strict validation

```bash
python -m event_pipeline.validate_release /path/to/release/events --require-sentiment
```

The validator checks the event/granularity matrix, required files, exact CSV
headers, UTC time-bin continuity, numeric domains, count/sentiment alignment,
normalization metadata and training counts, graph endpoints and duplicates,
text-view limits/references, and forbidden direct identity keys.

Use `--allow-missing-sentiment` only for the deliberate pre-annotation gate.

## Dependency profiles

Core processing is Python 3.11+ standard library. SSH/SFTP tools use the pinned
`remote` extra. The GPU lock captures the project-specific Linux environment
that produced the validated run; GPU occupancy, disk availability and model
paths must still be checked before any separately authorized workload.
