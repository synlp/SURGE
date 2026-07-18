# SURGE 35-event data pipeline handoff

## Delivery status

The pipeline, Qwen3-32B sentiment annotation, deterministic aggregation, and final SURGE-compatible validation are complete.

| Scope | Result |
|---|---:|
| Events | 35 |
| Post-level sentiment annotations | 441,631 |
| Existing data9 batch | 20 events / 228,690 posts |
| New crawler batch | 15 events / 212,941 posts |
| Event-granularity releases | 105 |
| Missing, extra, duplicate, or invalid annotations | 0 |
| Unit tests | 24 passed |

Sentiment labels contain 118,284 positive, 181,893 neutral, and 141,454 negative records. Full details are in `docs/SENTIMENT_35_EVENT_COMPLETION.md`.

## External delivery archives

The delivery directory contains three archives. Verify each against `SHA256SUMS.txt` before extraction.

1. `SURGE_event_data_pipeline_code_v2.zip`
   - Portable source, tests, configs, tools, documentation, and repository instructions.
2. `SURGE_35events_release_20260718_v1.zip`
   - Final 20-event and 15-event SURGE-compatible releases plus validation reports.
3. `SURGE_35events_qwen3_annotations_v1.zip`
   - Three immutable full-run worker JSONL files, the partition utility, and the completion report.

The annotation archive intentionally excludes the regenerated partitions because they duplicate the three worker files byte-for-byte in aggregate. Recreate the two partitions with `event_pipeline.sentiment_partition` and the two input manifests when needed.

## Review procedure

1. Verify archive SHA-256 values.
2. Extract the code archive and create a clean Python 3.11+ environment.
3. Run `python -m unittest discover -s tests -v`.
4. Extract the release archive without changing its internal paths.
5. Run `event_pipeline.validate_release` against both `events` directories.
6. Compare the generated reports with the included validated reports.
7. Review the methodological caveat below before merging into the main SURGE project.

## Methodological caveat

The labeling run used the same stated model family as SURGE: Qwen3-32B. Thinking was disabled and output was constrained to `negative`, `neutral`, or `positive`. The checked-out public SURGE repository says that a documented prompt was used but does not contain that prompt text. Consequently, this delivery establishes model-family, schema, and processing compatibility, not word-for-word prompt identity with the original private run.

## Suggested Codex prompt for the recipient

> Read `AGENTS.md`, `HANDOFF.md`, `docs/SENTIMENT_35_EVENT_COMPLETION.md`, and `docs/SURGE_COMPATIBILITY.md`. Verify the external archives against `SHA256SUMS.txt`, run all unit tests and both release validators, and report whether the delivery is ready to merge. Treat annotation workers and release artifacts as immutable. Do not modify source evidence or claim exact original-prompt equivalence.

## Source preservation

The original local project directories and the server-side inference outputs were not moved, deleted, or overwritten while producing this handoff. Delivery archives are copies made from the validated artifacts.

## Pipeline v0.2 follow-up

Before upstream submission, the independent pipeline gained registered Data9,
generic JSONL and Reddit JSONL adapters; an isolated resumable `run-release`
workflow; strict release validation; and explicit remote/GPU dependency
profiles. See `docs/PRODUCTION_WORKFLOW.md`. These additions do not modify the
validated 35-event artifacts described above.
