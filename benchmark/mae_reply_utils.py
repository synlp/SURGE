"""Utilities for the structure-aware MAE_reply metric.

* :func:`compute_event_reply_ratios` reads an event's reply / repost
  edge list (JSONL, schema documented in ``schema/edges.md``) and the
  paired ``comment_count.csv``, then derives a per-bin reply ratio
  ``r_t = edge_count_t / post_count_t`` aligned with the time-series
  timestamps.

* :func:`extract_test_reply_ratios` extracts, for each test window of
  an event, the per-step reply ratios at the prediction positions,
  yielding an array shaped ``(N_test, pred_len)`` that pairs one-to-one
  with ``y_true`` / ``y_pred`` from the dataloader.

* :func:`mae_reply_topk` picks the top ``k%`` of test time steps by
  reply ratio and returns MAE on those steps.

Edge records follow ``schema/edges.md``. The metric only uses
``source_time`` (the time of the responding post) for binning.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from common.io_utils import iter_jsonl


# ---------------------------------------------------------------------------
# Bin alignment
# ---------------------------------------------------------------------------

def _floor_timestamp(ts: pd.Timestamp, interval: str) -> pd.Timestamp:
    """Floor a timestamp to the start of the bin matching the given interval."""
    if interval == "1D":
        return ts.normalize()
    if interval == "12H":
        hour = (ts.hour // 12) * 12
        return ts.replace(hour=hour, minute=0, second=0, microsecond=0)
    if interval == "6H":
        hour = (ts.hour // 6) * 6
        return ts.replace(hour=hour, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unsupported interval: {interval}")


# ---------------------------------------------------------------------------
# Reply-ratio computation (per event)
# ---------------------------------------------------------------------------

def compute_event_reply_ratios(
    edges_jsonl_path: str,
    comment_count_csv_path: str,
    timestamps: list[str],
    interval: str,
) -> np.ndarray:
    """Compute ``r_t = edge_count[t] / post_count[t]`` for every bin of an event.

    Args:
        edges_jsonl_path: Path to the event's ``edges.jsonl`` file. If
            the file is missing, a zero-filled vector is returned.
        comment_count_csv_path: Path to the event's ``comment_count.csv``
            (raw, not normalized). Required for the per-bin post count.
        timestamps: List of bin-start time strings exactly matching the
            time series the predictions will be aligned with (typically
            obtained from :func:`benchmark.data_loader.load_event_series`).
        interval: One of ``"6H"``, ``"12H"``, ``"1D"``.

    Returns:
        1-D ``np.ndarray`` of length ``len(timestamps)``. Bins with zero
        observed posts (``post_count_t == 0``) get ``0.0``.
    """
    T = len(timestamps)
    if T == 0:
        return np.zeros(0, dtype=np.float64)

    if not os.path.exists(edges_jsonl_path):
        return np.zeros(T, dtype=np.float64)

    if not os.path.exists(comment_count_csv_path):
        return np.zeros(T, dtype=np.float64)

    cc_df = pd.read_csv(comment_count_csv_path)
    cc_times = pd.to_datetime(cc_df["time"])
    cc_values = cc_df["count"].fillna(0.0).to_numpy()
    post_count_map: dict[pd.Timestamp, float] = dict(zip(cc_times, cc_values))

    # Bin every edge by its source_time (responding post) and tally per bin.
    edge_bin_counts: dict[pd.Timestamp, int] = {}
    for edge in iter_jsonl(edges_jsonl_path):
        src = edge.get("source_time")
        if not src:
            continue
        try:
            t = pd.to_datetime(src)
        except (ValueError, TypeError):
            continue
        bin_start = _floor_timestamp(t, interval)
        edge_bin_counts[bin_start] = edge_bin_counts.get(bin_start, 0) + 1

    ts_index = pd.to_datetime(timestamps)
    reply_ratios = np.zeros(T, dtype=np.float64)
    for i, t in enumerate(ts_index):
        ec = edge_bin_counts.get(t, 0)
        pc = post_count_map.get(t, 0.0)
        if pc > 0:
            reply_ratios[i] = ec / pc
    return reply_ratios


# ---------------------------------------------------------------------------
# Test-window reply-ratio extraction
# ---------------------------------------------------------------------------

def extract_test_reply_ratios(
    reply_ratios: np.ndarray,
    seq_len: int,
    pred_len: int,
    *,
    train_ratio: float = 0.7,
    val_ratio: float = 0.1,
    relaxed_border: bool = True,
) -> np.ndarray:
    """Extract reply ratios at each test window's Y positions.

    Uses the same border-based 70 / 10 / 20 split logic as
    :func:`benchmark.data_loader.create_dataloaders`. When the standard
    ``int(T * (train_ratio + val_ratio))`` would leave fewer than
    ``pred_len`` bins for the test slice, ``val_end`` is pulled back
    to ``T - pred_len``.

    Returns:
        ``np.ndarray`` of shape ``(N_test, pred_len)`` aligned with the
        per-window ``y_true`` / ``y_pred`` produced by the standard
        evaluator. If no test windows fit, returns an empty array.
    """
    T = len(reply_ratios)
    train_end = int(T * train_ratio)
    val_end_strict = int(T * (train_ratio + val_ratio))
    if relaxed_border and val_end_strict > T - pred_len:
        val_end = max(train_end, T - pred_len)
    else:
        val_end = val_end_strict
    window_len = seq_len + pred_len
    n_windows = T - window_len + 1
    if n_windows <= 0:
        return np.empty((0, pred_len), dtype=np.float64)

    y_starts = np.arange(n_windows) + seq_len
    test_mask = y_starts >= val_end
    test_indices = np.where(test_mask)[0]
    if len(test_indices) == 0:
        return np.empty((0, pred_len), dtype=np.float64)

    out = np.zeros((len(test_indices), pred_len), dtype=np.float64)
    for j, wi in enumerate(test_indices):
        y_start = wi + seq_len
        out[j] = reply_ratios[y_start : y_start + pred_len]
    return out


# ---------------------------------------------------------------------------
# Top-k MAE
# ---------------------------------------------------------------------------

def mae_reply_topk(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    reply_ratios_test: np.ndarray,
    k_percent: int,
) -> float:
    """MAE on the top-``k_percent``% time steps ranked by reply ratio.

    Args:
        y_true: shape ``(N, pred_len)`` or ``(N, pred_len, C)``.
        y_pred: same shape as ``y_true``.
        reply_ratios_test: shape ``(N, pred_len)`` from
            :func:`extract_test_reply_ratios`.
        k_percent: integer in ``[1, 100]``. The paper reports
            ``{5, 10, 20, 50}``.

    Returns:
        Scalar MAE on the top-k% slice, or ``np.nan`` when no steps fit.
    """
    if reply_ratios_test.size == 0:
        return float("nan")

    if y_true.ndim == 2:
        y_true_flat = y_true.reshape(-1)
        y_pred_flat = y_pred.reshape(-1)
    else:
        y_true_flat = y_true.reshape(-1, y_true.shape[-1])
        y_pred_flat = y_pred.reshape(-1, y_pred.shape[-1])
    rr_flat = reply_ratios_test.reshape(-1)

    n = rr_flat.shape[0]
    top_k = max(1, int(np.ceil(n * k_percent / 100.0)))
    top_indices = np.argsort(rr_flat)[-top_k:]

    if y_true_flat.ndim == 1:
        sel_true = y_true_flat[top_indices]
        sel_pred = y_pred_flat[top_indices]
    else:
        sel_true = y_true_flat[top_indices]
        sel_pred = y_pred_flat[top_indices]
    return float(np.mean(np.abs(sel_true - sel_pred)))
