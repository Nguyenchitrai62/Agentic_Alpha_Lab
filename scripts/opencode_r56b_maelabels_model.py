"""Opencode R56-B (v146 MAE-utility): Selective-SSM TAI DUNG tu v35/v41 + nhan utility.

Kien truc DONG KICH THUOC v35/v38/v39/v40/v41 (SelectiveSSMTemporal ~0.6M params, causal):
  tai dung VERBATIM class tu scripts/opencode_r30m_v41_model.py (doi ten
  UtilityScaleSSMTemporal, khong doi dims/wiring, khong them params).
Loss DONG BANG configs/opencode_v146_maelabels.json (DOI vs v41 CHI o nhan):
  2.0*value_objective_chuan_hoa_tren_UTILITY(score_z,aux_z,labels_u,mu_u,sigma_u)
    payoff = MSE(score_z[...,0], (utility-mu_u)/sigma_u)
    + 0.1 fill BCE (logits, khong scale) + 0.1 aux MSE(aux_z, direction_u/sigma_u)
  + 0.5*pairwise_expected_rank_loss(expected_utility=score_z*sigma_u+mu_u, labels_u,
        temperature_percent=1.0, tie_band_percent=0.25)   [PRIMARY, tren UTILITY percent]
  + 1.0*CE_dir + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48, giu return-based)
  + 3.0*coverage-hinge TREN UTILITY TRADEABLE (en_best_utility = max_k utility).
De-chuan-hoa: utility_trade = score_z*sigma_u + mu_u (percent, affine giu thu tu).
KHONG CLIP tren selection path (giu raw order end-to-end, giu v41).
Sizing cap CHI tren file rieng: clip(utility_trade, +-2.0 percent), recorded.
Tie-break deterministic VERBATIM v40/v41 (tren raw utility).
Calibrate-first THUC THI o audit local sau tren VAL-PRED EXPORT RAW UTILITY.
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch.nn import functional as F

from agentic_alpha_lab.models.ranked_loss import pairwise_expected_rank_loss

from opencode_r30m_v41_model import (  # noqa: F401  (tai dung kien truc + loss-foundation v41)
    POLICY_MARGIN,
    POLICY_N_MIN,
    SIZING_CAP,
    TIE_BREAK_EPS,
    SIGMA_FLOOR,
    ValueScaleSSMTemporal,
    apply_sizing_cap_numpy,
    compute_value_stats,
    count_params,
    coverage_floor_loss,
    destandardize,
    deterministic_best_index,
    deterministic_best_indices,
    expected_net_best,
    pinball,
)
from opencode_r9m_nextarch_model import (  # noqa: F401
    apply_coverage_floor_policy,
)

QUANTS = (0.1, 0.5, 0.9)
LOSS_W_VALUE, LOSS_W_RANK, LOSS_W_DIR, LOSS_W_Q, LOSS_W_E = 2.0, 0.5, 1.0, 1.0, 0.5
RANK_TEMP_PCT, RANK_TIE_PCT = 1.0, 0.25
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4

# Alias kien truc: DONG KICH THUOC v41 (600875 params, 0 params moi).
UtilityScaleSSMTemporal = ValueScaleSSMTemporal


def compute_utility_stats(utility_train):
    """Thong ke train-only past-only cho chuan-hoa UTILITY (percent, zeros giu).

    utility_train: (n_train,16) utility. Tra ve (mu_u, sigma_eff) float.
    Tai dung logic compute_value_stats (mean/std population, floor 1e-6).
    """
    import numpy as np
    u = np.asarray(utility_train, dtype=np.float64).ravel()
    if u.size == 0 or not np.isfinite(u).all():
        raise ValueError("Invalid train utility for value stats")
    mu = float(np.mean(u))
    sigma = float(np.std(u))
    if not (np.isfinite(mu) and np.isfinite(sigma)):
        raise ValueError("Nonfinite utility stats")
    return mu, float(max(sigma, SIGMA_FLOOR))


def standardized_utility_objective(score_z, aux_z, labels_u, mu, sigma):
    """Value objective chuan-hoa tren UTILITY (thay net% cua v41).

    score_z[...,0]: z-pred; aux_z: z-aux; labels_u ch0 UTILITY percent
    (unconditional, zeros giu); ch1 fill.
    payoff = MSE(z0, (utility-mu)/sigma); aux = MSE(aux_z, direction_u/sigma)
    (direction_u = mean long-utility - mean short-utility percent, khong tru mu).
    """
    mu_f, sig_f = float(mu), float(sigma)
    if not sig_f >= SIGMA_FLOOR:
        raise ValueError("Invalid sigma for utility standardization")
    target = labels_u[..., 0]
    fill = labels_u[..., 1]
    z_target = (target - mu_f) / sig_f
    payoff = F.mse_loss(score_z[..., 0] / 1.0, z_target / 1.0)
    fill_loss = F.binary_cross_entropy_with_logits(score_z[..., 1], fill)
    direction = target[:, :8].mean(-1) - target[:, 8:].mean(-1)
    auxiliary_loss = F.mse_loss(aux_z / 1.0, (direction / sig_f) / 1.0)
    return payoff + 0.1 * fill_loss + 0.1 * auxiliary_loss


def multitask_loss_cov_rank_utility(score, aux, dlogits, quant, exc, labels_u, ydir,
                                    yret, yup, ydn, mu, sigma,
                                    value_w=LOSS_W_VALUE,
                                    rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                                    floor_pos=COV_FLOOR_POS,
                                    rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    """Full v146 loss: value tren Z_u + ranking/coverage tren UTILITY TRADEABLE.

    score[...,0] la Z_u. Ranking/coverage tinh tren
    utility_trade = score_z0*sigma_u + mu_u (percent). KHONG clip o day.
    labels_u: (n,16,3) [utility, fill, win|fill].
    """
    base = standardized_utility_objective(score, aux, labels_u, mu, sigma)
    trade_u = score.float()[..., 0] * float(sigma) + float(mu)
    rank = pairwise_expected_rank_loss(trade_u, labels_u,
                                       temperature_percent=rank_temp,
                                       tie_band_percent=rank_tie)
    counts = torch.bincount(ydir, minlength=3).float() + 1.0
    cw = (counts.sum() / (3 * counts)).to(dlogits.dtype)
    ce = F.cross_entropy(dlogits, ydir, weight=cw)
    qb = pinball(quant, yret)
    ex = F.mse_loss(torch.log1p(exc),
                     torch.log1p(torch.stack([yup, ydn], -1)))
    trade_full = torch.cat([trade_u.unsqueeze(-1), score[..., 1:]], dim=-1)
    cov, mean_pos, en_mean = coverage_floor_loss(trade_full, lambda_cov, floor_pos)
    total = value_w * base + rank_w * rank + LOSS_W_DIR * ce + LOSS_W_Q * qb + LOSS_W_E * ex + cov
    if not torch.isfinite(total):
        raise ValueError("Nonfinite utility training loss")
    return total, {"base": base.detach(), "rank": rank.detach(),
                   "ce": ce.detach(), "qb": qb.detach(), "ex": ex.detach(),
                   "cov": cov.detach(), "mean_pos": mean_pos,
                   "en_mean": en_mean}


# Alias giu tuong thich import style v41 (train/smoke goi multitask_loss_cov_rank).
def multitask_loss_cov_rank(score, aux, dlogits, quant, exc, labels, ydir,
                            yret, yup, ydn, mu=None, sigma=None, value_w=LOSS_W_VALUE,
                            rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                            floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    if mu is None or sigma is None:
        raise ValueError("v146 can mu_u/sigma_u train-window (past-only) cho moi fold")
    return multitask_loss_cov_rank_utility(
        score, aux, dlogits, quant, exc, labels, ydir,
        yret, yup, ydn, mu, sigma,
        value_w=value_w, rank_w=rank_w, lambda_cov=lambda_cov,
        floor_pos=floor_pos, rank_temp=rank_temp, rank_tie=rank_tie)


def predict_ssm_raw_utility(model, sequence, flat, mu, sigma, batch_size=32):
    """Map v8 RAW UTILITY (selection path, KHONG CLIP).

    Model xuat Z_u; de-chuan-hoa: utility_trade = z*sigma_u + mu_u (percent);
    ch0 = utility_trade/fill, ch4 = logit(fill); unconditional = utility_trade.
    """
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
    """Sizing copy RIENG (KHONG dung cho selection): clip utility ve +-cap."""
    import numpy as np
    raw = predict_ssm_raw_utility(model, sequence, flat, mu, sigma, batch_size=batch_size)
    if not float(cap) == 2.0:
        raise ValueError("v146 sizing cap phai 2.0 percent")
    fill = 1 / (1 + np.exp(-np.clip(raw[..., 4], -40, 40)))
    trade = raw[..., 0] * fill
    capped = apply_sizing_cap_numpy(trade, cap=cap)
    out = raw.copy()
    out[..., 0] = capped / fill
    return out


def predict_ssm(model, sequence, flat, batch_size=32, mu=None, sigma=None):
    if mu is None or sigma is None:
        raise ValueError("v146 predict_ssm can mu_u/sigma_u train-window (past-only)")
    return predict_ssm_raw_utility(model, sequence, flat, mu, sigma, batch_size=batch_size)
