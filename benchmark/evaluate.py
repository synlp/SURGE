"""Evaluation metrics for the SURGE benchmark."""

import numpy as np

MAE_REPLY_K_PERCENTS: tuple[int, ...] = (5, 10, 20, 50)


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error.

    Args:
        y_true: ground truth, shape (N,) or (N, C).
        y_pred: predictions, same shape as y_true.

    Returns:
        Scalar MAE value.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    if y_true.size == 0:
        return np.nan
    return float(np.mean(np.abs(y_true - y_pred)))


def mse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Squared Error.

    Args:
        y_true: ground truth, shape (N,) or (N, C).
        y_pred: predictions, same shape as y_true.

    Returns:
        Scalar MSE value.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    if y_true.size == 0:
        return np.nan
    return float(np.mean((y_true - y_pred) ** 2))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error.

    Args:
        y_true: ground truth, shape (N,) or (N, C).
        y_pred: predictions, same shape as y_true.

    Returns:
        Scalar RMSE value.
    """
    return float(np.sqrt(mse(y_true, y_pred)))


def mae_reply(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    reply_ratios: np.ndarray,
    k_percent: int,
) -> float:
    """Structure-aware MAE on the top-k% time steps by reply ratio.

    Pools every prediction time step across all test windows, ranks by
    per-step reply ratio, keeps the top ``k_percent`` slice, and reports
    MAE on that slice.

    Args:
        y_true: ground truth, shape ``(N, pred_len)`` or
            ``(N, pred_len, C)``. ``N`` is the number of test windows.
        y_pred: same shape as ``y_true``.
        reply_ratios: per-time-step reply ratios, shape
            ``(N, pred_len)`` or any 1-D array whose length matches the
            total number of prediction steps after flattening
            ``y_true``.
        k_percent: percentage threshold.

    Returns:
        MAE on the top-k% slice, or ``np.nan`` when ``reply_ratios``
        is ``None`` or empty.
    """
    if reply_ratios is None:
        return np.nan
    rr = np.asarray(reply_ratios, dtype=np.float64).ravel()
    if rr.size == 0:
        return np.nan

    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)

    # Flatten everything to (n_steps,) or (n_steps, C).
    if y_true.ndim >= 3:
        # (N, pred_len, C) -> (N*pred_len, C)
        c = y_true.shape[-1]
        yt = y_true.reshape(-1, c)
        yp = y_pred.reshape(-1, c)
    else:
        yt = y_true.reshape(-1)
        yp = y_pred.reshape(-1)

    if rr.shape[0] != yt.shape[0]:
        raise ValueError(
            f"reply_ratios length {rr.shape[0]} does not match "
            f"flattened y_true length {yt.shape[0]}; expected one "
            f"reply_ratio per prediction time step."
        )

    n = rr.shape[0]
    top_k = max(1, int(np.ceil(n * k_percent / 100.0)))
    top_indices = np.argsort(rr)[-top_k:]
    return mae(yt[top_indices], yp[top_indices])


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    reply_ratios: np.ndarray = None,
) -> dict:
    """Compute all metrics for a single prediction.

    Args:
        y_true: ground truth, shape (N,) or (N, C).
        y_pred: predictions, same shape as y_true.
        reply_ratios: optional 1-D array of length N.

    Returns:
        Dict with keys "MAE", "MSE", "RMSE", and optionally
        "MAE_reply_<k>" for each k in :data:`MAE_REPLY_K_PERCENTS`.
    """
    results = {
        "MAE": mae(y_true, y_pred),
        "MSE": mse(y_true, y_pred),
        "RMSE": rmse(y_true, y_pred),
    }

    if reply_ratios is not None:
        ratios = np.asarray(reply_ratios).ravel()
        if ratios.size > 0:
            for k in MAE_REPLY_K_PERCENTS:
                results[f"MAE_reply_{k}"] = mae_reply(
                    y_true, y_pred, reply_ratios, k
                )

    return results


def evaluate_per_event(
    y_true_list: list,
    y_pred_list: list,
    reply_ratios_list: list = None,
) -> tuple:
    """Compute per-event metrics and their averages.

    Args:
        y_true_list: list of arrays, one per event.
        y_pred_list: list of arrays, one per event.
        reply_ratios_list: optional list of 1-D arrays, one per event.

    Returns:
        (per_event_results, averaged_results) where per_event_results is a
        list of dicts and averaged_results is a dict with the same keys
        containing the mean across events (NaN values are ignored).
    """
    per_event_results = []
    for i in range(len(y_true_list)):
        rr = None if reply_ratios_list is None else reply_ratios_list[i]
        per_event_results.append(
            evaluate_predictions(y_true_list[i], y_pred_list[i], rr)
        )

    if not per_event_results:
        return per_event_results, {}

    # collect all metric keys that appear in any event
    all_keys = set()
    for d in per_event_results:
        all_keys.update(d.keys())

    averaged_results = {}
    for key in sorted(all_keys):
        values = [d[key] for d in per_event_results if key in d]
        # ignore NaN when averaging
        averaged_results[key] = float(np.nanmean(values))

    return per_event_results, averaged_results
