"""
Data loader for SURGE benchmark experiments.

Loads sentiment time series CSVs, creates sliding window (X, Y) pairs,
and provides DataLoaders for within-event and cross-event experiments.

Supported variables (matching the paper's Equation 1):
  - sentiment_polarity (SP): univariate, shape (T,)
  - comment_count    (DI): univariate, shape (T,)

Missing-bin imputation is performed split-internally: each event's series
is first split chronologically into 70 / 10 / 20 train / val / test
segments, and forward fill followed by backward fill is applied within
each segment independently so that no imputation reference crosses a
split boundary.
"""

import glob
import os
from typing import Optional

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = "data/events"

# Map variable name -> (csv stem, value columns).
_VARIABLE_CONFIG = {
    "sentiment_polarity": ("sentiment_polarity", ["polarity"]),
    "comment_count":      ("comment_count",      ["count"]),
}


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class EventTimeSeriesDataset(Dataset):
    """Sliding-window dataset over a 1-D or 2-D time series array.

    Given a contiguous array of shape (T,) or (T, C), produces (X, Y) pairs
    where X has shape (seq_len, n_features) and Y has shape (pred_len, n_features).
    """

    def __init__(self, values: np.ndarray, seq_len: int, pred_len: int):
        """
        Args:
            values: Time series values, shape (T,) or (T, C).
            seq_len: Number of input time steps.
            pred_len: Number of prediction time steps.
        """
        # Ensure 2-D: (T, n_features)
        if values.ndim == 1:
            values = values[:, np.newaxis]
        self.values = values.astype(np.float32)
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.window_len = seq_len + pred_len
        self.n_windows = max(len(self.values) - self.window_len + 1, 0)

    def __len__(self) -> int:
        return self.n_windows

    def __getitem__(self, idx: int):
        x = self.values[idx : idx + self.seq_len]               # (seq_len, C)
        y = self.values[idx + self.seq_len : idx + self.window_len]  # (pred_len, C)
        return torch.from_numpy(x), torch.from_numpy(y)


# ---------------------------------------------------------------------------
# Series loading
# ---------------------------------------------------------------------------

def load_event_series(
    data_dir: str,
    event_name: str,
    interval: str,
    variable: str,
    use_normalized: bool = True,
) -> tuple[list[str], np.ndarray]:
    """Load a single event's time series from its CSV file.

    Empty bins remain ``NaN`` in the returned array. Imputation is
    performed split-internally inside the dataloader factories.

    Args:
        data_dir: Root directory containing event folders.
        event_name: Event name (e.g. "gpt_release").
        interval: Temporal granularity (e.g. "1D", "12H").
        variable: One of the keys of :data:`_VARIABLE_CONFIG`.
        use_normalized: If True, load the z-score normalized CSV.

    Returns:
        (timestamps, values) where ``timestamps`` is a list of time strings
        and ``values`` is an ``np.ndarray`` of shape ``(T,)``. Empty bins
        are encoded as ``NaN``.
    """
    if variable not in _VARIABLE_CONFIG:
        raise ValueError(
            f"Unknown variable '{variable}'. "
            f"Choose from {list(_VARIABLE_CONFIG.keys())}."
        )
    csv_stem, value_cols = _VARIABLE_CONFIG[variable]

    # Build file path
    suffix = "_normalized" if use_normalized else ""
    folder = os.path.join(data_dir, f"{event_name}_{interval}")
    csv_path = os.path.join(folder, f"{csv_stem}{suffix}.csv")

    df = pd.read_csv(csv_path)

    timestamps = df["time"].astype(str).tolist()

    if len(value_cols) == 1:
        values = df[value_cols[0]].to_numpy(dtype=np.float64)  # (T,)
    else:
        values = df[value_cols].to_numpy(dtype=np.float64)     # (T, C)

    return timestamps, values


def _impute_split_internal(
    seg: np.ndarray,
    *,
    seed: float | np.ndarray | None = None,
) -> np.ndarray:
    """Forward fill then backward fill, confined to a single segment.

    Both passes operate on ``seg`` only; no value from outside ``seg``
    enters the result. When the entire segment is all-NaN and ``seed``
    is provided, the first position is seeded with ``seed`` before
    ffill+bfill so the segment becomes a constant ``seed``.
    """
    if seg.size == 0:
        return seg
    if seg.ndim == 1:
        s = pd.Series(seg)
        if seed is not None and np.isnan(seg).all():
            s = s.copy()
            s.iloc[0] = float(seed)
        return s.ffill().bfill().to_numpy(dtype=np.float64)
    df = pd.DataFrame(seg)
    if seed is not None and np.isnan(seg).all():
        df = df.copy()
        seed_arr = np.atleast_1d(np.asarray(seed, dtype=np.float64))
        if seed_arr.shape[0] != df.shape[1]:
            seed_arr = np.broadcast_to(seed_arr, (df.shape[1],)).copy()
        df.iloc[0, :] = seed_arr
    return df.ffill().bfill().to_numpy(dtype=np.float64)


