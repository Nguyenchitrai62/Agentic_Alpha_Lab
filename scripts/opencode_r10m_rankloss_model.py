"""Opencode R10-M (v38 rankloss): Selective-SSM TAI DUNG tu v35 + pairwise ranking.

Kien truc DONG KICH THUOC v35 (SelectiveSSMTemporal ~0.6M params, causal):
  tai dung VERBATIM class tu scripts/opencode_r9m_nextarch_model.py.
Loss DONG BANG configs/opencode_v38_rankloss.json (sua benh v28 theo v29):
  2.0*objective(score,aux,labels)          [nang value-objective tren aux heads]
  + 0.5*pairwise_expected_rank_loss(expected=score[...,0], labels,
        temperature_percent=1.0, tie_band_percent=0.25)   [nhu v29]
  + 1.0*CE_dir + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48)
  + 3.0*coverage-hinge (GIU NGUYEN v35: mean_pos=mean(relu(en_best)), floor 5e-4).
Policy floor (eval, pre-spec, GIU NGUYEN v35): gate en_best > 0 + fallback top-8.
Calibrate-first (isotonic past-only TRUOC choose) THUC THI o audit local sau,
khong trong file nay.
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
    predict_ssm,
)

QUANTS = (0.1, 0.5, 0.9)
LOSS_W_VALUE, LOSS_W_RANK, LOSS_W_DIR, LOSS_W_Q, LOSS_W_E = 2.0, 0.5, 1.0, 1.0, 0.5
RANK_TEMP_PCT, RANK_TIE_PCT = 1.0, 0.25
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4


def multitask_loss_cov_rank(score, aux, dlogits, quant, exc, labels, ydir,
                            yret, yup, ydn, value_w=LOSS_W_VALUE,
                            rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                            floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    """Full v38 loss: value-objective nang + ranking + aux + coverage-hinge."""
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
        raise ValueError("Nonfinite rankloss training loss")
    return total, {"base": base.detach(), "rank": rank.detach(),
                   "ce": ce.detach(), "qb": qb.detach(), "ex": ex.detach(),
                   "cov": cov.detach(), "mean_pos": mean_pos,
                   "en_mean": en_mean}
