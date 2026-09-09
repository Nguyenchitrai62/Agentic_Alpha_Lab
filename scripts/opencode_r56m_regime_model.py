"""Opencode R56-M (v145 regime-quiet): Selective-SSM TAI DUNG tu v35/v41 + upweight quiet opt_B.

Kien truc DONG KICH THUOC v35/v38/v39/v40/v41 (SelectiveSSMTemporal ~0.6M params, causal):
  tai dung VERBATIM class tu scripts/opencode_r9m_nextarch_model.py (doi ten
  ValueScaleRegimeSSMTemporal, khong doi dims/wiring, khong them params;
  upweight la vector ngoai params, 0 params moi).
Loss DONG BANG configs/opencode_v145_regime.json (DOI vs v41 CHI o ranking):
  2.0*value_objective_chuan_hoa(score_z,aux_z,labels,mu,sigma)
    payoff = MSE(score_z[...,0], (target-mu)/sigma)
    + 0.1 fill BCE (logits, khong scale) + 0.1 aux MSE(aux_z, direction/sigma)
  + 0.5*WEIGHTED-pairwise_expected_rank_loss(expected_trade=score_z*sigma+mu, labels, w opt_B,
        temperature_percent=1.0, tie_band_percent=0.25)   [per-row VERBATIM pairwise logic + WAIT=0, weighted mean]
  + 1.0*CE_dir + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48)
  + 3.0*coverage-hinge TREN TRADEABLE (en_best_trade = max_k trade).
Upweight CHI ranking term (value/coverage/aux giu unweighted); KHONG exclude bat ky sample nao (v103 verdict).
De-chuan-hoa: trade = score_z*sigma + mu (percent, affine giu thu tu).
KHONG CLIP tren selection path (giu raw order end-to-end, giu v41).
Sizing cap CHI tren file rieng: capped_sizing = clip(trade, +-2.0 percent), recorded, khong dung cho selection.
Tie-break deterministic VERBATIM v40/v41 (fill-desc, tren raw tradeable).
Calibrate-first (isotonic outlier-robust past-only TRUOC choose) THUC THI o audit
local sau tren VAL-PRED EXPORT RAW (val_predictions.npy), khong o day.
"""

import torch  # noqa: F401  (torch truoc pandas)
from torch.nn import functional as F

from agentic_alpha_lab.models.macro_micro_value import objective  # noqa: F401 (ghi nhan goc; v145 dung objective chuan-hoa rieng)
from agentic_alpha_lab.models.ranked_loss import pairwise_expected_rank_loss  # noqa: F401 (ghi nhan goc; v145 dung ban weighted per-row)

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
SIZING_CAP, SIZING_CAP_MODE = 2.0, "clip"
TIE_BREAK_EPS = 1e-6
SIGMA_FLOOR = 1e-6
UPWEIGHT_LLIKE = 2.0
VOL_CUT_V56 = 0.01338037015711381
FUND_ABS = 0.0001


def compute_value_stats(labels_train):
    """Thong ke train-only past-only cho chuan-hoa (labels percent, zeros giu nguyen).

    labels_train: (n_train,16,3) hoac (n_train,16) ch0. Tra ve (mu, sigma_eff) float.
    mu = mean ch0 flattened; sigma = std population (ddof=0); sigma_eff = max(sigma, 1e-6).
    """
    import numpy as np
    lab = np.asarray(labels_train)
    ch0 = lab[..., 0] if lab.ndim == 3 else lab
    ch0 = np.asarray(ch0, dtype=np.float64).ravel()
    if ch0.size == 0 or not np.isfinite(ch0).all():
        raise ValueError("Invalid train labels for value stats")
    mu = float(np.mean(ch0))
    sigma = float(np.std(ch0))
    if not (np.isfinite(mu) and np.isfinite(sigma)):
        raise ValueError("Nonfinite value stats")
    sigma_eff = float(max(sigma, SIGMA_FLOOR))
    return mu, sigma_eff


