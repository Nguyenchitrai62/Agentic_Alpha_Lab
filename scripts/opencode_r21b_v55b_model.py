"""Opencode R21-B (v55b = v55 + margin scale-cap): Selective-SSM encoder TAI DUNG
VERBATIM tu v55 + MOT thay doi duy nhat: hard cap tanh tren rank logits.

Clone chinh xac RankOnlySSM (597409 params, 0 params them boi cap). Cap rule
(pre-spec trong configs/opencode_v66_v55b.json, muc cap_rule):
    capped = CAP * tanh(raw / CAP), CAP = 3.0 (logit ordinal units)
Ap dung elementwise TRUOC ListNet loss, TRUOC threshold-fit, TRUOC gate/policy,
TRUOC export. tanh don dieu -> thu tu 16 candidates trong moi decision GIU
NGUYEN chinh xac; chi margin scale bi nen (|margin_capped| <= 2*CAP = 6.0).

Lua chon nay (thay vi adaptive tau = max(1.0%, validation-margin-scale)):
  - cung tau scale ca target lan pred trong ListNet v55 -> adaptive tau doi
    objective hoc; hard cap giu target softmax NGUYEN VEN;
  - adaptive tau khong bound test-time margins; hard cap bound theo cau truc;
  - CAP la hang so cau hinh (khong fit per-fold) -> khong them be mat leakage.
Tien le: v39 tanh cap +-5% tren value head (% units); v55b tanh 3.0 tren rank
logits (ordinal units). Clip bi LOAI (vung bang mat gradient + pha ties).
"""

import torch  # noqa: F401  (torch truoc pandas)
from torch import nn  # noqa: F401

# Tai dung VERBATIM tu v55 (encoder + loss + gate helpers + mapping).
from opencode_r17b_rankonly_model import (  # noqa: F401
    RANK_GATE_PERCENTILE,
    RANK_TEMPERATURE_PERCENT,
    RankOnlySSM,
    apply_rank_gate,
    count_params,
    listnet_rank_loss,
    predict_rank,
    rank_logits_to_signals,
    rank_top1_margin_np,
)

LOGIT_CAP = 3.0
LOGIT_MARGIN_BOUND = 2.0 * LOGIT_CAP


def cap_rank_logits_torch(raw, cap=LOGIT_CAP):
    """Hard cap tanh tren logits (giong v39, khac don vi). Don dieu, 0 params."""
    if cap <= 0:
        raise ValueError("Invalid logit cap")
    if not torch.isfinite(raw).all():
        raise ValueError("Nonfinite raw rank logits")
    capped = cap * torch.tanh(raw / cap)
    if not torch.isfinite(capped).all():
        raise ValueError("Nonfinite capped rank logits")
    return capped


def cap_rank_logits_np(raw, cap=LOGIT_CAP):
    """Ban numpy (inference/export/audit). Don dieu elementwise."""
    import numpy as np
    if cap <= 0:
        raise ValueError("Invalid logit cap")
    mat = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(mat).all():
        raise ValueError("Nonfinite raw rank logits")
    return (cap * np.tanh(mat / cap)).astype(np.float32)


def capped_listnet_rank_loss(raw_pred, labels,
                             temperature_percent=RANK_TEMPERATURE_PERCENT,
                             cap=LOGIT_CAP):
    """ListNet v55 (VERBATIM) tinh TREN CAPPED logits. Target softmax KHONG DOI."""
    return listnet_rank_loss(cap_rank_logits_torch(raw_pred, cap),
                             labels, temperature_percent=temperature_percent)


def capped_top1_margin_np(raw_logits, cap=LOGIT_CAP):
    """Margins tu capped logits (bounded |margin| <= 2*CAP)."""
    return rank_top1_margin_np(cap_rank_logits_np(raw_logits, cap))


def capped_logits_to_signals(raw_test_logits, threshold, cap=LOGIT_CAP):
    """Mapping chuan v55b: cap -> top1/margin -> gate p70 (else WAIT)."""
    import numpy as np
    capped = cap_rank_logits_np(raw_test_logits, cap)
    top1, margins = rank_top1_margin_np(capped)
    picks = apply_rank_gate(margins, threshold)
    chosen = np.full(len(top1), -1, dtype=np.int64)
    chosen[picks] = top1[picks]
    return chosen, margins, capped
