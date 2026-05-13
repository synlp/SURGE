"""End-to-end test of the SURGE benchmark stack against the released data."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))

from benchmark.data_loader import (  # noqa: E402
    create_dataloaders, create_cross_event_dataloaders, load_event_series,
)
from benchmark.evaluate import (  # noqa: E402
    evaluate_predictions, MAE_REPLY_K_PERCENTS,
)
from benchmark.mae_reply_utils import (  # noqa: E402
    compute_event_reply_ratios, extract_test_reply_ratios, mae_reply_topk,
)
from benchmark.train import run_single_experiment  # noqa: E402
from event_config import get_real_events, PAPER_CATEGORIES  # noqa: E402


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ---------------------------------------------------------------------------
# 1. Dataloaders × granularity × variable
# ---------------------------------------------------------------------------

section("1. create_dataloaders × {1D, 12H, 6H} × {DI, SP}")

interval_config = {
    "1D":  {"seq_len": 14, "pred_len": 7,  "expected_in_paper": 55},
    "12H": {"seq_len": 28, "pred_len": 14, "expected_in_paper": 64},
    "6H":  {"seq_len": 56, "pred_len": 28, "expected_in_paper": 67},
}

for interval, cfg in interval_config.items():
    seq_len, pred_len = cfg["seq_len"], cfg["pred_len"]
    for variable in ("comment_count", "sentiment_polarity"):
        train_l, val_l, test_l, meta = create_dataloaders(
            data_dir="data/events",
            interval=interval,
            variable=variable,
            seq_len=seq_len,
            pred_len=pred_len,
            batch_size=32,
        )
        n_events = len(meta["event_names"])
        n_test = sum(end - start for start, end in meta["per_event_test_indices"].values())
        sample_x, sample_y = next(iter(train_l))
        assert not torch.isnan(sample_x).any().item(), \
            f"NaN leaked into X at {interval}/{variable}"
        assert not torch.isnan(sample_y).any().item(), \
            f"NaN leaked into Y at {interval}/{variable}"
        assert sample_x.shape[1] == seq_len
        assert sample_y.shape[1] == pred_len
        assert n_test == len(test_l.dataset), "per_event_test_indices != test loader size"
        print(f"  {interval:>3} / {variable:<20} | events={n_events:2d} (paper expects ≤{cfg['expected_in_paper']}) "
              f"| train={len(train_l.dataset):5d} val={len(val_l.dataset):4d} test={len(test_l.dataset):5d} "
              f"| X={tuple(sample_x.shape)}")


# ---------------------------------------------------------------------------
# 2. Cross-event dataloader (leave-one-category-out)
# ---------------------------------------------------------------------------

section("2. create_cross_event_dataloaders (held-out: natural_disaster, 1D, SP)")

real_events = get_real_events()
held_out_disasters = [
    e.name for e in real_events
    if e.category == "natural_disaster" and "1D" in e.available_granularities
]
print(f"  natural-disaster events held out at 1D: {len(held_out_disasters)}")
ce_train, ce_val, ce_test, ce_meta = create_cross_event_dataloaders(
    data_dir="data/events",
    interval="1D",
    variable="sentiment_polarity",
    seq_len=14, pred_len=7,
    held_out_events=held_out_disasters,
    batch_size=32,
)
print(f"  train events: {len(ce_meta['train_events'])}, "
      f"held-out at test: {len(ce_meta['held_out_events'])}")
print(f"  windows: train={len(ce_train.dataset)} val={len(ce_val.dataset)} test={len(ce_test.dataset)}")
xb, _ = next(iter(ce_train))
assert not torch.isnan(xb).any().item(), "NaN in cross-event train"
xb, _ = next(iter(ce_test))
assert not torch.isnan(xb).any().item(), "NaN in cross-event test"
print("  cross-event loader OK (no NaN)")


# ---------------------------------------------------------------------------
# 3. End-to-end mini-training: linear model on 1D SP
# ---------------------------------------------------------------------------

section("3. End-to-end mini training (linear model, 1D SP, 5 epochs)")


class LinearForecaster(nn.Module):
    """Tiny linear head over the lookback flat to a (pred_len, c_out) horizon.

    Just enough to put the harness through its paces; not a baseline.
    """

    def __init__(self, seq_len: int, pred_len: int, n_features: int):
        super().__init__()
        self.pred_len = pred_len
        self.n_features = n_features
        self.fc = nn.Linear(seq_len * n_features, pred_len * n_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b = x.shape[0]
        flat = x.reshape(b, -1)
        out = self.fc(flat)
        return out.reshape(b, self.pred_len, self.n_features)


train_l, val_l, test_l, meta = create_dataloaders(
    data_dir="data/events",
    interval="1D", variable="sentiment_polarity",
    seq_len=14, pred_len=7, batch_size=32,
)
model = LinearForecaster(seq_len=14, pred_len=7, n_features=1)
result = run_single_experiment(
    model_name="LinearForecaster",
    model=model,
    train_loader=train_l, val_loader=val_l, test_loader=test_l,
    config={"lr": 1e-3, "epochs": 5, "patience": 5, "device": "cpu"},
    seed=42,
)
print(f"  best_val_loss={result['train_info']['best_val_loss']:.4f}")
print(f"  test MAE={result['metrics']['MAE']:.4f}  MSE={result['metrics']['MSE']:.4f}  RMSE={result['metrics']['RMSE']:.4f}")
assert result["metrics"]["MAE"] < 5.0, "MAE wildly off — harness regression"


# ---------------------------------------------------------------------------
# 4. evaluate_predictions with synthetic reply ratios
# ---------------------------------------------------------------------------

section("4. evaluate_predictions with synthetic reply ratios (MAE_reply k ∈ {5,10,20,50})")

rng = np.random.default_rng(0)
n_test = len(test_l.dataset)
y_true = np.zeros((n_test, 7))
y_pred = np.zeros((n_test, 7))
i = 0
for xb, yb in test_l:
    bs = yb.shape[0]
    y_true[i:i + bs] = yb.squeeze(-1).numpy()
    y_pred[i:i + bs] = model(xb).detach().squeeze(-1).numpy()
    i += bs
flat_reply_ratios = rng.uniform(0, 1, size=n_test * 7)
metrics = evaluate_predictions(y_true, y_pred, reply_ratios=flat_reply_ratios)
for k in MAE_REPLY_K_PERCENTS:
    key = f"MAE_reply_{k}"
    assert key in metrics, f"metric {key} missing"
    print(f"  {key:>14} = {metrics[key]:.4f}")


# ---------------------------------------------------------------------------
# 5. mae_reply_utils with synthetic edges.jsonl on a real event
# ---------------------------------------------------------------------------

section("5. mae_reply_utils with synthetic edges.jsonl on a real event")

ts, _ = load_event_series("data/events", "gpt_release", "1D", "comment_count", use_normalized=False)
print(f"  event=gpt_release, 1D, T={len(ts)}")

with tempfile.TemporaryDirectory() as td:
    edges_path = Path(td) / "edges.jsonl"
    n_edges_per_bin = rng.integers(0, 50, size=len(ts))
    with edges_path.open("w", encoding="utf-8") as f:
        for t_str, n in zip(ts, n_edges_per_bin):
            for _ in range(int(n)):
                rec = {
                    "event": "gpt_release", "edge_type": "reply",
                    "source_post_id": "x", "target_post_id": "y",
                    "source_time": t_str, "target_time": t_str,
                    "platform": "synthetic",
                }
                f.write(json.dumps(rec) + "\n")
    rr = compute_event_reply_ratios(
        edges_jsonl_path=str(edges_path),
        comment_count_csv_path="data/events/gpt_release_1D/comment_count.csv",
        timestamps=ts, interval="1D",
    )
    assert rr.shape == (len(ts),)
    rr_test = extract_test_reply_ratios(rr, seq_len=14, pred_len=7)
    print(f"  reply_ratios shape: full={rr.shape}, test_only={rr_test.shape}")
    print(f"  rr nonzero fraction full={np.mean(rr > 0):.3f} test={np.mean(rr_test > 0):.3f}")
    # Construct fake y_true/y_pred for this event's test slice
    n_test_windows = rr_test.shape[0]
    y_true_e = rng.standard_normal((n_test_windows, 7))
    y_pred_e = y_true_e + rng.standard_normal((n_test_windows, 7)) * 0.5
    for k in MAE_REPLY_K_PERCENTS:
        v = mae_reply_topk(y_true_e, y_pred_e, rr_test, k)
        print(f"  MAE_reply_topk({k:>2}%) = {v:.4f}")


# ---------------------------------------------------------------------------
# 6. Released textual artifacts: schema + cross-consistency
# ---------------------------------------------------------------------------

section("6. Released textual artifacts: schema + cross-consistency on 34 events")

phase_d = json.load(open("tests/phase_d_events.json", encoding="utf-8"))
selected = phase_d["events"]
event_md = json.load(open("data/events/event_metadata.json", encoding="utf-8"))["events"]
gran_map = {e["name"]: e["available_granularities"] for e in event_md}

assert len(selected) == 34, f"expected 34 selected events, got {len(selected)}"

n_total_lookup = 0
n_total_edges = 0
n_total_textview_bins = 0
events_with_empty_edges = []

for ev in selected:
    ev_dir = Path(f"data/events/{ev}")

    # 6a. post_id_lookup.jsonl
    lookup_pids = set()
    n_lookup_rows = 0
    with (ev_dir / "post_id_lookup.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            for k in ("post_id", "platform", "url"):
                assert k in r, f"{ev}: lookup row missing {k}: {r}"
            lookup_pids.add(r["post_id"])
            n_lookup_rows += 1
    assert len(lookup_pids) == n_lookup_rows, \
        f"{ev}: {n_lookup_rows - len(lookup_pids)} duplicate post_ids in lookup"
    n_total_lookup += n_lookup_rows

    # 6b. edges.jsonl
    edges_pids = set()
    n_edges = 0
    with (ev_dir / "edges.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            assert r["event"] == ev, f"{ev}: edges row event mismatch: {r['event']}"
            for k in ("edge_type", "source_post_id", "target_post_id",
                      "source_time", "target_time", "platform"):
                assert k in r, f"{ev}: edge missing {k}"
            edges_pids.add(r["source_post_id"])
            edges_pids.add(r["target_post_id"])
            n_edges += 1
    if n_edges == 0:
        events_with_empty_edges.append(ev)
    n_total_edges += n_edges

    # 6c. text_view.jsonl across granularities
    textview_pids = set()
    n_bins_this_event = 0
    for g in gran_map.get(ev, []):
        bin_dir = Path(f"data/events/{ev}_{g}")
        if not (bin_dir / "text_view.jsonl").exists():
            continue
        with (bin_dir / "text_view.jsonl").open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                assert r["event"] == ev
                assert r["granularity"] == g
                for k in ("bin_start", "bin_end", "n_posts_in_bin", "main_posts"):
                    assert k in r, f"{ev}/{g}: text_view missing {k}"
                assert r["n_posts_in_bin"] >= 0
                assert len(r["main_posts"]) <= 3, \
                    f"{ev}/{g}: more than 3 main posts in a bin"
                for mp in r["main_posts"]:
                    assert "post_id" in mp and "replies" in mp
                    textview_pids.add(mp["post_id"])
                    assert len(mp["replies"]) <= 2, \
                        f"{ev}/{g}: more than 2 replies under one main"
                    for rp in mp["replies"]:
                        textview_pids.add(rp["post_id"])
                n_bins_this_event += 1
    n_total_textview_bins += n_bins_this_event

    # 6d. cross-consistency: every referenced post_id resolves in lookup
    referenced = textview_pids | edges_pids
    unresolved = referenced - lookup_pids
    assert not unresolved, \
        f"{ev}: {len(unresolved)} referenced post_ids not in lookup " \
        f"(sample: {list(unresolved)[:3]})"

print(f"  walked all {len(selected)} events without schema or consistency errors")
print(f"  totals: lookup_rows={n_total_lookup}  edges={n_total_edges}  textview_bins={n_total_textview_bins}")
if events_with_empty_edges:
    print(f"  events with 0 edges (source had no edges.csv): {events_with_empty_edges}")


# ---------------------------------------------------------------------------
# 7. mae_reply_utils on a real released edges.jsonl (no synthetic data)
# ---------------------------------------------------------------------------

section("7. mae_reply_utils on real released edges.jsonl (gpt_release, 1D)")

ts_real, _ = load_event_series("data/events", "gpt_release", "1D",
                                "comment_count", use_normalized=False)
rr_real = compute_event_reply_ratios(
    edges_jsonl_path="data/events/gpt_release/edges.jsonl",
    comment_count_csv_path="data/events/gpt_release_1D/comment_count.csv",
    timestamps=ts_real, interval="1D",
)
assert rr_real.shape == (len(ts_real),)
assert (rr_real >= 0).all(), "reply ratios must be non-negative"
print(f"  T={len(ts_real)}  rr nonzero fraction={float(np.mean(rr_real > 0)):.3f}  "
      f"mean={float(np.mean(rr_real)):.3f}  max={float(np.max(rr_real)):.3f}")
rr_test_real = extract_test_reply_ratios(rr_real, seq_len=14, pred_len=7)
assert rr_test_real.shape[1] == 7
print(f"  test windows={rr_test_real.shape[0]}  rr_test nonzero={float(np.mean(rr_test_real > 0)):.3f}")


# ---------------------------------------------------------------------------
# 8. hydrate.py: lookup loading + neutral NotImplementedError contract
# ---------------------------------------------------------------------------

section("8. hydrate.py: lookup loading + fetcher contract")

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import hydrate  # noqa: E402

lookup_real = hydrate._load_lookup(Path("data/events/gpt_release"))
print(f"  loaded gpt_release lookup: {len(lookup_real)} post IDs")
assert len(lookup_real) > 0
sample_pid = next(iter(lookup_real))
assert "platform" in lookup_real[sample_pid] and "url" in lookup_real[sample_pid]

for fetcher_name in ("fetch_twitter", "fetch_reddit", "fetch_threads"):
    fetcher = getattr(hydrate, fetcher_name)
    try:
        fetcher(["dummy_id"], {"dummy_id": "https://example.com/x"})
    except NotImplementedError as exc:
        msg = str(exc)
        assert msg, f"{fetcher_name} raised empty NotImplementedError"
        print(f"  {fetcher_name}: NotImplementedError -> '{msg[:60]}...'")
    else:
        raise AssertionError(f"{fetcher_name} did not raise NotImplementedError")


print("\nAll end-to-end checks passed.")
