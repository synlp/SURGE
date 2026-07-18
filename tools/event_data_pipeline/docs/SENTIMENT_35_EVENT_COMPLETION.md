# Qwen3-32B sentiment completion report

## Outcome

Sentiment annotation and deterministic SURGE aggregation completed successfully on 2026-07-18 for all 35 events.

| Batch | Events | Annotation records | Release granularities | Validation |
|---|---:|---:|---:|---|
| Existing data9 | 20 | 228,690 | 60 | valid, 0 errors |
| New crawler backup | 15 | 212,941 | 45 | valid, 0 errors |
| Total | 35 | 441,631 | 105 | complete |

The full annotation set contains 118,284 positive, 181,893 neutral, and 141,454 negative labels. Every `(event_id, post_id)` input key has exactly one annotation. There are no missing keys, extra keys, duplicate keys, invalid fields, invalid labels, or label/score mismatches.

## Model run

- Model: local Qwen3-32B BF16
- Runtime: vLLM 0.9.2 with PyTorch 2.7.0+cu126
- Layout: three independent 2xA40 tensor-parallel workers
- Prompt: `surge-sentiment-qwen3-v1`, thinking disabled, constrained three-label output
- Full inference duration: approximately 42 minutes
- Generation failures: 0

The public SURGE repository states that Qwen3-32B and a documented prompt were used, but the checked-out public repository does not include the prompt text. Model and output-schema compatibility are confirmed; word-for-word prompt identity with the original private labeling run cannot be claimed.

## Preserved annotation artifacts

- Server source: `/media/ubuntu/data/chenming/projects/surge-sentiment/runs/full-441631-v1`
- Local downloaded workers: `data/sentiment/output/qwen3_32b_full_v1/worker-*.jsonl`
- Local 20-event partition: `data/sentiment/output/qwen3_32b_full_v1/partitions/data9_20events/`
- Local 15-event partition: `data/sentiment/output/qwen3_32b_full_v1/partitions/surge_crawler_15/`

Downloaded worker SHA-256 values match the server-validated files:

- `worker-0.jsonl`: `afcdb9491e689c48b5ab86902ca7eb04328260c1c13dd5cdf72f81e1f908645f`
- `worker-1.jsonl`: `63d40a6bbcfa209833c78709a409e7296edcee97a0df37a5319e33c3e71f5a34`
- `worker-2.jsonl`: `bf1eec0461c61ed416aaf0cf51e6b1a3c87655ff35d84af906bfdbb745bb7637`

## Final SURGE-compatible releases

- 20-event release: `data/release/surge/events/`
- 15-event release: `data/surge_crawler_15/release/surge/events/`
- 20-event sentiment report: `data/release/reports/sentiment_timeseries_export.json`
- 15-event sentiment report: `data/surge_crawler_15/release/reports/sentiment_timeseries_export.json`
- 20-event validation: `data/release/reports/surge_release_validation_with_sentiment.json`
- 15-event validation: `data/surge_crawler_15/release/reports/surge_release_validation_with_sentiment.json`

All 105 event-granularity directories contain both `sentiment_polarity.csv` and `sentiment_polarity_normalized.csv`, and their `normalization.json` files include sentiment normalization statistics.