def destandardize(z, mu, sigma):
    """De-chuan-hoa: trade (percent) = z*sigma + mu (affine giu thu tu)."""
    return z * float(sigma) + float(mu)


def apply_sizing_cap(trade, cap=SIZING_CAP):
    """Sizing-cap RIENG (torch): clip trade percent ve +-cap. KHONG dung cho selection."""
    if not float(cap) == 2.0:
        raise ValueError("v145 sizing cap phai 2.0 percent")
    return torch.clamp(trade, -float(cap), float(cap))


def apply_sizing_cap_numpy(trade, cap=SIZING_CAP):
    """Numpy mirror cua sizing-cap rieng (chi cho file sizing + demo, khong train/selection)."""
    import numpy as np
    trade = np.asarray(trade, dtype=np.float64)
    if not float(cap) == 2.0:
        raise ValueError("v145 sizing cap phai 2.0 percent")
    return np.clip(trade, -float(cap), float(cap))


def compute_upweights(vol_high, fund_high, factor=UPWEIGHT_LLIKE):
    """Upweight vector EXACT v103 rule (opt_B): w=2.0 neu (vol_high==0 & fund_high==0) else 1.0."""
    import numpy as np
    vh = np.asarray(vol_high).reshape(-1)
    fh = np.asarray(fund_high).reshape(-1)
    if vh.shape != fh.shape:
        raise ValueError("vol/fund shape mismatch")
    if not float(factor) == 2.0:
        raise ValueError("v145 upweight factor phai 2.0")
    like = (vh == 0) & (fh == 0)
    w = np.where(like, float(factor), 1.0).astype(np.float64)
    return w, like.astype(bool)


def upweight_stats(weights, like):
    """Thong ke record moi fold/seed: frac/mean/ESS (toan bo tu past-only descriptors)."""
    import numpy as np
    w = np.asarray(weights, dtype=np.float64).reshape(-1)
    lk = np.asarray(like).reshape(-1).astype(bool)
    if w.shape != lk.shape or not np.isfinite(w).all() or bool((w <= 0).any()):
        raise ValueError("Invalid upweight vector for stats")
    n = int(w.size)
    n_like = int(lk.sum())
    frac = float(n_like / n) if n else float("nan")
    mean_like = float(w[lk].mean()) if n_like else float("nan")
    mean_rest = float(w[~lk].mean()) if n - n_like else float("nan")
    ess = float((w.sum() ** 2) / (np.square(w).sum())) if n else float("nan")
    return {"n": n, "n_Llike": n_like, "frac_Llike": frac,
            "mean_w_Llike": mean_like, "mean_w_rest": mean_rest,
            "eff_sample_size": ess}


def weighted_pairwise_rank_loss(expected, labels, weights=None,
                                temperature_percent=RANK_TEMP_PCT,
                                tie_band_percent=RANK_TIE_PCT):
    """Pairwise ranking VERBATIM logic per-row (kem WAIT=0) + weighted mean (opt_B).

    expected: (m,16) tradeable percent (de-chuan-hoa); labels: (m,16,3) hard ch0 percent.
    weights: (m,) float (2.0 L-like quiet, 1.0 rest; None -> uniform == v41).
    Tra ve (scalar, per_row detached).
    """
    if expected.ndim != 2 or expected.shape[1] != 16:
        raise ValueError("Expected (m,16) tradeable scores")
    if labels.ndim != 3 or labels.shape[:2] != expected.shape:
        raise ValueError("Expected (m,16,3) hard labels")
    if not (torch.isfinite(expected).all() and torch.isfinite(labels).all()):
        raise ValueError("Nonfinite ranking inputs")
    if temperature_percent <= 0 or tie_band_percent < 0:
        raise ValueError("Invalid ranking temperature or tie band")
    realized = labels[..., 0]
    exp = torch.cat((expected.float(), expected.float().new_zeros((len(expected), 1))), dim=1)
    real = torch.cat((realized.float(), realized.float().new_zeros((len(realized), 1))), dim=1)
    target_diff = real.unsqueeze(-1) - real.unsqueeze(-2)
    score_diff = exp.unsqueeze(-1) - exp.unsqueeze(-2)
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


