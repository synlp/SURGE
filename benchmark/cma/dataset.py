"""CMA dataset and dataloader factory.

Builds ``(train, val, test)`` datasets that pair the per-event
chronological 70 / 10 / 20 split with precomputed text embeddings.

Inputs:

* ``csv_path`` — pooled (event-by-row) CSV with columns ``date``,
  ``OT`` (target series), ``prior_history_avg`` (rolling-average prior).
* ``emb_path`` — ``.npz`` archive with arrays ``main_embs`` (per-bin
  BERT [CLS] embeddings of up to ``K_post=3`` main posts),
  ``reply_embs`` (up to ``K_reply=2`` replies per main post),
  ``n_posts`` (per-bin main post count), ``n_replies`` (per-bin
  per-thread reply count).

Per-bin token capacity is ``T_max = K_post * (1 + K_reply) = 9``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from torch.utils.data import Dataset

_MMTSFLIB_ROOT = str(
    Path(__file__).resolve().parent.parent.parent
    / "references" / "code" / "MM-TSFlib-main"
)
if _MMTSFLIB_ROOT not in sys.path:
    sys.path.insert(0, _MMTSFLIB_ROOT)


MAX_POSTS = 3
MAX_REPLIES = 2
MAX_TOKENS_PER_BIN = MAX_POSTS * (1 + MAX_REPLIES)  # 9


class CMADataset(Dataset):
    """Per-sample loader pairing the time-series window with text tokens
    drawn from all ``L`` lookback bins jointly.

    For each sample index ``s``, this class returns:

    * ``seq_x``: encoder input, shape ``(seq_len, c_in)``
    * ``seq_y``: decoder input + horizon target, shape
      ``(label_len + pred_len, c_out)``
    * ``mark_x`` / ``mark_y``: time-feature embeddings for the same
      windows, shape ``(seq_len, n_time_feats)`` and
      ``(label_len + pred_len, n_time_feats)``.
    * ``prior_y``: rolling-average prior for the horizon, shape
      ``(pred_len, c_out)``, added as a residual after the
      encoder-to-horizon MLP.
    * ``tokens``: text token embeddings for the lookback, shape
      ``(L * T_max, d_text)`` in bin-major order.
    * ``type_ids``: per-token type indicator (0 = main post, 1 = reply),
      shape ``(L * T_max,)``.
    * ``thread_ids``: per-token thread indicator within bin (which
      ``main_<k>`` thread the token belongs to), shape ``(L * T_max,)``.
    * ``bin_ids``: which lookback bin a token came from, shape
      ``(L * T_max,)``.
    * ``valid``: per-token validity mask, shape ``(L * T_max,)``.
    """

    def __init__(
        self, data, data_prior, data_stamp,
        main_embs, reply_embs, n_posts_arr, n_replies_arr,
        seq_len, label_len, pred_len, border,
    ):
        self.data = data
        self.prior = data_prior
        self.stamp = data_stamp
        self.main_embs = main_embs
        self.reply_embs = reply_embs
        self.n_posts = n_posts_arr
        self.n_replies = n_replies_arr
        self.seq_len = seq_len
        self.label_len = label_len
        self.pred_len = pred_len
        self.border = border
        self.tot_len = len(data) - seq_len - pred_len + 1

    def __len__(self):
        return max(0, self.tot_len)

    def _flatten_one_bin(self, abs_pos):
        """Flatten one bin into ``(T_max, D)`` plus per-token type/thread ids."""
        me = self.main_embs[abs_pos]      # (K, D)
        re = self.reply_embs[abs_pos]     # (K, R, D)
        np_ = int(self.n_posts[abs_pos])
        nr = self.n_replies[abs_pos]      # (K,)
        D = me.shape[-1]

        tokens = np.zeros((MAX_TOKENS_PER_BIN, D), dtype=np.float32)
        type_ids = np.zeros(MAX_TOKENS_PER_BIN, dtype=np.int64)
        thread_ids = np.zeros(MAX_TOKENS_PER_BIN, dtype=np.int64)
        n_valid = 0
        for k in range(min(np_, MAX_POSTS)):
            tokens[n_valid] = me[k]
            type_ids[n_valid] = 0  # main post
            thread_ids[n_valid] = k
            n_valid += 1
            for r in range(min(int(nr[k]), MAX_REPLIES)):
                tokens[n_valid] = re[k, r]
                type_ids[n_valid] = 1  # reply
                thread_ids[n_valid] = k
                n_valid += 1
        return tokens, type_ids, thread_ids, n_valid

    def _gather_lookback_text(self, s):
        """Gather text from all ``L`` lookback bins ``[border+s, border+s+L-1]``."""
        L = self.seq_len
        D = self.main_embs.shape[-1]
        tokens_LT = np.zeros((L, MAX_TOKENS_PER_BIN, D), dtype=np.float32)
        type_LT = np.zeros((L, MAX_TOKENS_PER_BIN), dtype=np.int64)
        thread_LT = np.zeros((L, MAX_TOKENS_PER_BIN), dtype=np.int64)
        n_tok_L = np.zeros(L, dtype=np.int64)
        for li in range(L):
            abs_pos = self.border + s + li
            tk, tid, thid, nv = self._flatten_one_bin(abs_pos)
            tokens_LT[li] = tk
            type_LT[li] = tid
            thread_LT[li] = thid
            n_tok_L[li] = nv
        return tokens_LT, type_LT, thread_LT, n_tok_L

    def __getitem__(self, idx):
        s = idx
        e = s + self.seq_len
        r0 = e - self.label_len
        r1 = r0 + self.label_len + self.pred_len

        seq_x = self.data[s:e].astype(np.float32)
        seq_y = self.data[r0:r1].astype(np.float32)
        mark_x = self.stamp[s:e].astype(np.float32)
        mark_y = self.stamp[r0:r1].astype(np.float32)
        prior_y = self.prior[e:e + self.pred_len].astype(np.float32)

        tokens_LT, type_LT, thread_LT, n_tok_L = self._gather_lookback_text(s)
        L = self.seq_len
        T = MAX_TOKENS_PER_BIN
        tokens = tokens_LT.reshape(L * T, -1)
        type_ids = type_LT.reshape(L * T)
        thread_ids = thread_LT.reshape(L * T)
        bin_ids = np.repeat(np.arange(L, dtype=np.int64), T)
        within = np.tile(np.arange(T, dtype=np.int64), L)
        n_tok_expanded = np.repeat(n_tok_L, T)
        valid = (within < n_tok_expanded).astype(np.bool_)

        return (
            seq_x, seq_y, mark_x, mark_y, prior_y,
            tokens, type_ids, thread_ids, bin_ids, valid,
        )


def build_datasets(csv_path, emb_path, seq_len, label_len, pred_len, freq="d"):
    """Build train / val / test :class:`CMADataset` instances.

    Returns:
        ``(datasets, scaler)`` where ``datasets`` is a dict keyed by
        ``"train" / "val" / "test"`` and ``scaler`` is the
        :class:`~sklearn.preprocessing.StandardScaler` fitted on the
        train split only.
    """
    from utils.timefeatures import time_features as compute_tf

    df = pd.read_csv(csv_path)
    n = len(df)
    emb = np.load(emb_path)

    scaler = StandardScaler()
    num_train = int(n * 0.7)
    num_test = int(n * 0.2)
    b1s = [0, num_train - seq_len, n - num_test - seq_len]
    b2s = [num_train, num_train + (n - num_train - num_test), n]

    ot = df[["OT"]].values
    prior = df[["prior_history_avg"]].values
    scaler.fit(ot[b1s[0]:b2s[0]])
    ot_s = scaler.transform(ot)
    pr_s = scaler.transform(prior)

    datasets = {}
    for flag, i in [("train", 0), ("val", 1), ("test", 2)]:
        b1, b2 = b1s[i], b2s[i]
        stamp_df = df[["date"]].iloc[b1:b2].copy()
        stamp_df["date"] = pd.to_datetime(stamp_df["date"])
        stamp = compute_tf(pd.to_datetime(stamp_df["date"].values), freq=freq).T

        datasets[flag] = CMADataset(
            data=ot_s[b1:b2], data_prior=pr_s[b1:b2], data_stamp=stamp,
            main_embs=emb["main_embs"], reply_embs=emb["reply_embs"],
            n_posts_arr=emb["n_posts"], n_replies_arr=emb["n_replies"],
            seq_len=seq_len, label_len=label_len, pred_len=pred_len, border=b1,
        )
    return datasets, scaler
