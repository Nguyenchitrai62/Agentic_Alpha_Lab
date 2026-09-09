"""Opencode R17-B (v55 rankonly): Selective-SSM encoder TAI DUNG tu v35 + MOT head
ranking duy nhat. KHONG co value/quantile/dir/excursion/regime heads.

Kien truc encoder DONG KICH THUOC v35 (SelectiveSSM1D import VERBATIM tu
scripts/opencode_r9m_nextarch_model.py; frame/cross dims + fusion macro/micro/
action giu nguyen hinh dang de so sanh cong bang voi v35 (rank-less) va v38
(ranking-inside-multitask). Chi khac objective: ranking-ALONE.

Objective DUY NHAT (listwise ListNet, pre-spec trong configs/opencode_v55_rankonly.json):
    target_p(i) = softmax(realized_i / tau)      (realized = labels[...,0], don vi %)
    pred_logp(i) = log_softmax(pred_i / tau)     (pred = rank logits, ordinal)
    loss = mean_decisions[ -sum_i target_p(i) * pred_logp(i) ], tau = 1.0 (%)
Ties: softmax/log_softmax deterministic; moi argmax lay first-max (candidate
index nho nhat) mot cach deterministic; margin = top1 - second (second = max
tren 15 candidate con lai). Margin = 0 khi tie tuyet doi.

Mapping rank->signal (pre-spec, causal, frozen; chi tiet trong config):
    top1 = argmax logits; margin = top1 - second;
    threshold = percentile-70 cua margins tren nested-validation past-only
    (moi fold/seed doc lap, luu trong metadata);
    phat top1 candidate NEU margin > threshold, nguoc lai WAIT.
    KHONG fallback top-N (else WAIT dung nghia). KHONG du bao fill (fill channel
    khong ton tai; downstream dung execution fill model, khong dung learned fill).
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch import nn
from torch.nn import functional as F

from opencode_r9m_nextarch_model import SelectiveSSM1D  # noqa: F401  (tai dung VERBATIM)

RANK_TEMPERATURE_PERCENT = 1.0
RANK_GATE_PERCENTILE = 70


class RankOnlySSM(nn.Module):
    """Encoder SSM giong v35 + MOT rank scorer per-candidate (n,16) logits."""

    def __init__(self, candidates, width=192, frame_dim=64, frame_state=16,
                 frame_layers=2, cross_state=16, dropout=0.1, n_flat=133):
        super().__init__()
        self.n_flat = n_flat
        self.register_buffer("feature_mean", torch.zeros(n_flat))
        self.register_buffer("feature_scale", torch.ones(n_flat))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale", torch.tensor([1., 1.5, 3., 3., 6., 7.]))
        # Encoder VERBATIM hinh dang v35 (doi ten class, giu dims/wiring).
        self.frame_in = nn.Linear(6, frame_dim)
        self.frame_ssm = nn.ModuleList(
            [SelectiveSSM1D(frame_dim, frame_state, dropout=dropout) for _ in range(frame_layers)])
        self.frame_pool = nn.Linear(2 * frame_dim, width)
        self.cross_ssm = SelectiveSSM1D(width, cross_state, dropout=dropout)
        self.frame_features = nn.Sequential(nn.Linear(8, width), nn.GELU())
        self.macro = nn.Sequential(nn.Linear(2 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.micro = nn.Sequential(nn.Linear(3 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.gate = nn.Linear(width, width)
        self.action = nn.Sequential(nn.Linear(6, width), nn.GELU())
        # MOT head duy nhat: rank scorer (KHONG value/dir/quant/exc/regime).
        self.rank = nn.Sequential(nn.Linear(4 * width, width), nn.GELU(),
                                  nn.Dropout(dropout), nn.Linear(width, 1))

    def context(self, sequence, flat):
        if sequence.ndim != 4 or sequence.shape[1:] != (5, 128, 6):
            raise ValueError("Expected [batch, 5, 128, 6] closed-candle contexts")
        if flat.shape[-1] != self.n_flat:
            raise ValueError(f"Expected flat {self.n_flat}, got {flat.shape[-1]}")
        n = len(sequence)
        frames = []
        for i in range(5):  # encoder shared tren 5 frames (weight-shared, nhu v35)
            z = self.frame_in(sequence[:, i])
            for layer in self.frame_ssm:
                z = layer(z)
            frames.append(self.frame_pool(torch.cat((z[:, -1], z.mean(1)), -1)))
        scanned = self.cross_ssm(torch.stack(frames, 1)) + torch.stack(frames, 1)
        normalized = ((flat - self.feature_mean) / self.feature_scale).clamp(-10, 10)
        frame = scanned + self.frame_features(normalized[:, :40].reshape(n, 5, 8))
        macro = self.macro(frame[:, 3:].flatten(1))
        micro = self.micro(frame[:, :3].flatten(1)) * self.gate(macro).sigmoid()
        return macro, micro

    def forward(self, sequence, flat):
        macro, micro = self.context(sequence, flat)
        action = self.action(self.candidates / self.candidate_scale)
        k, n = len(action), len(sequence)
        ma = macro[:, None].expand(-1, k, -1)
        mi = micro[:, None].expand(-1, k, -1)
        ac = action[None].expand(n, -1, -1)
        return self.rank(torch.cat((ma, mi, ac, (ma + mi) * ac), -1)).squeeze(-1)


def listnet_rank_loss(pred, labels, temperature_percent=RANK_TEMPERATURE_PERCENT):
    """ListNet softmax-CE duy nhat: sap xep 16 candidates theo realized net."""
    if pred.ndim != 2 or labels.ndim != 3 or labels.shape[:2] != pred.shape:
        raise ValueError("Expected [batch,16] rank logits and [batch,16,3] labels")
    if temperature_percent <= 0:
        raise ValueError("Invalid ranking temperature")
    if not torch.isfinite(pred).all() or not torch.isfinite(labels).all():
        raise ValueError("Nonfinite ranking inputs")
    realized = labels[..., 0].float() / temperature_percent
    scores = pred.float() / temperature_percent
    target = F.softmax(realized, dim=1)
    logp = F.log_softmax(scores, dim=1)
    loss = -(target * logp).sum(dim=1).mean()
    if not torch.isfinite(loss):
        raise ValueError("Nonfinite listnet ranking loss")
    return loss


def rank_top1_margin_np(logits):
    """top1 (first-max deterministic) + margin = top1 - max(15 con lai)."""
    import numpy as np
    mat = np.asarray(logits, dtype=np.float64)
    if mat.ndim != 2 or mat.shape[1] != 16:
        raise ValueError("Expected [n,16] rank logits")
    top1 = np.argmax(mat, axis=1)  # first-max -> deterministic tie-break
    best = np.take_along_axis(mat, top1[:, None], axis=1)[:, 0]
    mask = np.ones_like(mat, dtype=bool)
    mask[np.arange(len(mat)), top1] = False
    second = np.where(mask, mat, -np.inf).max(axis=1)
    return top1.astype(np.int64), (best - second)


def apply_rank_gate(margins, threshold):
    """Gate pre-spec: giu decisions co margin > threshold (strict; tie -> WAIT)."""
    import numpy as np
    margins = np.asarray(margins, dtype=np.float64)
    return np.sort(np.flatnonzero(margins > float(threshold)))


def rank_logits_to_signals(test_logits, threshold):
    """Mapping chuan v55: moi decision -> (candidate_idx | -1=WAIT, margin)."""
    import numpy as np
    top1, margins = rank_top1_margin_np(test_logits)
    picks = apply_rank_gate(margins, threshold)
    chosen = np.full(len(top1), -1, dtype=np.int64)
    chosen[picks] = top1[picks]
    return chosen, margins


def predict_rank(model, sequence, flat, batch_size=32):
    """Export RAW rank logits (n,16). KHONG phai v8 block (khong co fill)."""
    import numpy as np
    model.eval()
    device = next(model.parameters()).device
    out = []
    with torch.no_grad():
        for s in range(0, len(flat), batch_size):
            xs = torch.as_tensor(sequence[s:s + batch_size], dtype=torch.float32, device=device)
            xf = torch.as_tensor(flat[s:s + batch_size], dtype=torch.float32, device=device)
            out.append(model(xs, xf).float().cpu())
    logits = torch.cat(out).numpy()
    if not np.isfinite(logits).all():
        raise ValueError("Nonfinite rank logits")
    return logits


def count_params(model):
    return sum(p.numel() for p in model.parameters())
