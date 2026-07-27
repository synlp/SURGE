# SURGE Web v2

This directory is a self-contained GitHub Pages release of the SURGE public
website.

## Included

- The original SURGE dataset introduction page at `index.html`.
- Unified event discovery and the complete 297-event catalog at
  `live/index.html`.
- A compatibility redirect at `live/events.html` for previously shared links.
- Event-level activity, sentiment, sentiment time-series, stance-layout preview,
  and supporting aggregate details at `live/event.html`.
- Static JSON and JavaScript companions for the current public aggregate.
- The runtime boundary needed to replace static data with `/api/v1` endpoints
  later.

## Publication boundary

The release contains aggregate public data only. It does not contain post text,
post URLs, account identifiers, crawler credentials, model weights, private
analysis batches, or local filesystem paths.

The stance section is an illustrative four-group layout. Groups A, B, C, and D
are intentionally equal placeholders and must not be interpreted as analyzed
event results.

## GitHub Pages

The package root corresponds to a GitHub Pages publishing root. Copy its
contents into the repository's `docs/` directory, or publish the package root
from a dedicated Pages branch.

After upload, the expected entry points are:

- `/index.html`
- `/live/index.html`
- `/live/event.html?id=surge300v2-127`

Keep `.nojekyll` in the published root.
