"""CMA building blocks: intra-bin encoder and text-only auxiliary head.

Both blocks correspond directly to the paper's Appendix E
specification.

* :class:`IntraBinEncoder` — Stage 1 of the cross-modal pathway:
  within-bin self-attention over up to ``T_max = 9`` post tokens with
  type and thread embeddings, followed by a learnable [BIN_CLS]
  attention pool and an optional type-conditional residual pool.
* :class:`TextAuxHead` — Auxiliary supervised head that predicts the
  horizon target from the per-bin text vectors alone, providing direct
  gradient signal to the cross-modal pathway during training.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class IntraBinEncoder(nn.Module):
    """Stage 1: within-bin self-attention + learnable pool.

    Each bin has at most ``T_max = K_post * (1 + K_reply) = 9`` post
    tokens. Per-bin self-attention with type and thread embeddings lets
    tokens attend to their thread-mates and other tokens within the
    same bin, producing a structure-aware bin representation. The bin
    is then summarized by a learnable [BIN_CLS] attention query
    (``attn_pool=True``) or by a masked mean. An optional
    type-conditional residual pool keeps the main-post and reply
    contributions explicitly separable when ``type_pool=True`` and
    ``residual_type_pool=True``.
    """

    def __init__(self, d_model, d_text, max_threads, n_heads=4, dropout=0.1,
                 type_pool=False, residual_type_pool=False, n_intra_layers=1,
                 attn_pool=False):
        super().__init__()
        self.type_pool = type_pool
        self.residual_type_pool = residual_type_pool
        self.n_intra_layers = n_intra_layers
        self.attn_pool = attn_pool
        self.text_proj = nn.Linear(d_text, d_model)
        self.type_embedding = nn.Embedding(2, d_model)
        self.thread_embedding = nn.Embedding(max_threads, d_model)
        self.intra_attn_layers = nn.ModuleList([
            nn.MultiheadAttention(
                embed_dim=d_model, num_heads=n_heads, dropout=dropout,
                batch_first=True,
            ) for _ in range(n_intra_layers)
        ])
        self.intra_norm_layers = nn.ModuleList([
            nn.LayerNorm(d_model) for _ in range(n_intra_layers)
        ])
        # Backward-compat aliases for single-layer access
        self.intra_attn = self.intra_attn_layers[0]
        self.intra_norm = self.intra_norm_layers[0]
        if attn_pool:
            self.bin_cls = nn.Parameter(torch.zeros(d_model))
            self.bin_pool_attn = nn.MultiheadAttention(
                embed_dim=d_model, num_heads=n_heads, dropout=dropout,
                batch_first=True,
            )
        if type_pool:
            self.type_pool_mix = nn.Linear(2 * d_model, d_model)
            if residual_type_pool:
                self.type_pool_alpha = nn.Parameter(torch.zeros(1))

    def forward(self, text_embs, type_ids, thread_ids, valid_mask,
                use_type=True, use_thread=True):
        """
        text_embs:  (B, L, T_max, d_text)
        type_ids:   (B, L, T_max)
        thread_ids: (B, L, T_max)
        valid_mask: (B, L, T_max)  True = valid token
        Returns:    (bin_vec, bin_valid) with shapes (B, L, d_model) and (B, L)
        """
        B, L, T, _ = text_embs.shape

        h = self.text_proj(text_embs)
        if use_type:
            h = h + self.type_embedding(type_ids)
        if use_thread:
            h = h + self.thread_embedding(thread_ids)

        BL = B * L
        h = h.view(BL, T, -1)
        kpm = (~valid_mask).view(BL, T)

        all_invalid = kpm.all(dim=1)
        safe_kpm = kpm.clone()
        safe_kpm[all_invalid, 0] = False

        h_post = h
        for attn_layer, norm_layer in zip(self.intra_attn_layers, self.intra_norm_layers):
            attn_out, _ = attn_layer(h_post, h_post, h_post, key_padding_mask=safe_kpm)
            h_post = norm_layer(h_post + attn_out)

        valid_f = valid_mask.view(BL, T, 1).float()

        if self.attn_pool:
            cls_q = self.bin_cls.unsqueeze(0).expand(BL, 1, -1)
            base_pool, _ = self.bin_pool_attn(
                query=cls_q, key=h_post, value=h_post, key_padding_mask=safe_kpm,
            )
            base_pool = base_pool.squeeze(1)
        else:
            denom = valid_f.sum(dim=1).clamp_min(1.0)
            base_pool = (h_post * valid_f).sum(dim=1) / denom

        if self.type_pool and use_type:
            type_flat = type_ids.view(BL, T)
            main_mask = ((type_flat == 0) & valid_mask.view(BL, T)).unsqueeze(-1).float()
            reply_mask = ((type_flat == 1) & valid_mask.view(BL, T)).unsqueeze(-1).float()
            main_denom = main_mask.sum(dim=1).clamp_min(1.0)
            reply_denom = reply_mask.sum(dim=1).clamp_min(1.0)
            main_vec = (h_post * main_mask).sum(dim=1) / main_denom
            reply_vec = (h_post * reply_mask).sum(dim=1) / reply_denom
            mixed = self.type_pool_mix(torch.cat([main_vec, reply_vec], dim=-1))
            if self.residual_type_pool:
                bin_vec = base_pool + self.type_pool_alpha * (mixed - base_pool)
            else:
                bin_vec = mixed
        else:
            bin_vec = base_pool

        bin_vec = bin_vec * (~all_invalid).float().unsqueeze(-1)
        bin_vec = bin_vec.view(B, L, -1)
        bin_valid = (~all_invalid).view(B, L)
        return bin_vec, bin_valid


class TextAuxHead(nn.Module):
    """Auxiliary head: predicts the horizon target from text-only bin vectors.

    Used to inject a direct supervised signal into the text branch so
    that bin vectors are encouraged to be predictive of the target
    rather than only being instrumental to the main fusion path.
    """

    def __init__(self, d_model, pred_len, c_out, hidden=None, dropout=0.1):
        super().__init__()
        if hidden is None:
            hidden = d_model
        self.pool_attn = nn.Linear(d_model, 1)
        self.head = nn.Sequential(
            nn.Linear(d_model, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, pred_len * c_out),
        )
        self.pred_len = pred_len
        self.c_out = c_out

    def forward(self, bin_vecs, bin_valid):
        """
        bin_vecs:  (B, L, d_model)
        bin_valid: (B, L) bool
        Returns:   (B, pred_len, c_out)
        """
        scores = self.pool_attn(bin_vecs).squeeze(-1)
        scores = scores.masked_fill(~bin_valid, float("-inf"))
        any_valid = bin_valid.any(dim=1, keepdim=True)
        scores = torch.where(any_valid, scores, torch.zeros_like(scores))
        weights = torch.softmax(scores, dim=1).unsqueeze(-1)
        summary = (bin_vecs * weights).sum(dim=1)
        out = self.head(summary)
        return out.view(-1, self.pred_len, self.c_out)
