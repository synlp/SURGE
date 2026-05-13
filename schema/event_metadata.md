# Schema: Event metadata

The event registry lives in `event_config.py` at the repository root and
provides one `EventConfig` entry per released event. The same registry is
imported by the benchmark harness to drive event discovery, granularity
gating, and category-stratified analyses.

## EventConfig fields

| Field | Type | Description |
|---|---|---|
| `name` | string | Stable identifier used in folder names (`<name>_<granularity>`) and in the metric-aggregation outputs |
| `display_name` | string | Human-readable event title |
| `category` | string | One of the five event categories used in the paper: `natural_disaster`, `political`, `social_movement`, `technology`, or `sports_entertainment` |
| `start_time` | ISO-8601 string | Bin-start of the first bin in the released active period |
| `end_time` | ISO-8601 string | Bin-end of the last bin in the released active period |
| `available_granularities` | list of string | Subset of `["6H", "12H", "1D"]` that the event is released at |
| `notes` | string, optional | Maintainer notes |

## Active period

`start_time` and `end_time` delimit the **active period** identified by the
construction pipeline (full procedure documented in the paper's
time-series-construction appendix). Bins outside this window are not
released even when raw posts exist; this is what causes some events to
have fewer 12H or 1D bins than a naive division of the raw collection
would suggest.

## Categories

The five event categories are used in the paper's stratified analyses
(per-category MAE breakdowns and leave-one-category-out cross-event
generalization). Each event is assigned a single category. Category
labels are intentionally coarse and editorial; they are not derived
from any automated classifier. The per-category event counts in the
release match the paper's event-list appendix:
Natural Disaster (12), Political (17), Social Movement (12),
Technology (12), and Sports & Entertainment (14), totaling 67 events.

## Synthetic events

The two synthetic mini-events shipped under `data/synthetic_examples/`
populate the same fields. Their `category` is set to `synthetic` so that
any analysis that filters by category will exclude them by default.
