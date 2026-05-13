"""Unit tests for the dataloader's split-boundary and imputation logic."""

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

from benchmark.data_loader import (  # noqa: E402
    _impute_split_internal,
    _last_finite_row,
    _split_and_impute,
)


# ---------------------------------------------------------------------------
# _impute_split_internal
# ---------------------------------------------------------------------------

def test_impute_basic_ffill_bfill():
    seg = np.array([np.nan, 1.0, np.nan, 3.0, np.nan])
    out = _impute_split_internal(seg)
    np.testing.assert_array_equal(out, [1.0, 1.0, 1.0, 3.0, 3.0])


def test_impute_all_nan_no_seed_stays_nan():
    seg = np.array([np.nan, np.nan, np.nan])
    out = _impute_split_internal(seg)
    assert np.isnan(out).all()


def test_impute_all_nan_with_seed_becomes_constant_seed():
    seg = np.array([np.nan, np.nan, np.nan])
    out = _impute_split_internal(seg, seed=5.0)
    np.testing.assert_array_equal(out, [5.0, 5.0, 5.0])


def test_impute_partial_nan_ignores_seed():
    """seed only kicks in when the whole segment is NaN."""
    seg = np.array([np.nan, 2.0, np.nan])
    out = _impute_split_internal(seg, seed=99.0)
    np.testing.assert_array_equal(out, [2.0, 2.0, 2.0])


def test_impute_empty_segment():
    out = _impute_split_internal(np.array([]), seed=1.0)
    assert out.size == 0


# ---------------------------------------------------------------------------
# _last_finite_row
# ---------------------------------------------------------------------------

def test_last_finite_row_1d():
    assert _last_finite_row(np.array([1.0, 2.0, np.nan])) == 2.0
    assert _last_finite_row(np.array([np.nan, np.nan])) is None
    assert _last_finite_row(np.array([])) is None


# ---------------------------------------------------------------------------
# _split_and_impute split boundaries
# ---------------------------------------------------------------------------

def _basic_series(T: int) -> np.ndarray:
    return np.arange(1, T + 1, dtype=np.float64)


def test_split_long_event_uses_int_T_dot_8():
    v = _basic_series(100)
    _, train_end, val_end = _split_and_impute(v, pred_len=7)
    assert train_end == 70
    assert val_end == 80


def test_split_short_event_pulls_val_end_to_T_minus_pred():
    v = _basic_series(21)
    _, train_end, val_end = _split_and_impute(v, pred_len=7)
    assert train_end == 14
    assert val_end == 14


def test_split_strict_border_keeps_int_T_dot_8():
    v = _basic_series(21)
    _, train_end, val_end = _split_and_impute(v, pred_len=7, relaxed_border=False)
    assert val_end == 16


def test_split_val_end_caps_at_train_end():
    v = _basic_series(10)
    _, train_end, val_end = _split_and_impute(v, pred_len=8)
    assert train_end == 7
    assert val_end == 7


# ---------------------------------------------------------------------------
# _split_and_impute NaN handling
# ---------------------------------------------------------------------------

def test_split_seeds_empty_segment_from_previous():
    v = np.array([1.0, 2.0, 3.0, 4.0, 5.0,
                  6.0, 7.0, 8.0, 9.0, 10.0,
                  11.0, 12.0, 13.0, 14.0,
                  np.nan, np.nan,
                  np.nan, np.nan, np.nan, np.nan])
    out, _, _ = _split_and_impute(v, pred_len=2, relaxed_border=False)
    assert np.isfinite(out).all()
    np.testing.assert_array_equal(out[14:], [14.0] * 6)


def test_split_without_seed_leaves_empty_segment_nan():
    v = np.array([1.0, 2.0, 3.0, 4.0, 5.0,
                  6.0, 7.0, 8.0, 9.0, 10.0,
                  11.0, 12.0, 13.0, 14.0,
                  np.nan, np.nan,
                  np.nan, np.nan, np.nan, np.nan])
    out, _, _ = _split_and_impute(
        v, pred_len=2, nan_tolerance=False, relaxed_border=False,
    )
    assert np.isnan(out[14:]).all()
    np.testing.assert_array_equal(out[:14], v[:14])


if __name__ == "__main__":
    # Allow direct execution without pytest.
    fns = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