def _last_finite_row(seg: np.ndarray) -> np.ndarray | float | None:
    """Return the last finite value (1-D) or row (2-D) in seg, or None."""
    if seg.size == 0:
        return None
    if seg.ndim == 1:
        valid = np.where(np.isfinite(seg))[0]
        if valid.size == 0:
            return None
        return float(seg[valid[-1]])
    finite_rows = np.where(np.isfinite(seg).all(axis=1))[0]
    if finite_rows.size == 0:
        return None
    return seg[finite_rows[-1]]


def _split_and_impute(
    values: np.ndarray,
    *,
    pred_len: int = 0,
    nan_tolerance: bool = True,
    relaxed_border: bool = True,
) -> tuple[np.ndarray, int, int]:
    """Apply the chronological split and impute each segment independently.

    Returns the imputed contiguous series together with the split
    boundaries ``(train_end, val_end)``. Splits use ``int(T * 0.7)`` and
    ``int(T * 0.8)``; when the standard ``val_end`` would leave fewer
    than ``pred_len`` bins for the test slice, ``val_end`` is pulled
    back to ``max(train_end, T - pred_len)``. An entirely-empty
    val / test segment is seeded with the previous segment's last
    imputed value before ffill+bfill.
    """
    T = len(values)
    train_end = int(T * 0.7)
    val_end_strict = int(T * 0.8)
    if relaxed_border and pred_len > 0 and val_end_strict > T - pred_len:
        val_end = max(train_end, T - pred_len)
    else:
        val_end = val_end_strict

    train_seg = _impute_split_internal(values[:train_end])
    train_seed = _last_finite_row(train_seg) if nan_tolerance else None
    val_seg = _impute_split_internal(values[train_end:val_end], seed=train_seed)
    val_seed = _last_finite_row(val_seg) if nan_tolerance else None
    if val_seed is None:
        val_seed = train_seed
    test_seg = _impute_split_internal(values[val_end:], seed=val_seed)

    return np.concatenate([train_seg, val_seg, test_seg], axis=0), train_end, val_end


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _discover_events(data_dir: str, interval: str) -> list[str]:
    """Discover all event names available for a given interval.

    Scans *_{interval}/ directories under data_dir and extracts event names.
    For example, directory "Trump_Inauguration_12H" with interval "12H" yields
    event name "Trump_Inauguration".

    Returns:
        Sorted list of event names.
    """
    pattern = os.path.join(data_dir, f"*_{interval}")
    dirs = sorted(glob.glob(pattern))
    events = []
    # Regex: everything before the last _<interval>
    suffix = f"_{interval}"
    for d in dirs:
        if not os.path.isdir(d):
            continue
        basename = os.path.basename(d)
        if basename.endswith(suffix):
            event_name = basename[: -len(suffix)]
            if event_name:
                events.append(event_name)
    return events


