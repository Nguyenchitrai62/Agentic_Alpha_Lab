"""Opencode R37-M (v106 student-from-distill): SSM student TAI DUNG v35/v41 + distill loss.

Kien truc: tai dung VERBATIM SelectiveSSM1D + encoder/context/action wiring tu
scripts/opencode_r9m_nextarch_model.py (causal, ~0.6M). ONLY diff: final head
Linear(192,1) thay vi Linear(192,2) -> student_logits (n,16) free units
(khong percent, khong destandardize, khong mu/sigma). Encoder/action dims/wiring
GIU NGUYEN de so sanh cong bang voi v38/v55c/v41.
Loss DONG BANG configs/opencode_v106_student.json:
  L = 1.0*KL(student||frozen-soft, T=1, soft-subset)
    + 0.2*weighted_ranking(student_logits, hard labels, upweight L-like 2.0x)
    + 3.0*coverage-hinge TREN LOGITS (safety net).
Ranking per-row VERBATIM logic pairwise_expected_rank_loss (temp 1.0% / tie 0.25%,
kem WAIT=0 reference), weighted mean voi w_i (upweight CHI ranking term).
Tie-break deterministic (eps 1e-6, holding-asc, index-min; BO fill-desc vi
student KHONG train fill head). Calibrate-first THUC THI o audit local sau tren
VAL-LOGITS EXPORT (val_predictions_logits.npy), khong o day.
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch import nn
from torch.nn import functional as F

from opencode_r9m_nextarch_model import (  # noqa: F401  (tai dung verbatim)
    POLICY_MARGIN,
    POLICY_N_MIN,
    SelectiveSSM1D,
    SelectiveSSMTemporal,
    apply_coverage_floor_policy,
    count_params,
    coverage_floor_loss,
    expected_net_best,
    pinball,
)

KL_WEIGHT = 1.0
RANK_WEIGHT = 0.2
RANK_TEMP_PCT, RANK_TIE_PCT = 1.0, 0.25
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4
UPWEIGHT_LLIKE = 2.0
TIE_BREAK_EPS = 1e-6
VOL_CUT_V56 = 0.01338037015711381
FUND_ABS = 0.0001


class StudentSSMTemporal(SelectiveSSMTemporal):
    """Student SSM: encoder/action VERBATIM v35/v41, head single-logit per candidate.

    Giu frame_in/frame_ssm/frame_pool/cross_ssm/frame_features/macro/micro/gate/
    action DONG KICH THUOC v35/v41 (khong doi dims/wiring). Thay score(->2) bang
    student head (->1): Linear(4*width,width)+GELU+Dropout+Linear(width,1).
    Forward tra ve student_logits (n,16) free units (T=1 KL truc tiep).
    """

    def __init__(self, candidates, width=192, frame_dim=64, frame_state=16,
                 frame_layers=2, cross_state=16, dropout=0.1, n_flat=133):
        nn.Module.__init__(self)
        self.n_flat = n_flat
        self.register_buffer("feature_mean", torch.zeros(n_flat))
        self.register_buffer("feature_scale", torch.ones(n_flat))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale", torch.tensor([1., 1.5, 3., 3., 6., 7.]))
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
        self.student = nn.Sequential(nn.Linear(4 * width, width), nn.GELU(),
                                     nn.Dropout(dropout), nn.Linear(width, 1))

    def forward(self, sequence, flat):
        macro, micro = self.context(sequence, flat)
        action = self.action(self.candidates / self.candidate_scale)
        k, n = len(action), len(sequence)
        ma = macro[:, None].expand(-1, k, -1)
        mi = micro[:, None].expand(-1, k, -1)
        ac = action[None].expand(n, -1, -1)
        logits = self.student(torch.cat((ma, mi, ac, (ma + mi) * ac), -1)).squeeze(-1)
        return logits


def student_kl(student_logits, soft_targets):
    """KL(student||teacher, T=1) tren soft-subset (student-first, dung mission).

    student_logits: (m,16) free units; soft_targets: (m,16) rows sum-to-1 frozen.
    Tra ve scalar batchmean.
    """
    if student_logits.ndim != 2 or student_logits.shape[1] != 16:
        raise ValueError("Expected (m,16) student logits")
    if soft_targets.shape != student_logits.shape:
        raise ValueError("Soft-target shape mismatch")
    if not (torch.isfinite(student_logits).all() and torch.isfinite(soft_targets).all()):
        raise ValueError("Nonfinite KL inputs")
    logp = F.log_softmax(student_logits.float(), dim=1)
    q = soft_targets.float().clamp(1e-12, 1.0)
    q = q / q.sum(dim=1, keepdim=True).clamp_min(1e-12)
    p = logp.exp()
    kl_row = (p * (logp - q.log())).sum(dim=1)
    kl = kl_row.mean()
    if not torch.isfinite(kl):
        raise ValueError("Nonfinite student KL")
    return kl


def weighted_ranking_loss(student_logits, labels, weights=None,
                          temperature_percent=RANK_TEMP_PCT,
                          tie_band_percent=RANK_TIE_PCT):
    """Ranking-on-hard VERBATIM pairwise logic (per-row) + weighted mean (opt_B).

    student_logits: (m,16) free units; labels: (m,16,3) hard (ch0 percent, zeros giu).
    weights: (m,) float (2.0 L-like, 1.0 rest; None -> uniform). Kem WAIT=0 reference.
    Tra ve (scalar, per_row detached).
    """
    if student_logits.ndim != 2 or student_logits.shape[1] != 16:
        raise ValueError("Expected (m,16) student logits")
    if labels.ndim != 3 or labels.shape[:2] != student_logits.shape:
        raise ValueError("Expected (m,16,3) hard labels")
    if not (torch.isfinite(student_logits).all() and torch.isfinite(labels).all()):
        raise ValueError("Nonfinite ranking inputs")
    if temperature_percent <= 0 or tie_band_percent < 0:
        raise ValueError("Invalid ranking temperature or tie band")
    realized = labels[..., 0]
    expected = torch.cat((student_logits.float(), student_logits.float().new_zeros((len(student_logits), 1))), dim=1)
    realized = torch.cat((realized.float(), realized.float().new_zeros((len(realized), 1))), dim=1)
    target_diff = realized.unsqueeze(-1) - realized.unsqueeze(-2)
    score_diff = expected.unsqueeze(-1) - expected.unsqueeze(-2)
    comparable = target_diff > float(tie_band_percent)
    penalties = F.softplus(-score_diff / float(temperature_percent))
    denom = comparable.sum(dim=(1, 2)).clamp_min(1).float()
    per_row = (penalties * comparable).sum(dim=(1, 2)) / denom
    if weights is None:
        w = torch.ones_like(per_row)
    else:
        w = torch.as_tensor(weights, dtype=per_row.dtype, device=per_row.device).reshape(-1)
        if w.shape != per_row.shape or not torch.isfinite(w).all() or bool((w <= 0).any()):
            raise ValueError("Invalid upweight vector")
    loss = (w * per_row).sum() / w.sum().clamp_min(1e-12)
    if not torch.isfinite(loss):
        raise ValueError("Nonfinite weighted ranking loss")
    return loss, per_row.detach()


def coverage_hinge_logits(student_logits, lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS):
    """Coverage-hinge TREN LOGITS free units (safety net, inactive khi healthy)."""
    en_best = student_logits.float().amax(dim=1)
    mean_pos = F.relu(en_best).mean()
    gap = F.relu(1.0 - mean_pos / float(floor_pos))
    loss = float(lambda_cov) * gap * gap
    return loss, mean_pos.detach(), en_best.detach().mean()


def student_loss(student_logits, soft_targets_or_none, labels, weights=None,
                 kl_w=KL_WEIGHT, rank_w=RANK_WEIGHT,
                 lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS,
                 rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    """Full v106 loss: KL (soft-subset, unweighted) + ranking (all-train, weighted) + coverage.

    student_logits/labels/weights: full batch (m rows). soft_targets_or_none: None
    (fold0 fallback, KL=0) hoac (m_soft,16) + soft_idx (m_soft,) — o day nhan truc
    tiep logits_soft (m_soft,16) + soft (m_soft,16) de don gian goi tu train/smoke.
    De tranh nham lan, ham nay nhan logits_full + labels_full + weights_full cho
    ranking/coverage, va kl_term scalar rieng (tinh boi caller tren soft-subset).
    O day giu signature don gian: caller truyen kl_term da tinh (0.0 neu empty).
    """
    raise NotImplementedError("Dung student_loss_from_parts (KL tach rieng vi soft-subset).")


def student_loss_from_parts(kl_term, student_logits_full, labels_full, weights_full=None,
                            kl_w=KL_WEIGHT, rank_w=RANK_WEIGHT,
                            lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    rank, per_row = weighted_ranking_loss(student_logits_full, labels_full, weights_full,
                                          temperature_percent=rank_temp, tie_band_percent=rank_tie)
    cov, mean_pos, en_mean = coverage_hinge_logits(student_logits_full, lambda_cov, floor_pos)
    kl = torch.as_tensor(float(kl_term), dtype=student_logits_full.dtype, device=student_logits_full.device)
    total = float(kl_w) * kl + float(rank_w) * rank + cov
    if not torch.isfinite(total):
        raise ValueError("Nonfinite student training loss")
    return total, {"kl": kl.detach(), "rank": rank.detach(),
                   "cov": cov.detach(), "mean_pos": mean_pos,
                   "en_mean": en_mean, "rank_per_row": per_row}


def compute_upweights(vol_high, fund_high, factor=UPWEIGHT_LLIKE):
    """Upweight vector EXACT v103 rule: w=2.0 neu (vol_high==0 & fund_high==0) else 1.0."""
    import numpy as np
    vh = np.asarray(vol_high).reshape(-1)
    fh = np.asarray(fund_high).reshape(-1)
    if vh.shape != fh.shape:
        raise ValueError("vol/fund shape mismatch")
    if not float(factor) == 2.0:
        raise ValueError("v106 upweight factor phai 2.0")
    like = (vh == 0) & (fh == 0)
    w = np.where(like, float(factor), 1.0).astype(np.float64)
    return w, like.astype(bool)


def deterministic_best_index(logits_row, candidates, eps=TIE_BREAK_EPS):
    """Tie-break deterministic pre-spec v106 (TREN LOGITS free units, BO fill-desc).

    logits_row: (16,) student logits free units.
    candidates: (16,6) [side, entry, b0,b1,b2, holding]; holding = [:,5] trong {3,7}.
    Quy tac: (1) m = max(logits); (2) T = {k: m - logits[k] < eps};
    (3) trong T chon holding nho nhat; (4) neu van tie chon index nho nhat.
    """
    import numpy as np
    lg = np.asarray(logits_row, dtype=np.float64).reshape(-1)
    cand = np.asarray(candidates)
    if lg.shape[0] != 16 or cand.shape != (16, 6):
        raise ValueError("Tie-break expects (16,) logits + (16,6) candidates")
    if not np.isfinite(lg).all():
        raise ValueError("Nonfinite tie-break inputs")
    if not float(eps) == 1e-6:
        raise ValueError("v106 tie_break_eps phai 1e-6")
    m = float(np.max(lg))
    tied = np.flatnonzero((m - lg) < float(eps))
    if len(tied) == 1:
        return int(tied[0])
    holdings = cand[tied, 5].astype(np.float64)
    hmin = float(np.min(holdings))
    tied_h = tied[holdings <= hmin + 1e-12]
    return int(np.min(tied_h))


def deterministic_best_indices(logits, candidates, eps=TIE_BREAK_EPS):
    """Vector hoa deterministic_best_index cho (n,16). Tra ve (n,) int64."""
    import numpy as np
    lg = np.asarray(logits, dtype=np.float64)
    if lg.ndim != 2 or lg.shape[1] != 16:
        raise ValueError("Expected (n,16) logits")
    return np.asarray([deterministic_best_index(lg[i], candidates, eps=eps)
                       for i in range(lg.shape[0])], dtype=np.int64)


def predict_student_logits(model, sequence, flat, batch_size=32):
    """Export logits free units (n,16) cho test/val (selection + calibrate-first sau)."""
    import numpy as np
    model.eval()
    device = next(model.parameters()).device
    out = []
    with torch.no_grad():
        for s in range(0, len(flat), batch_size):
            xs = torch.as_tensor(sequence[s:s + batch_size], dtype=torch.float32, device=device)
            xf = torch.as_tensor(flat[s:s + batch_size], dtype=torch.float32, device=device)
            out.append(model(xs, xf).detach().cpu())
    return torch.cat(out).numpy()
