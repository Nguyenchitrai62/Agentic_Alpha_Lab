"""Opencode R25-M (v40 cap-at-policy): Selective-SSM TAI DUNG tu v35/v38/v39 + ranking TREN RAW.

Kien truc DONG KICH THUOC v35/v38/v39 (SelectiveSSMTemporal ~0.6M params, causal):
  tai dung VERBATIM class tu scripts/opencode_r9m_nextarch_model.py (doi ten
  CapAtPolicySSMTemporal, khong doi dims/wiring, khong them params).
Loss DONG BANG configs/opencode_v77_v40.json (GIONG v38, KHAC v39):
  2.0*objective(score_raw,aux,labels)   [payoff MSE + 0.1 fill BCE + 0.1 aux, TREN RAW]
  + 0.5*pairwise_expected_rank_loss(expected=raw0, labels,
        temperature_percent=1.0, tie_band_percent=0.25)   [nhu v29/v38, TREN RAW]
  + 1.0*CE_dir + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48)
  + 3.0*coverage-hinge (GIU NGUYEN v35/v38, TINH TREN RAW:
        en_best_raw = max_k raw[k,0]).
Cap CHI o policy/export (pre-spec v40, sua rank-flat v39):
  capped = clip(raw, -0.02, +0.02) SAU ranking/argmax, post-hoc eval-only,
  khong gradient. Clip giu nguyen vung [-2%,+2%], chi cat outliers.
Tie-break deterministic (pre-spec v40, sua 55% near-tie instability v39):
  deterministic_best_index(expected_row, fill_row, candidates, eps=1e-6):
  gap<1e-6 -> fill-desc, roi holding-asc (3 truoc 7), roi index nho nhat.
Policy floor (eval, pre-spec): gate en_best_capped > 0 + fallback top-8 (tie-break).
Calibrate-first (isotonic outlier-robust past-only TRUOC choose) THUC THI o audit
local sau tren VAL-PRED EXPORT (val_predictions.npy, ke thua v39), khong o day.
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch.nn import functional as F

from agentic_alpha_lab.models.macro_micro_value import objective
from agentic_alpha_lab.models.ranked_loss import pairwise_expected_rank_loss

from opencode_r9m_nextarch_model import (  # noqa: F401  (tai dung kien truc v35)
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

QUANTS = (0.1, 0.5, 0.9)
LOSS_W_VALUE, LOSS_W_RANK, LOSS_W_DIR, LOSS_W_Q, LOSS_W_E = 2.0, 0.5, 1.0, 1.0, 0.5
RANK_TEMP_PCT, RANK_TIE_PCT = 1.0, 0.25
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4
POLICY_CAP, POLICY_CAP_MODE = 0.02, "clip"
TIE_BREAK_EPS = 1e-6


def apply_policy_cap(raw, cap=POLICY_CAP, mode=POLICY_CAP_MODE):
    """Cap-at-policy pre-spec v40: clip post-hoc, eval-only, khong gradient.

    capped = clip(raw, -cap, +cap), |capped| <= cap. Chi goi o policy/export,
    KHONG goi trong loss. Clip (khong tanh) vi giu nguyen vung quyet dinh.
    """
    if mode != "clip":
        raise ValueError(f"v40 chi cho phep policy_cap_mode=clip, nhan {mode!r}")
    if not float(cap) == 0.02:
        raise ValueError(f"v40 policy_cap_cap phai 0.02 (+-2%), nhan {cap!r}")
    return torch.clamp(raw, -float(cap), float(cap))


def apply_policy_cap_numpy(raw, cap=POLICY_CAP):
    """Numpy mirror cua apply_policy_cap (dung cho bounded-proof/export, khong train)."""
    import numpy as np
    raw = np.asarray(raw, dtype=np.float64)
    if not float(cap) == 0.02:
        raise ValueError("v40 policy_cap_cap phai 0.02")
    return np.clip(raw, -float(cap), float(cap))


def deterministic_best_index(expected_row, fill_row, candidates, eps=TIE_BREAK_EPS):
    """Tie-break deterministic pre-spec v40 (per-decision, causal, khong fit).

    expected_row: (16,) expected (raw hoac capped, tuy caller; policy dung capped).
    fill_row: (16,) fill logit (score[...,1]).
    candidates: (16,6) [side, entry, b0,b1,b2, holding]; holding = [:,5] trong {3,7}.
    Quy tac: (1) m = max(expected); (2) T = {k: m - expected[k] < eps};
    (3) trong T chon fill cao nhat; (4) neu fill van tie (<1e-9) chon holding
    nho nhat; (5) neu van tie chon index nho nhat.
    """
    import numpy as np
    exp = np.asarray(expected_row, dtype=np.float64).reshape(-1)
    fil = np.asarray(fill_row, dtype=np.float64).reshape(-1)
    cand = np.asarray(candidates)
    if exp.shape[0] != 16 or fil.shape[0] != 16 or cand.shape != (16, 6):
        raise ValueError("Tie-break expects (16,) expected/fill + (16,6) candidates")
    if not (np.isfinite(exp).all() and np.isfinite(fil).all()):
        raise ValueError("Nonfinite tie-break inputs")
    if not float(eps) == 1e-6:
        raise ValueError("v40 tie_break_eps phai 1e-6")
    m = float(np.max(exp))
    tied = np.flatnonzero((m - exp) < float(eps))
    if len(tied) == 1:
        return int(tied[0])
    # (3) fill-score-descending trong nhom tie
    fmax = float(np.max(fil[tied]))
    tied_f = tied[(fil[tied] >= fmax - 1e-9)]
    if len(tied_f) == 1:
        return int(tied_f[0])
    # (4) holding-ascending (candidates[:,5]: 3 truoc 7)
    holdings = cand[tied_f, 5].astype(np.float64)
    hmin = float(np.min(holdings))
    tied_h = tied_f[holdings <= hmin + 1e-12]
    # (5) index nho nhat
    return int(np.min(tied_h))


def deterministic_best_indices(expected, fill_logits, candidates, eps=TIE_BREAK_EPS):
    """Vector hoa deterministic_best_index cho (n,16). Tra ve (n,) int64."""
    import numpy as np
    exp = np.asarray(expected, dtype=np.float64)
    fil = np.asarray(fill_logits, dtype=np.float64)
    if exp.ndim != 2 or exp.shape[1] != 16 or fil.shape != exp.shape:
        raise ValueError("Expected (n,16) expected/fill")
    return np.asarray([deterministic_best_index(exp[i], fil[i], candidates, eps=eps)
                       for i in range(exp.shape[0])], dtype=np.int64)


class CapAtPolicySSMTemporal(SelectiveSSMTemporal):
    """SelectiveSSMTemporal xuat RAW (khong cap trong forward; cap post-hoc o export).

    Giu params 600875 (khong them params). Forward tra ve score RAW de loss
    chay tren RAW (gradient untouched). Export/policy clip sau.
    """

    def forward(self, sequence, flat):
        return super().forward(sequence, flat)


def multitask_loss_cov_rank_raw(score, aux, dlogits, quant, exc, labels, ydir,
                                yret, yup, ydn, value_w=LOSS_W_VALUE,
                                rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                                floor_pos=COV_FLOOR_POS,
                                rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    """Full v40 loss TREN RAW (giong v38): value + ranking + aux + coverage-hinge.

    score[...,0] phai la RAW (tu CapAtPolicySSMTemporal.forward). Ham nay KHONG
    cap (defensive assert: tu choi capped-input? khong the phan biet, nen chi
    dam bao khong goi apply_policy_cap o day). Cap chi o predict/policy.
    """
    base = objective(score, aux, labels)
    rank = pairwise_expected_rank_loss(score.float()[..., 0], labels,
                                       temperature_percent=rank_temp,
                                       tie_band_percent=rank_tie)
    counts = torch.bincount(ydir, minlength=3).float() + 1.0
    cw = (counts.sum() / (3 * counts)).to(dlogits.dtype)
    ce = F.cross_entropy(dlogits, ydir, weight=cw)
    qb = pinball(quant, yret)
    ex = F.mse_loss(torch.log1p(exc),
                     torch.log1p(torch.stack([yup, ydn], -1)))
    cov, mean_pos, en_mean = coverage_floor_loss(score, lambda_cov, floor_pos)
    total = value_w * base + rank_w * rank + LOSS_W_DIR * ce + LOSS_W_Q * qb + LOSS_W_E * ex + cov
    if not torch.isfinite(total):
        raise ValueError("Nonfinite capatpolicy training loss")
    return total, {"base": base.detach(), "rank": rank.detach(),
                   "ce": ce.detach(), "qb": qb.detach(), "ex": ex.detach(),
                   "cov": cov.detach(), "mean_pos": mean_pos,
                   "en_mean": en_mean}


# Alias giu tuong thich import style v38/v39 (train/smoke goi multitask_loss_cov_rank).
def multitask_loss_cov_rank(score, aux, dlogits, quant, exc, labels, ydir,
                            yret, yup, ydn, value_w=LOSS_W_VALUE,
                            rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                            floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    return multitask_loss_cov_rank_raw(
        score, aux, dlogits, quant, exc, labels, ydir, yret, yup, ydn,
        value_w=value_w, rank_w=rank_w, lambda_cov=lambda_cov,
        floor_pos=floor_pos, rank_temp=rank_temp, rank_tie=rank_tie)


def predict_ssm_capped(model, sequence, flat, batch_size=32, cap=POLICY_CAP):
    """Map v8 CAPPED cap-at-policy (giong temporal_value.predict + clip +-2%).

    Model xuat RAW; o day clip post-hoc: clipped = clip(raw0, +-cap);
    ch0 = clipped/fill, ch4 = logit(fill). unconditional = ch0*fill = clipped
    (bounded +-2%); policy gate + tie-break dung unconditional capped.
    """
    import numpy as np
    if not float(cap) == POLICY_CAP:
        raise ValueError("v40 policy cap phai 0.02")
    model.eval()
    device = next(model.parameters()).device
    out = []
    with torch.no_grad():
        for s in range(0, len(flat), batch_size):
            xs = torch.as_tensor(sequence[s:s + batch_size], dtype=torch.float32, device=device)
            xf = torch.as_tensor(flat[s:s + batch_size], dtype=torch.float32, device=device)
            score, *_ = model(xs, xf)
            raw0 = score[..., 0]
            capped0 = apply_policy_cap(raw0, cap=cap)
            fill = score[..., 1].sigmoid().clamp(1e-6, 1 - 1e-6)
            block = torch.zeros((*score.shape[:2], 6), device=device)
            block[..., 0], block[..., 4] = capped0 / fill, torch.logit(fill)
            out.append(block.cpu())
    return torch.cat(out).numpy()


def predict_ssm_raw(model, sequence, flat, batch_size=32):
    """Map v8 RAW (khong cap, dung cho audit rank-gradient; khong dung cho policy)."""
    import numpy as np
    model.eval()
    device = next(model.parameters()).device
    out = []
    with torch.no_grad():
        for s in range(0, len(flat), batch_size):
            xs = torch.as_tensor(sequence[s:s + batch_size], dtype=torch.float32, device=device)
            xf = torch.as_tensor(flat[s:s + batch_size], dtype=torch.float32, device=device)
            score, *_ = model(xs, xf)
            fill = score[..., 1].sigmoid().clamp(1e-6, 1 - 1e-6)
            block = torch.zeros((*score.shape[:2], 6), device=device)
            block[..., 0], block[..., 4] = score[..., 0] / fill, torch.logit(fill)
            out.append(block.cpu())
    return torch.cat(out).numpy()


# predict_ssm la ten chuan driver goi; v40 tro den ban capped (policy).
def predict_ssm(model, sequence, flat, batch_size=32):
    return predict_ssm_capped(model, sequence, flat, batch_size=batch_size)
