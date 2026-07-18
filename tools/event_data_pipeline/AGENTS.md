# Repository guidance for Codex

## Purpose

This repository is an independent pipeline for converting multi-platform event data into SURGE-compatible releases. The completed 2026-07-18 handoff covers 35 events and 441,631 Qwen3-32B sentiment annotations.

Start by reading `HANDOFF.md`, `docs/PRODUCTION_WORKFLOW.md`, `docs/SENTIMENT_35_EVENT_COMPLETION.md`, and `docs/SURGE_COMPATIBILITY.md`.

## Preservation rules

- Treat downloaded annotation workers, source inputs, raw backups, and completed release artifacts as immutable evidence.
- Never overwrite or silently regenerate a delivered artifact. Write experimental or revised outputs to a new versioned directory.
- Do not commit model weights, virtual environments, raw data, generated releases, credentials, cookies, authentication headers, runtime caches, or server logs.
- Keep code and data delivery separate. Verify every external archive against `SHA256SUMS.txt` before using it.
- The public SURGE repository does not expose the original sentiment prompt text. Do not claim word-for-word prompt identity; model and schema compatibility are the supported claim.

## Setup and verification

Use Python 3.11 or later.

```bash
python -m venv .venv
python -m pip install -e .
python -m unittest discover -s tests -v
```

Optional SSH/SFTP dependencies are installed with `pip install -e .[remote]`.
GPU inference must use the separately documented Linux/CUDA profile; do not
install or load it as part of ordinary CPU validation.

Validate an extracted release with:

```bash
python -m event_pipeline.validate_release <release-events-directory> --report <report-path>
```

The expected final state is:

- 20-event release: 60 event-granularity directories, 228,690 lookup posts, zero validation errors.
- 15-event release: 45 event-granularity directories, 212,941 lookup posts, zero validation errors.
- Total sentiment annotations: 441,631 unique `(event_id, post_id)` keys.

## Change discipline

- Use `apply_patch` or focused edits for source changes.
- Add or update tests for behavioral changes and run the full suite.
- Preserve existing user data and unrelated changes.
- Report exact validation evidence and remaining research-quality caveats.
