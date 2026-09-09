"""Opencode R19-M (v39 scalecap): Selective-SSM TAI DUNG tu v35/v38 + scale-cap + pairwise ranking.

Kien truc DONG KICH THUOC v35/v38 (SelectiveSSMTemporal ~0.6M params, causal):
  tai dung VERBATIM class tu scripts/opencode_r9m_nextarch_model.py, them
  scale-cap TREN value head (moi o v39, sua overconfidence v38):
    capped0 = CAP * tanh(raw0 / CAP), CAP = 0.05 (+-5%), mode = tanh (pre-spec).
  tanh don dieu -> giu thu tu pairwise ranking; khong them params.
Loss DONG BANG configs/opencode_v60_v39.json:
  2.0*objective(score_capped,aux,labels)   [payoff MSE + 0.1 fill BCE + 0.1 aux, TREN CAPPED]
  + 0.5*pairwise_expected_rank_loss(expected=capped0, labels,
        temperature_percent=1.0, tie_band_percent=0.25)   [nhu v29/v38, TREN CAPPED]
  + 1.0*CE_dir + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48)
  + 3.0*coverage-hinge (GIU NGUYEN v35/v38, TINH TREN CAPPED:
        en_best_capped = max_k capped[k,0]).
Policy floor (eval, pre-spec, GIU NGUYEN): gate en_best_capped > 0 + fallback top-8.
Calibrate-first (isotonic past-only TRUOC choose) THUC THI o audit local sau
tren VAL-PRED EXPORT (val_predictions.npy, moi o v39), khong trong file nay.
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
SCALE_CAP, SCALE_CAP_MODE = 0.05, "tanh"


def apply_scale_cap(raw, cap=SCALE_CAP, mode=SCALE_CAP_MODE):
    """Scale-cap pre-spec v39: chan bien do expected-net, giu thu tu.

    tanh: capped = cap * tanh(raw / cap), |capped| < cap, don dieu nghiem ngat.
    clip: bi CAM o v39 (chi de assertive-error, khong dung).
    """
    if mode != "tanh":
        raise ValueError(f"v39 chi cho phep scale_cap_mode=tanh, nhan {mode!r}")
    if not float(cap) == 0.05:
        raise ValueError(f"v39 scale_cap_cap phai 0.05 (+-5%), nhan {cap!r}")
    return cap * torch.tanh(raw / cap)


def apply_scale_cap_numpy(raw, cap=SCALE_CAP):
    """Numpy mirror cua apply_scale_cap (dung cho bounded-proof, khong train)."""
    import numpy as np
    raw = np.asarray(raw, dtype=np.float64)
    if not float(cap) == 0.05:
        raise ValueError("v39 scale_cap_cap phai 0.05")
    return cap * np.tanh(raw / cap)


class ScaleCapSSMTemporal(SelectiveSSMTemporal):
    """SelectiveSSMTemporal + tanh scale-cap tren score[...,0] (khong them params)."""

    def forward(self, sequence, flat):
        score, aux, dlogits, quant, exc = super().forward(sequence, flat)
        capped0 = apply_scale_cap(score[..., 0])
        capped = torch.stack([capped0, score[..., 1]], dim=-1)
        return (capped, aux, dlogits, quant, exc)


def multitask_loss_cov_rank_cap(score, aux, dlogits, quant, exc, labels, ydir,
                                yret, yup, ydn, value_w=LOSS_W_VALUE,
                                rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                                floor_pos=COV_FLOOR_POS,
                                rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT,
                                scale_cap=SCALE_CAP):
    """Full v39 loss: value-objective (CAPPED) + ranking (CAPPED) + aux + coverage-hinge (CAPPED).

    score[...,0] phai da capped (tu ScaleCapSSMTemporal.forward). Ham nay
    defensive-cap lai de dam bao loss/ranking/policy luon tren mien bounded
    ngay ca khi caller truyen raw (tinh idempotent vi tanh(tanh) van bounded,
    nhung model luon cap truoc nen duong chinh la single-cap).
    """
    if float(scale_cap) != SCALE_CAP:
        raise ValueError("v39 scale_cap_cap phai 0.05")
    capped0 = apply_scale_cap(score[..., 0], cap=scale_cap)
    score = torch.stack([capped0, score[..., 1]], dim=-1)
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
        raise ValueError("Nonfinite scalecap training loss")
    return total, {"base": base.detach(), "rank": rank.detach(),
                   "ce": ce.detach(), "qb": qb.detach(), "ex": ex.detach(),
                   "cov": cov.detach(), "mean_pos": mean_pos,
                   "en_mean": en_mean}


# Alias giu tuong thich import style v38 (train/smoke goi multitask_loss_cov_rank).
def multitask_loss_cov_rank(score, aux, dlogits, quant, exc, labels, ydir,
                            yret, yup, ydn, value_w=LOSS_W_VALUE,
                            rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                            floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    return multitask_loss_cov_rank_cap(
        score, aux, dlogits, quant, exc, labels, ydir, yret, yup, ydn,
        value_w=value_w, rank_w=rank_w, lambda_cov=lambda_cov,
        floor_pos=floor_pos, rank_temp=rank_temp, rank_tie=rank_tie,
        scale_cap=SCALE_CAP)


def predict_ssm_cap(model, sequence, flat, batch_size=32):
    """Map v8 CAPPED (giong temporal_value.predict): ch0 = capped/fill, ch4 = logit(fill).

    unconditional = ch0*fill = capped (bounded +-5%); policy gate dung unconditional.
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
            # Defensive: dam bao capped ngay ca khi model la raw (idempotent).
            capped0 = apply_scale_cap(score[..., 0])
            fill = score[..., 1].sigmoid().clamp(1e-6, 1 - 1e-6)
            block = torch.zeros((*score.shape[:2], 6), device=device)
            block[..., 0], block[..., 4] = capped0 / fill, torch.logit(fill)
            out.append(block.cpu())
    return torch.cat(out).numpy()


# predict_ssm la ten chuan driver v38 goi; v39 tro den ban capped.
def predict_ssm(model, sequence, flat, batch_size=32):
    return predict_ssm_cap(model, sequence, flat, batch_size=batch_size)
