# Schema: Per-event numerical time series

## Directory layout

Numerical CSVs are organized one folder per (event, granularity), where
the folder is named `<event_name>_<granularity>` and contains four CSV
variants plus the per-event normalization statistics:

```
data/events/<event_name>_<granularity>/
├── comment_count.csv                    # Discussion Intensity (DI), raw
├── comment_count_normalized.csv         # DI, per-event z-score (NaN preserved)
├── sentiment_polarity.csv               # Sentiment Polarity (SP), raw
├── sentiment_polarity_normalized.csv    # SP, per-event z-score (NaN preserved)
└── normalization.json                   # per-event z-score statistics
```

`<granularity>` is one of `6H`, `12H`, `1D`. Some shorter events do not
have enough bins to populate the larger granularities; in that case the
corresponding directory is simply absent. The current repository release
covers 102 events at 6H, 99 events at 12H, and 90 events at 1D; the
original paper benchmark covered 67 / 64 / 55 respectively.

The two released variables match the paper's Equation 1: Discussion
Intensity $c_t = |\mathcal{P}_t|$ and Sentiment Polarity
$\bar{s}_t = \frac{1}{c_t}\sum_{p \in \mathcal{P}_t} s_p$ with
$s_p \in \{-1, 0, +1\}$.

## CSV format

All CSVs share the same overall structure: a `time` column followed by
a single value column, with one row per bin in chronological order.
Bin boundaries are aligned to absolute calendar time (UTC).

### `comment_count.csv` (Discussion Intensity, raw)

| Column | Type | Description |
|---|---|---|
| `time` | string | Bin-start timestamp, ISO-8601, tz-naive |
| `count` | integer ≥ 0 | Number of posts whose `post_time` falls in this bin |

A row with `count` missing (`NaN`) means the bin is inside the event's
active period but contains zero observed posts. Empty bins are
preserved as `NaN` so that downstream users retain the choice of
imputation strategy.

### `sentiment_polarity.csv` (Sentiment Polarity, raw)

| Column | Type | Description |
|---|---|---|
| `time` | string | Bin-start timestamp, ISO-8601, tz-naive |
| `polarity` | float ∈ [−1, +1] | Mean of per-post LLM-assigned polarity scores in the bin |

Per-post polarity uses the mapping `positive → +1`, `neutral → 0`,
`negative → −1`. Empty bins yield `NaN`.

### `*_normalized.csv` variants

Each raw CSV has a paired `*_normalized.csv` whose value column holds
per-event z-scored values, computed using the per-event normalization
statistics documented in [`normalization.md`](normalization.md). The
`time` column is identical to the raw variant. Bins that are `NaN` in
the raw CSV remain `NaN` in the normalized CSV — z-scoring is applied
position-wise to non-`NaN` values only, and imputation is performed at
load time so that no information crosses split boundaries.

## Reading a CSV

```python
import pandas as pd

df = pd.read_csv("data/events/<event>_1D/sentiment_polarity_normalized.csv")
# df["time"]      -> chronological bin-start timestamps
# df["polarity"]  -> per-event z-scored mean polarity per bin, NaN for empty bins
```

The benchmark `data_loader.py` performs split-internal forward fill
followed by backward fill within each of the 70 / 10 / 20 chronological
segments before producing sliding windows. No imputation reference
ever crosses a split boundary.
