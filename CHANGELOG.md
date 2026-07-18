# Changelog

## v0.2

- Added a 35-event public ID-only extension with 441,631 post IDs and
  complete 6H / 12H / 1D derived artifacts.
- Expanded the registry to 102 events with 102 / 99 / 90 granularity
  coverage while preserving the original 67-event paper benchmark.
- Added `extension_35_manifest.json` with per-event provenance, counts,
  privacy mode, and deterministic release hashes.

## v0.1

Initial release.

- 67-event registry at `data/events/event_metadata.json` and the
  matching per-event numerical CSVs at three temporal granularities.
- Two synthetic mini-events under `data/synthetic_examples/`.
- Benchmark code: data loader with split-internal imputation,
  evaluation metrics including `MAE_reply(k%)`, generic training
  loop, and the CMA reference probe (`benchmark/cma/`).
- Vendored MM-TSFlib backbone at `references/code/MM-TSFlib-main/`.