def _split_chronological(
    values: np.ndarray,
    train_ratio: float = 0.7,
    val_ratio: float = 0.1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split a time series array chronologically into train / val / test.

    Args:
        values: Shape (T,) or (T, C).
        train_ratio: Fraction for training.
        val_ratio: Fraction for validation. Test gets the rest.

    Returns:
        (train, val, test) arrays.
    """
    T = len(values)
    train_end = int(T * train_ratio)
    val_end = int(T * (train_ratio + val_ratio))
    return values[:train_end], values[train_end:val_end], values[val_end:]


def _make_windows(
    values: np.ndarray, seq_len: int, pred_len: int
) -> np.ndarray:
    """Create sliding windows from a contiguous array using stride tricks.

    Args:
        values: Shape (T,) or (T, C).
        seq_len: Input window length.
        pred_len: Prediction window length.

    Returns:
        Array of shape (N, seq_len + pred_len) for 1-D input, or
        (N, seq_len + pred_len, C) for 2-D input.
    """
    if values.ndim == 1:
        values = values[:, np.newaxis]  # (T, 1)

    window_len = seq_len + pred_len
    T, C = values.shape
    n_windows = T - window_len + 1
    if n_windows <= 0:
        return np.empty((0, window_len, C), dtype=values.dtype)

    # stride_tricks: build (n_windows, window_len, C) view
    stride_t, stride_c = values.strides
    windows = np.lib.stride_tricks.as_strided(
        values,
        shape=(n_windows, window_len, C),
        strides=(stride_t, stride_t, stride_c),
    )
    # Return a contiguous copy so downstream code is safe
    return windows.copy()


# ---------------------------------------------------------------------------
# Main dataloader factories
# ---------------------------------------------------------------------------

def create_dataloaders(
    data_dir: str = DEFAULT_DATA_DIR,
    interval: str = "1D",
    variable: str = "sentiment_polarity",
    seq_len: int = 30,
    pred_len: int = 10,
    batch_size: int = 32,
    use_normalized: bool = True,
    min_event_length: Optional[int] = None,
) -> tuple[DataLoader, DataLoader, DataLoader, dict]:
    """Create pooled train / val / test DataLoaders across all events.

    For each discovered event the series is loaded, split chronologically
    (70 / 10 / 20), and converted to sliding windows.  Windows from all
    events are pooled into unified train / val / test sets.

    Args:
        data_dir: Root data directory.
        interval: Temporal granularity (e.g. "1D", "12H", "6H").
        variable: Target variable name.
        seq_len: Input window length.
        pred_len: Prediction window length.
        batch_size: DataLoader batch size.
        use_normalized: Whether to load z-score normalized series.
        min_event_length: Minimum series length to include an event.
            Defaults to seq_len + pred_len + 10.

    Returns:
        (train_loader, val_loader, test_loader, meta_dict)

        meta_dict keys:
          - event_names: list of included event names
          - per_event_test_indices: dict mapping event_name -> (start, end)
              index range within the pooled test set
          - seq_len: int
          - pred_len: int
    """
    if min_event_length is None:
        min_event_length = seq_len + pred_len

    window_len = seq_len + pred_len
    events = _discover_events(data_dir, interval)

    train_windows_list: list[np.ndarray] = []
    val_windows_list: list[np.ndarray] = []
    test_windows_list: list[np.ndarray] = []
    included_events: list[str] = []
    per_event_test_indices: dict[str, tuple[int, int]] = {}
    test_offset = 0

    for ev in events:
        _, raw_values = load_event_series(
            data_dir, ev, interval, variable, use_normalized
        )
        T = len(raw_values)
        if T < min_event_length:
            continue

        values, train_end, val_end = _split_and_impute(
            raw_values, pred_len=pred_len,
        )
        if not np.isfinite(values).all():
            continue

        all_w = _make_windows(values, seq_len, pred_len)
        if len(all_w) == 0:
            continue

        y_starts = np.arange(len(all_w)) + seq_len
        y_ends = y_starts + pred_len

        train_mask = y_ends <= train_end
        val_mask = (y_starts >= train_end) & (y_ends <= val_end)
        test_mask = y_starts >= val_end

        train_w = all_w[train_mask]
        val_w = all_w[val_mask]
        test_w = all_w[test_mask]

        if len(test_w) == 0:
            continue

        if len(train_w) > 0:
            train_windows_list.append(train_w)
        if len(val_w) > 0:
            val_windows_list.append(val_w)
        test_windows_list.append(test_w)

        included_events.append(ev)
        per_event_test_indices[ev] = (test_offset, test_offset + len(test_w))
        test_offset += len(test_w)

    # Concatenate all windows: shape (N, window_len, C)
    train_windows = (
        np.concatenate(train_windows_list, axis=0)
        if train_windows_list
        else np.empty((0, window_len, 1), dtype=np.float32)
    )
    val_windows = (
        np.concatenate(val_windows_list, axis=0)
        if val_windows_list
        else np.empty((0, window_len, 1), dtype=np.float32)
    )
    test_windows = (
        np.concatenate(test_windows_list, axis=0)
        if test_windows_list
        else np.empty((0, window_len, 1), dtype=np.float32)
    )

    train_ds = _WindowDataset(train_windows, seq_len, pred_len)
    val_ds = _WindowDataset(val_windows, seq_len, pred_len)
    test_ds = _WindowDataset(test_windows, seq_len, pred_len)

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, drop_last=False
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, drop_last=False
    )
    test_loader = DataLoader(
        test_ds, batch_size=batch_size, shuffle=False, drop_last=False
    )

    meta = {
        "event_names": included_events,
        "per_event_test_indices": per_event_test_indices,
        "seq_len": seq_len,
        "pred_len": pred_len,
    }

    return train_loader, val_loader, test_loader, meta


def create_cross_event_dataloaders(
    data_dir: str = DEFAULT_DATA_DIR,
    interval: str = "1D",
    variable: str = "sentiment_polarity",
    seq_len: int = 30,
    pred_len: int = 10,
    held_out_events: list[str] = (),
    batch_size: int = 32,
    use_normalized: bool = True,
    val_ratio: float = 0.1,
) -> tuple[DataLoader, DataLoader, DataLoader, dict]:
    """Create DataLoaders for leave-one-category-out cross-event evaluation.

    Training events contribute ALL their time steps, with a fraction held out
    as validation (for early stopping).  Held-out events are test-only.

    Args:
        data_dir: Root data directory.
        interval: Temporal granularity.
        variable: Target variable name.
        seq_len: Input window length.
        pred_len: Prediction window length.
        held_out_events: List of event names reserved for testing.
        batch_size: DataLoader batch size.
        use_normalized: Whether to load z-score normalized series.
        val_ratio: Fraction of training windows to hold out for validation.

    Returns:
        (train_loader, val_loader, test_loader, meta_dict)
    """
    window_len = seq_len + pred_len
    held_out_set = set(held_out_events)
    events = _discover_events(data_dir, interval)

    train_windows_list: list[np.ndarray] = []
    test_windows_list: list[np.ndarray] = []
    train_event_names: list[str] = []
    test_event_names: list[str] = []
    per_event_test_indices: dict[str, tuple[int, int]] = {}
    test_offset = 0

    for ev in events:
        _, raw_values = load_event_series(
            data_dir, ev, interval, variable, use_normalized
        )
        values = _impute_split_internal(raw_values)
        if not np.isfinite(values).all():
            continue
        windows = _make_windows(values, seq_len, pred_len)
        if len(windows) == 0:
            continue

        if ev in held_out_set:
            test_windows_list.append(windows)
            test_event_names.append(ev)
            per_event_test_indices[ev] = (test_offset, test_offset + len(windows))
            test_offset += len(windows)
        else:
            train_windows_list.append(windows)
            train_event_names.append(ev)

    all_train = (
        np.concatenate(train_windows_list, axis=0)
        if train_windows_list
        else np.empty((0, window_len, 1), dtype=np.float32)
    )
    test_windows = (
        np.concatenate(test_windows_list, axis=0)
        if test_windows_list
        else np.empty((0, window_len, 1), dtype=np.float32)
    )

    # Split training windows into train + val for early stopping
    n_total = len(all_train)
    n_val = max(1, int(n_total * val_ratio))
    # Shuffle before splitting to mix events
    rng = np.random.RandomState(0)
    perm = rng.permutation(n_total)
    val_idx = perm[:n_val]
    train_idx = perm[n_val:]

    train_windows = all_train[train_idx]
    val_windows = all_train[val_idx]

    train_ds = _WindowDataset(train_windows, seq_len, pred_len)
    val_ds = _WindowDataset(val_windows, seq_len, pred_len)
    test_ds = _WindowDataset(test_windows, seq_len, pred_len)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, drop_last=False)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, drop_last=False)

    meta = {
        "train_events": train_event_names,
        "held_out_events": test_event_names,
        "per_event_test_indices": per_event_test_indices,
        "seq_len": seq_len,
        "pred_len": pred_len,
    }

    return train_loader, val_loader, test_loader, meta


# ---------------------------------------------------------------------------
# Internal window dataset (wraps pre-computed window arrays)
# ---------------------------------------------------------------------------

class _WindowDataset(Dataset):
    """Thin Dataset wrapper around a pre-computed (N, window_len, C) array."""

    def __init__(self, windows: np.ndarray, seq_len: int, pred_len: int):
        self.windows = windows.astype(np.float32)
        self.seq_len = seq_len
        self.pred_len = pred_len

    def __len__(self) -> int:
        return len(self.windows)

    def __getitem__(self, idx: int):
        w = self.windows[idx]                        # (window_len, C)
        x = torch.from_numpy(w[: self.seq_len])      # (seq_len, C)
        y = torch.from_numpy(w[self.seq_len :])       # (pred_len, C)
        return x, y
