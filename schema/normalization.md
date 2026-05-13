# Schema: Per-event normalization statistics

Each event ships its own per-variable z-score normalization statistics.
Statistics are fitted on the **train split only** of the corresponding
series and then applied to the entire series (train, validation, and
test), so no information crosses the split boundary at fitting time. The
imputation reference used while fitting `mean` and `std` is the
train-split-internal forward fill followed by backward fill described in
[`numerical_ts.md`](numerical_ts.md); the raw `*_normalized.csv` files
preserve `NaN` for empty bins so that imputation can also be applied
consistently at load time.

## File location

```
data/events/<event_name>_<granularity>/normalization.json
```

## File format

```json
{
  "event": "<event_name>",
  "granularity": "<6H|12H|1D>",
  "split_ratios": {"train": 0.7, "val": 0.1, "test": 0.2},
  "variables": {
    "comment_count":      {"mean": 12.4, "std": 8.7,  "n_train": 21},
    "sentiment_polarity": {"mean": 0.13, "std": 0.42, "n_train": 21}
  }
}
```

`mean` and `std` are computed on the train split only, after the
**split-internal** forward fill followed by backward fill is applied to
the train segment to resolve any empty bins inside it. `std` is the
sample standard deviation with `ddof=0`. `n_train` records the number
of train bins used to fit the statistics, for reference. Validation and
test bins never participate in fitting.

## Recomputing the normalized CSV

```python
normalized = (raw - mean) / std
```

The released `*_normalized.csv` files apply this formula position-wise
to non-`NaN` raw values. Bins that are `NaN` in the raw CSV remain `NaN`
in the normalized CSV; the loader fills them split-internally at load
time as documented in [`numerical_ts.md`](numerical_ts.md).
