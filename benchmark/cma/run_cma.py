#!/usr/bin/env python
"""
CMA: encoder-side fusion of per-bin text vectors with a Transformer
encoder time-series backbone.

The encoder output and the per-bin text vectors are aligned on the
lookback axis and fused with a learnable per-position gate::

    enc_out_fused = enc_out + gate * bin_vecs * bin_valid_mask

The gate is initialized to zero. The fused encoder output is mapped
to the horizon by a two-stage MLP with a rolling-average prior
residual.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader

_MMTSFLIB_ROOT = str(
    Path(__file__).resolve().parent.parent.parent
    / "references" / "code" / "MM-TSFlib-main"
)
if _MMTSFLIB_ROOT not in sys.path:
    sys.path.insert(0, _MMTSFLIB_ROOT)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmark.cma.dataset import (
    CMADataset, build_datasets,
    MAX_POSTS, MAX_REPLIES, MAX_TOKENS_PER_BIN,
)
from benchmark.cma.blocks import IntraBinEncoder, TextAuxHead

logger = logging.getLogger(__name__)


class HistoricalFusion(nn.Module):
    """Fuse encoder output with per-bin text vectors at each lookback position.

    enc_out_fused = enc_out + gate * bin_vecs * bin_valid_mask
    The gate is a learnable scalar (or per-position, if per_pos_gate=True).
    Initialized to 0 so fusion is identity at the start of training.

    With mode_aware_gate=True, separate gate parameters for flat and structured
    modes (no_text never reaches this module). Lets the model learn to
    suppress text contribution in flat mode while using it in struct mode.
    """

    def __init__(self, d_model, max_bins, per_pos_gate=False, mode_aware_gate=False):
        super().__init__()
        self.per_pos_gate = per_pos_gate
        self.mode_aware_gate = mode_aware_gate
        n_gates = 2 if mode_aware_gate else 1  # flat / struct
        if per_pos_gate:
            self.gate = nn.Parameter(torch.zeros(n_gates, max_bins))
        else:
            self.gate = nn.Parameter(torch.zeros(n_gates, 1))

    def forward(self, enc_out, bin_vecs, bin_valid, mode_idx=0):
        """
        enc_out:   (B, L, d_model)
        bin_vecs:  (B, L, d_model)
        bin_valid: (B, L) bool
        mode_idx:  0 for flat, 1 for struct (only used when mode_aware_gate)
        """
        bv = bin_vecs * bin_valid.unsqueeze(-1).float()
        if self.mode_aware_gate:
            gate = self.gate[mode_idx]  # (L,) or (1,)
        else:
            gate = self.gate[0]
        if self.per_pos_gate:
            g = gate.view(1, -1, 1)
        else:
            g = gate.view(1, 1, 1)
        return enc_out + g * bv


class EncoderToHorizonMLP(nn.Module):
    """Direct mapping from encoder output (B, L, d_model) to predictions (B, H, c_out).

    Two-stage projection (DLinear-style):
      1. Temporal: linear from L lookback positions to H prediction positions
      2. Feature: per-step MLP from d_model to c_out
    """

    def __init__(self, d_model, seq_len, pred_len, c_out, hidden=None, dropout=0.1):
        super().__init__()
        if hidden is None:
            hidden = d_model
        self.temporal_proj = nn.Linear(seq_len, pred_len)
        self.feat_proj = nn.Sequential(
            nn.Linear(d_model, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, c_out),
        )

    def forward(self, enc_out_fused):
        # (B, L, d_model) -> (B, d_model, L) -> (B, d_model, H) -> (B, H, d_model)
        x = enc_out_fused.transpose(1, 2)
        x = self.temporal_proj(x)
        x = x.transpose(1, 2)
        # Feature MLP: (B, H, d_model) -> (B, H, c_out)
        return self.feat_proj(x)


class CMAModel(nn.Module):
    """Backbone + Stage-1 IntraBinEncoder + encoder-side fusion + aux head.

    With use_decoder=True (default): standard Transformer decoder reads the
    fused encoder output and emits predictions, then output projection +
    prior_y residual.
    With use_decoder=False: the decoder is bypassed entirely; the fused
    encoder output is mapped directly to the H-step prediction sequence by
    EncoderToHorizonMLP.
    """

    def __init__(self, ts_configs, d_bert=768, text_mode="structured_text",
                 use_prior=True, per_pos_gate=False, use_decoder=True,
                 type_pool=False, residual_type_pool=False, n_intra_layers=1,
                 attn_pool=False, mode_aware_gate=False):
        super().__init__()
        from models.Transformer import Model as TFModel

        assert text_mode in ("no_text", "flat_text", "structured_text"), \
            f"unknown text_mode: {text_mode}"
        self.text_mode = text_mode
        self.use_prior = use_prior
        self.use_decoder = use_decoder

        self.tf = TFModel(ts_configs)
        d_model = ts_configs.d_model

        self.intra_bin_encoder = IntraBinEncoder(
            d_model=d_model, d_text=d_bert, max_threads=MAX_POSTS,
            n_heads=4, dropout=0.1, type_pool=type_pool,
            residual_type_pool=residual_type_pool,
            n_intra_layers=n_intra_layers,
            attn_pool=attn_pool,
        )
        self.fusion = HistoricalFusion(
            d_model=d_model, max_bins=ts_configs.seq_len,
            per_pos_gate=per_pos_gate,
            mode_aware_gate=mode_aware_gate,
        )
        self.aux_head = TextAuxHead(
            d_model=d_model, pred_len=ts_configs.pred_len,
            c_out=ts_configs.c_out, dropout=0.1,
        )

        if use_decoder:
            self.out_proj = nn.Linear(d_model, ts_configs.c_out)
            self.horizon_head = None
        else:
            self.out_proj = None
            self.horizon_head = EncoderToHorizonMLP(
                d_model=d_model,
                seq_len=ts_configs.seq_len,
                pred_len=ts_configs.pred_len,
                c_out=ts_configs.c_out,
                dropout=0.1,
            )

        self.pred_len = ts_configs.pred_len
        self.label_len = ts_configs.label_len
        self.seq_len = ts_configs.seq_len

    def forward(self, x, x_mark, y, y_mark,
                text_embs, type_ids, thread_ids, bin_ids, valid_mask, prior_y):
        B = x.size(0)

        # --- Encoder ---
        enc_out = self.tf.enc_embedding(x, x_mark)
        enc_out, _ = self.tf.encoder(enc_out)

        aux_out = None
        if self.text_mode != "no_text":
            # Stage 1: intra-bin self-attention -> bin vectors
            L = self.seq_len
            T = MAX_TOKENS_PER_BIN
            text_emb_BLT = text_embs.view(B, L, T, -1)
            type_BLT = type_ids.view(B, L, T)
            thread_BLT = thread_ids.view(B, L, T)
            valid_BLT = valid_mask.view(B, L, T)

            use_type = (self.text_mode == "structured_text")
            use_thread = (self.text_mode == "structured_text")

            bin_vecs, bin_valid = self.intra_bin_encoder(
                text_emb_BLT, type_BLT, thread_BLT, valid_BLT,
                use_type=use_type, use_thread=use_thread,
            )

            # --- MM-TSFlib-style fusion: text -> encoder output ---
            mode_idx = 1 if self.text_mode == "structured_text" else 0
            enc_out = self.fusion(enc_out, bin_vecs, bin_valid, mode_idx=mode_idx)

            # Auxiliary text-only prediction
            aux_out = self.aux_head(bin_vecs, bin_valid)

        # --- Map fused encoder output to predictions ---
        if self.use_decoder:
            # Standard Transformer decoder
            dec_inp = torch.zeros(B, self.pred_len, x.size(2), device=x.device)
            dec_inp = torch.cat([y[:, :self.label_len, :], dec_inp], dim=1)
            dec_out = self.tf.dec_embedding(dec_inp, y_mark)
            for layer in self.tf.decoder.layers:
                dec_out = layer(dec_out, enc_out)
            if self.tf.decoder.norm is not None:
                dec_out = self.tf.decoder.norm(dec_out)
            dec_out = dec_out[:, -self.pred_len:, :]
            output = self.out_proj(dec_out)
        else:
            # Direct MLP from fused encoder output to (H, c_out)
            output = self.horizon_head(enc_out)

        if self.use_prior:
            output = output + prior_y
        return output, aux_out


def train_and_evaluate(
    model, train_loader, val_loader, test_loader,
    device, lr=1e-4, lr_cma=1e-3, epochs=10, patience=5,
    aux_lambda=0.1,
):
    ts_params = list(model.tf.parameters())
    cma_params = (
        list(model.intra_bin_encoder.parameters())
        + list(model.fusion.parameters())
        + list(model.aux_head.parameters())
    )
    if model.out_proj is not None:
        cma_params += list(model.out_proj.parameters())
    if model.horizon_head is not None:
        cma_params += list(model.horizon_head.parameters())
    opt_ts = torch.optim.Adam(ts_params, lr=lr)
    opt_cma = torch.optim.Adam(cma_params, lr=lr_cma)

    criterion = nn.MSELoss()
    model.to(device)

    best_val = float("inf")
    wait = 0
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        train_losses = []
        for batch in train_loader:
            bx, by, mx, my, prior, tokens, tids, thids, bids, vmask = [
                t.to(device) for t in batch
            ]
            opt_ts.zero_grad()
            opt_cma.zero_grad()
            out, aux = model(bx, mx, by, my, tokens, tids, thids, bids, vmask, prior)
            target = by[:, -model.pred_len:, :]
            loss = criterion(out, target)
            if aux is not None:
                loss = loss + aux_lambda * criterion(aux, target)
            loss.backward()
            opt_ts.step()
            opt_cma.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for batch in val_loader:
                bx, by, mx, my, prior, tokens, tids, thids, bids, vmask = [
                    t.to(device) for t in batch
                ]
                out, _ = model(bx, mx, by, my, tokens, tids, thids, bids, vmask, prior)
                val_losses.append(criterion(out, by[:, -model.pred_len:, :]).item())
        val_loss = np.mean(val_losses) if val_losses else float("inf")
        logger.info("Epoch %d/%d  train=%.6f  val=%.6f",
                     epoch, epochs, np.mean(train_losses), val_loss)

        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                logger.info("Early stopping at epoch %d", epoch)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.to(device)

    model.eval()
    preds, trues = [], []
    with torch.no_grad():
        for batch in test_loader:
            bx, by, mx, my, prior, tokens, tids, thids, bids, vmask = [
                t.to(device) for t in batch
            ]
            out, _ = model(bx, mx, by, my, tokens, tids, thids, bids, vmask, prior)
            preds.append(out.cpu().numpy())
            trues.append(by[:, -model.pred_len:, :].cpu().numpy())

    preds = np.concatenate(preds, axis=0)
    trues = np.concatenate(trues, axis=0)
    mae = np.mean(np.abs(preds - trues))
    mse = np.mean((preds - trues) ** 2)
    return {"MAE": mae, "MSE": mse, "RMSE": np.sqrt(mse), "preds": preds, "trues": trues}


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="CMA v4 training (encoder-side fusion)")
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--emb-path", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 123, 456])
    parser.add_argument("--seq-len", type=int, default=14)
    parser.add_argument("--pred-len", type=int, default=7)
    parser.add_argument("--freq", type=str, default="d")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--lr-cma", type=float, default=1e-3)
    parser.add_argument("--aux-lambda", type=float, default=0.1)
    parser.add_argument("--d-model", type=int, default=512)
    parser.add_argument("--n-heads", type=int, default=8)
    parser.add_argument("--e-layers", type=int, default=2)
    parser.add_argument("--d-layers", type=int, default=1)
    parser.add_argument("--d-ff", type=int, default=2048)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--text-mode",
                        choices=["no_text", "flat_text", "structured_text"],
                        default="structured_text")
    parser.add_argument("--no-prior", action="store_true")
    parser.add_argument("--per-pos-gate", action="store_true",
                        help="Use per-lookback-position gate vector instead of scalar.")
    parser.add_argument("--no-decoder", action="store_true",
                        help="Bypass Transformer decoder; map fused encoder output directly to predictions via MLP.")
    parser.add_argument("--type-pool", action="store_true",
                        help="Use type-conditional dual pooling (mains + replies separately) instead of single mean pool. Forces structural distinction in struct mode.")
    parser.add_argument("--residual-type-pool", action="store_true",
                        help="Use residual form of type-pool: bin_vec = single + alpha * (mixed - single), alpha init=0 so identity at start.")
    parser.add_argument("--n-intra-layers", type=int, default=1,
                        help="Number of intra-bin self-attention layers in IntraBinEncoder (default 1).")
    parser.add_argument("--attn-pool", action="store_true",
                        help="Use learnable [BIN_CLS] attention pool instead of mean pool for bin_vec baseline.")
    parser.add_argument("--mode-aware-gate", action="store_true",
                        help="Use separate fusion gate parameters for flat and structured modes.")
    parser.add_argument("--edge-dir", default=None)
    parser.add_argument("--ts-dir", default=None)
    parser.add_argument("--mae-reply-ks", nargs="+", type=int, default=[5, 10, 20, 50])
    args = parser.parse_args()

    device = (
        f"cuda:{args.gpu}"
        if args.gpu >= 0 and torch.cuda.is_available()
        else "cpu"
    )
    label_len = args.seq_len // 2

    if args.output_dir is None:
        args.output_dir = str(Path(args.csv_path).parent / "cma_v4_results")
    os.makedirs(args.output_dir, exist_ok=True)

    ts_cfg = SimpleNamespace(
        task_name="long_term_forecast", pred_len=args.pred_len,
        seq_len=args.seq_len, label_len=label_len,
        output_attention=False,
        enc_in=1, dec_in=1, c_out=1,
        d_model=args.d_model, n_heads=args.n_heads,
        e_layers=args.e_layers, d_layers=args.d_layers,
        d_ff=args.d_ff, dropout=args.dropout,
        factor=1, embed="timeF", freq=args.freq, activation="gelu",
    )

    all_results = []
    for seed in args.seeds:
        logger.info("=== seed=%d  text_mode=%s ===", seed, args.text_mode)
        torch.manual_seed(seed)
        np.random.seed(seed)

        datasets, scaler = build_datasets(
            args.csv_path, args.emb_path,
            args.seq_len, label_len, args.pred_len, args.freq,
        )
        loaders = {
            k: DataLoader(ds, batch_size=args.batch_size,
                          shuffle=(k == "train"), drop_last=False)
            for k, ds in datasets.items()
        }

        model = CMAModel(ts_cfg, text_mode=args.text_mode,
                           use_prior=not args.no_prior,
                           per_pos_gate=args.per_pos_gate,
                           use_decoder=not args.no_decoder,
                           type_pool=args.type_pool,
                           residual_type_pool=args.residual_type_pool,
                           n_intra_layers=args.n_intra_layers,
                           attn_pool=args.attn_pool,
                           mode_aware_gate=args.mode_aware_gate)
        metrics = train_and_evaluate(
            model, loaders["train"], loaders["val"], loaders["test"],
            device, lr=args.lr, lr_cma=args.lr_cma,
            epochs=args.epochs, patience=args.patience,
            aux_lambda=args.aux_lambda,
        )
        logger.info("seed=%d  MAE=%.6f  MSE=%.6f", seed, metrics["MAE"], metrics["MSE"])

        learned_gate = model.fusion.gate.detach().cpu().tolist()
        if args.text_mode != "no_text":
            logger.info("seed=%d  learned_fusion_gate=%s", seed, learned_gate)

        result = {
            "seed": seed,
            "text_mode": args.text_mode,
            "arch": "v4_encoder_fusion" + ("_nodec" if args.no_decoder else ""),
            "use_prior": not args.no_prior,
            "per_pos_gate": args.per_pos_gate,
            "use_decoder": not args.no_decoder,
            "learned_fusion_gate": learned_gate,
            "MAE": float(metrics["MAE"]),
            "MSE": float(metrics["MSE"]),
            "RMSE": float(metrics["RMSE"]),
        }

        if args.edge_dir and args.ts_dir:
            from benchmark.mae_reply_utils import (
                compute_mae_reply_k,
                compute_pooled_reply_ratios,
                get_test_reply_ratios,
                load_event_map,
            )
            event_map_path = args.csv_path.replace(".csv", "_event_map.json")
            if os.path.exists(event_map_path):
                event_map = load_event_map(event_map_path)
                reply_ratios = compute_pooled_reply_ratios(
                    event_map, args.edge_dir, args.ts_dir, "1D",
                )
                df_tmp = pd.read_csv(args.csv_path)
                ratios = get_test_reply_ratios(
                    reply_ratios, len(df_tmp), args.seq_len, args.pred_len,
                )
                if ratios is not None and len(ratios) > 0:
                    for k_pct in args.mae_reply_ks:
                        mr = compute_mae_reply_k(
                            metrics["preds"], metrics["trues"], ratios, k_pct,
                        )
                        result[f"MAE_reply_{k_pct}"] = float(mr)
                        logger.info("  MAE_reply(%d%%)=%.6f", k_pct, mr)

        all_results.append(result)
        del model
        torch.cuda.empty_cache()

    mean_mae = np.mean([r["MAE"] for r in all_results])
    mean_mse = np.mean([r["MSE"] for r in all_results])
    logger.info("=== MEAN  MAE=%.6f  MSE=%.6f ===", mean_mae, mean_mse)

    results_path = os.path.join(
        args.output_dir,
        f"cma_v4_results_{args.text_mode}.json",
    )
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    logger.info("Saved to %s", results_path)


if __name__ == "__main__":
    main()
