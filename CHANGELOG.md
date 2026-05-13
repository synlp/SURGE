# Changelog

## v0.1

Initial release.

- 67-event registry at `data/events/event_metadata.json` and the
  matching per-event numerical CSVs at three temporal granularities.
- Two synthetic mini-events under `data/synthetic_examples/`.
- Benchmark code: data loader with split-internal imputation,
  evaluation metrics including `MAE_reply(k%)`, generic training
  loop, and the CMA reference probe (`benchmark/cma/`).
- Vendored MM-TSFlib backbone at `references/code/MM-TSFlib-main/`.
