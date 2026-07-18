# Data processing tools

`event_data_pipeline/` is an independently runnable, versioned pipeline for
converting collected event data into SURGE-compatible artifacts. It includes
registered Data9, generic JSONL and Reddit JSONL adapters, a resumable staged
workflow, privacy-minimized sentiment preparation and strict release validation.

The tool intentionally does not contain raw datasets, model weights, credentials
or generated release artifacts. Start with
[`event_data_pipeline/AGENTS.md`](event_data_pipeline/AGENTS.md) and
[`event_data_pipeline/docs/PRODUCTION_WORKFLOW.md`](event_data_pipeline/docs/PRODUCTION_WORKFLOW.md).