def deterministic_best_index(expected_row, fill_row, candidates, eps=TIE_BREAK_EPS):
    """Tie-break deterministic pre-spec v145 (giu VERBATIM v40/v41, tren RAW TRADEABLE).

    expected_row: (16,) expected tradeable percent (RAW, khong clip).
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
        raise ValueError("v145 tie_break_eps phai 1e-6")
    m = float(np.max(exp))
    tied = np.flatnonzero((m - exp) < float(eps))
    if len(tied) == 1:
        return int(tied[0])
    fmax = float(np.max(fil[tied]))
    tied_f = tied[(fil[tied] >= fmax - 1e-9)]
    if len(tied_f) == 1:
        return int(tied_f[0])
    holdings = cand[tied_f, 5].astype(np.float64)
    hmin = float(np.min(holdings))
    tied_h = tied_f[holdings <= hmin + 1e-12]
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


class ValueScaleRegimeSSMTemporal(SelectiveSSMTemporal):
    """SelectiveSSMTemporal xuat Z (chuan-hoa; de-chuan-hoa post-hoc o export/policy).

    Giu params 600875 (khong them params; upweight 0 params). Forward tra ve score_z
    de loss chay tren Z (gradient scale-invariant). Export/policy de-chuan-hoa ve tradeable.
    """

    def forward(self, sequence, flat):
        return super().forward(sequence, flat)


def standardized_value_objective(score_z, aux_z, labels, mu, sigma):
    """Value objective chuan-hoa v145 (giu VERBATIM v41).

    score_z[...,0]: z-pred; aux_z: z-aux; labels ch0 percent (unconditional, zeros giu).
    payoff = MSE(score_z0, (target-mu)/sigma); aux = MSE(aux_z, direction/sigma)
    (direction = mean long - mean short percent, khong tru mu); fill BCE giu nguyen.
    Tra ve scalar (payoff + 0.1*fill + 0.1*aux) nhu macro_micro_value.objective.
    """
    mu_f, sig_f = float(mu), float(sigma)
    if not sig_f >= SIGMA_FLOOR:
        raise ValueError("Invalid sigma for standardization")
    target = labels[..., 0]
    fill = labels[..., 1]
    z_target = (target - mu_f) / sig_f
    payoff = F.mse_loss(score_z[..., 0] / 1.0, z_target / 1.0)
    fill_loss = F.binary_cross_entropy_with_logits(score_z[..., 1], fill)
    direction = target[:, :8].mean(-1) - target[:, 8:].mean(-1)
    auxiliary_loss = F.mse_loss(aux_z / 1.0, (direction / sig_f) / 1.0)
    return payoff + 0.1 * fill_loss + 0.1 * auxiliary_loss


def multitask_loss_cov_rank_std(score, aux, dlogits, quant, exc, labels, ydir,
                                yret, yup, ydn, mu, sigma, weights=None,
                                value_w=LOSS_W_VALUE,
                                rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                                floor_pos=COV_FLOOR_POS,
                                rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    """Full v145 loss: value tren Z + WEIGHTED ranking/coverage tren TRADEABLE.

    score[...,0] la Z (tu ValueScaleRegimeSSMTemporal.forward). Ranking tinh tren
    trade = score_z0*sigma + mu (percent) voi weights opt_B (2.0 quiet else 1.0);
    value/coverage/aux KHONG weight. KHONG clip o day.
    Tra ve (total, parts incl rank_per_row detached).
    """
    base = standardized_value_objective(score, aux, labels, mu, sigma)
    trade = score.float()[..., 0] * float(sigma) + float(mu)
    rank, per_row = weighted_pairwise_rank_loss(trade, labels, weights,
                                                temperature_percent=rank_temp,
                                                tie_band_percent=rank_tie)
    counts = torch.bincount(ydir, minlength=3).float() + 1.0
    cw = (counts.sum() / (3 * counts)).to(dlogits.dtype)
    ce = F.cross_entropy(dlogits, ydir, weight=cw)
    qb = pinball(quant, yret)
    ex = F.mse_loss(torch.log1p(exc),
                     torch.log1p(torch.stack([yup, ydn], -1)))
    trade_full = torch.cat([trade.unsqueeze(-1), score[..., 1:]], dim=-1)
    cov, mean_pos, en_mean = coverage_floor_loss(trade_full, lambda_cov, floor_pos)
    total = value_w * base + rank_w * rank + LOSS_W_DIR * ce + LOSS_W_Q * qb + LOSS_W_E * ex + cov
    if not torch.isfinite(total):
        raise ValueError("Nonfinite regimescale training loss")
    return total, {"base": base.detach(), "rank": rank.detach(),
                   "ce": ce.detach(), "qb": qb.detach(), "ex": ex.detach(),
                   "cov": cov.detach(), "mean_pos": mean_pos,
                   "en_mean": en_mean, "rank_per_row": per_row}


# Alias giu tuong thich import style v38/v39/v40/v41 (train/smoke goi multitask_loss_cov_rank).
def multitask_loss_cov_rank(score, aux, dlogits, quant, exc, labels, ydir,
                            yret, yup, ydn, mu=None, sigma=None, weights=None,
                            value_w=LOSS_W_VALUE,
                            rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                            floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    if mu is None or sigma is None:
        raise ValueError("v145 can mu/sigma train-window (past-only) cho moi fold")
    return multitask_loss_cov_rank_std(
        score, aux, dlogits, quant, exc, labels, ydir,
        yret, yup, ydn, mu, sigma, weights,
        value_w=value_w, rank_w=rank_w, lambda_cov=lambda_cov,
        floor_pos=floor_pos, rank_temp=rank_temp, rank_tie=rank_tie)


def predict_ssm_raw(model, sequence, flat, mu, sigma, batch_size=32):
    """Map v8 RAW TRADEABLE v145 (selection path, KHONG CLIP; giu VERBATIM v41)."""
    import numpy as np
    model.eval()
    device = next(model.parameters()).device
    out = []
    with torch.no_grad():
        for s in range(0, len(flat), batch_size):
            xs = torch.as_tensor(sequence[s:s + batch_size], dtype=torch.float32, device=device)
            xf = torch.as_tensor(flat[s:s + batch_size], dtype=torch.float32, device=device)
            score, *_ = model(xs, xf)
            z0 = score[..., 0]
            trade0 = z0 * float(sigma) + float(mu)
            fill = score[..., 1].sigmoid().clamp(1e-6, 1 - 1e-6)
            block = torch.zeros((*score.shape[:2], 6), device=device)
            block[..., 0], block[..., 4] = trade0 / fill, torch.logit(fill)
            out.append(block.cpu())
    return torch.cat(out).numpy()


def predict_ssm_sizing_capped(model, sequence, flat, mu, sigma, batch_size=32, cap=SIZING_CAP):
    """Sizing copy RIENG v145 (KHONG dung cho selection): clip trade ve +-cap percent."""
    import numpy as np
    raw = predict_ssm_raw(model, sequence, flat, mu, sigma, batch_size=batch_size)
    if not float(cap) == 2.0:
        raise ValueError("v145 sizing cap phai 2.0 percent")
    fill = 1 / (1 + np.exp(-np.clip(raw[..., 4], -40, 40)))
    trade = raw[..., 0] * fill
    capped = apply_sizing_cap_numpy(trade, cap=cap)
    out = raw.copy()
    out[..., 0] = capped / fill
    return out


# predict_ssm la ten chuan driver goi; v145 tro den ban RAW (selection, khong clip).
def predict_ssm(model, sequence, flat, batch_size=32, mu=None, sigma=None):
    if mu is None or sigma is None:
        raise ValueError("v145 predict_ssm can mu/sigma train-window (past-only)")
    return predict_ssm_raw(model, sequence, flat, mu, sigma, batch_size=batch_size)
