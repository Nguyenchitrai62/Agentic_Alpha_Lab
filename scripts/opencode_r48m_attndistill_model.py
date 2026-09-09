"""Opencode R48-M (v132 attention-distill): small Transformer TAI DUNG pattern v96 + distill loss.

Kien truc (pre-spec configs/opencode_v132_attndistill.json, MUCH cheaper than v96):
  frame encoder SHARED: Linear(6->128) + learned pos (128) + 2 x PreNorm
    TransformerEncoderLayer (d_model=128, nhead=4, ff=256, GELU, norm_first=True,
    batch_first=True), pool concat(last,mean) -> Linear(256->128).
  cross-frame: learned pos (5) + 1 x PreNorm TransformerEncoderLayer (128/4/256)
    + outer residual (wiring parity voi v35/v96).
  fusion/student-head ONLY (KHONG multitask): frame_features/macro/micro/gate/
    action width 128 + student Linear(512->128)+GELU+Dropout+Linear(128->1)
    -> (n,16) student_logits free units (T=1 KL truc tiep vs soft-targets).
Forward signature: forward(sequence, flat) -> logits (n,16) free units.

CAUSAL MASKING — KHONG CAN, GHI NHAN RO RANG (nhu v96):
  Moi frame window chi gom NEN DONG QUA KHU truoc signal time T (cache
  sequences.npy xay tu closed candles; audit v35/v47 da verify close_last<=T
  5628/5628). Cross-frame sap xep 5 frames past-only theo thoi gian. Khong co
  autoregressive decoding (moi decision doc lap, one-shot scoring 16 candidates).
  Vay full bidirectional self-attention TRONG window past-only khong the thay
  tuong lai tuong doi voi T -> live-faithful, khong can causal mask.

Loss DONG BANG configs/opencode_v132_attndistill.json:
  L = 1.0*KL(student||frozen-soft, T=1, soft-subset) PRIMARY
    + 1.0*entropy-floor-penalty (H_floor 2.20 nats, all-train)
    + 0.1*ListNet-listwise TREN HARD (all-train, THAP, khong dan loss)
    + 3.0*coverage-hinge TREN LOGITS (safety net).
Entropy-floor la rule CHONG collapse truc tiep (failure mode v96: pmax gap doi,
entropy thap 11/11 folds): penalty inactive khi healthy (H>=floor).
Tie-break deterministic (v106 verbatim, tren LOGITS, BO fill-desc).
Calibrate-first THUC THI o audit local sau tren VAL-LOGITS EXPORT, khong o day.
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch import nn
from torch.nn import functional as F

from opencode_r9m_nextarch_model import (  # noqa: F401  (tai dung utils/policy v35)
    POLICY_MARGIN,
    POLICY_N_MIN,
    apply_coverage_floor_policy,
    count_params,
    coverage_floor_loss,
    expected_net_best,
    pinball,
)

KL_WEIGHT = 1.0
ENT_LAMBDA = 1.0
ENT_FLOOR_NATS = 2.2
RANK_WEIGHT = 0.1
RANK_TEMP = 1.0
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4
TIE_BREAK_EPS = 1e-6

# Kich thuoc encoder NHO (dong bang config v132; doi so nao cung phai sua config + do lai params).
D_MODEL, NHEAD, FF_DIM = 128, 4, 256
FRAME_LAYERS, CROSS_LAYERS = 2, 1
FRAME_LEN, N_FRAMES = 128, 5


def student_kl(student_logits, soft_targets):
    """KL(student||teacher, T=1) tren soft-subset (student-first, dung mission v101)."""
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


def entropy_floor_penalty(student_logits, floor_nats=ENT_FLOOR_NATS, lambda_ent=ENT_LAMBDA):
    """Entropy-floor penalty CHONG mass-collapse (rule v132, failure mode v96).

    student_logits: (m,16) free units. p = softmax(logits); H_row (nats).
    ent = lambda * mean(relu(floor - H)^2). Inactive khi healthy (H>=floor).
    Tra ve (scalar, mean_H detached, min_H detached).
    """
    if student_logits.ndim != 2 or student_logits.shape[1] != 16:
        raise ValueError("Expected (m,16) student logits")
    if not torch.isfinite(student_logits).all():
        raise ValueError("Nonfinite entropy inputs")
    if not float(floor_nats) == 2.2:
        raise ValueError("v132 entropy floor phai 2.20 nats")
    if not float(lambda_ent) == 1.0:
        raise ValueError("v132 entropy lambda phai 1.0")
    logp = F.log_softmax(student_logits.float(), dim=1)
    p = logp.exp()
    h_row = -(p * logp).sum(dim=1)
    gap = F.relu(float(floor_nats) - h_row)
    ent = float(lambda_ent) * (gap * gap).mean()
    if not torch.isfinite(ent):
        raise ValueError("Nonfinite entropy penalty")
    return ent, h_row.detach().mean(), h_row.detach().min()


def listnet_on_hard(student_logits, labels, temperature=RANK_TEMP):
    """ListNet-listwise THAP tren hard labels (VERBATIM logic v96, weight 0.1 o caller).

    student_logits: (m,16) free units; labels: (m,16,3); ch0 realized percent.
    target = softmax(realized/tau); loss = CE(target, log_softmax(logits/tau)).
    """
    if student_logits.ndim != 2 or student_logits.shape[1] != 16 or labels.ndim != 3:
        raise ValueError("Expected (m,16) logits and (m,16,3) labels")
    if not torch.isfinite(student_logits).all() or not torch.isfinite(labels).all():
        raise ValueError("Nonfinite listwise inputs")
    if not float(temperature) == 1.0:
        raise ValueError("v132 listnet temperature phai 1.0")
    realized = labels[..., 0].float()
    pred = student_logits.float()
    target = F.softmax(realized / float(temperature), dim=-1)
    logp = F.log_softmax(pred / float(temperature), dim=-1)
    loss = -(target * logp).sum(dim=-1).mean()
    if not torch.isfinite(loss):
        raise ValueError("Nonfinite listwise loss")
    return loss


def coverage_hinge_logits(student_logits, lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS):
    """Coverage-hinge TREN LOGITS free units (safety net, inactive khi healthy)."""
    en_best = student_logits.float().amax(dim=1)
    mean_pos = F.relu(en_best).mean()
    gap = F.relu(1.0 - mean_pos / float(floor_pos))
    loss = float(lambda_cov) * gap * gap
    return loss, mean_pos.detach(), en_best.detach().mean()


def attndistill_loss_from_parts(kl_term, student_logits_full, labels_full,
                                kl_w=KL_WEIGHT, ent_w=ENT_LAMBDA,
                                rank_w=RANK_WEIGHT,
                                lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS,
                                rank_temp=RANK_TEMP,
                                floor_nats=ENT_FLOOR_NATS):
    """Full v132 loss tu parts (KL tach rieng vi soft-subset)."""
    rank = listnet_on_hard(student_logits_full, labels_full, temperature=rank_temp)
    ent, mean_h, min_h = entropy_floor_penalty(student_logits_full, floor_nats, ent_w)
    cov, mean_pos, en_mean = coverage_hinge_logits(student_logits_full, lambda_cov, floor_pos)
    kl = torch.as_tensor(float(kl_term), dtype=student_logits_full.dtype, device=student_logits_full.device)
    total = float(kl_w) * kl + ent + float(rank_w) * rank + cov
    if not torch.isfinite(total):
        raise ValueError("Nonfinite attndistill training loss")
    return total, {"kl": kl.detach(), "ent": ent.detach(),
                   "rank": rank.detach(), "cov": cov.detach(),
                   "mean_pos": mean_pos, "en_mean": en_mean,
                   "mean_h": mean_h, "min_h": min_h}


class AttnDistillTemporal(nn.Module):
    """Small attention-distill v132 (~0.5-0.7M, so dem trong config/smoke).

    Input DONG BANG v35/v96/v106: sequence (n,5,128,6) + flat (n,133).
    Output: student_logits (n,16) free units (T=1 KL truc tiep).
    """

    def __init__(self, candidates, width=D_MODEL, frame_dim=D_MODEL,
                 frame_layers=FRAME_LAYERS, cross_layers=CROSS_LAYERS,
                 nhead=NHEAD, ff_dim=FF_DIM, dropout=0.1, n_flat=133):
        super().__init__()
        if not (frame_dim == width == D_MODEL and nhead == NHEAD and ff_dim == FF_DIM
                and frame_layers == FRAME_LAYERS and cross_layers == CROSS_LAYERS):
            raise ValueError("v132 dims phai dong bang config (128/4/256/2/1)")
        self.n_flat = n_flat
        self.register_buffer("feature_mean", torch.zeros(n_flat))
        self.register_buffer("feature_scale", torch.ones(n_flat))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale", torch.tensor([1., 1.5, 3., 3., 6., 7.]))
        # Frame encoder shared (weight-shared tren 5 frames, nhu v96).
        self.frame_in = nn.Linear(6, frame_dim)
        self.frame_pos = nn.Embedding(FRAME_LEN, frame_dim)
        frame_layer = nn.TransformerEncoderLayer(
            d_model=frame_dim, nhead=nhead, dim_feedforward=ff_dim,
            dropout=dropout, activation="gelu", batch_first=True, norm_first=True)
        self.frame_enc = nn.TransformerEncoder(frame_layer, num_layers=frame_layers)
        self.frame_pool = nn.Linear(2 * frame_dim, width)
        # Cross-frame (5 frame vectors, past-only co thu tu; khong can mask).
        self.cross_pos = nn.Embedding(N_FRAMES, width)
        cross_layer = nn.TransformerEncoderLayer(
            d_model=width, nhead=nhead, dim_feedforward=ff_dim,
            dropout=dropout, activation="gelu", batch_first=True, norm_first=True)
        self.cross_enc = nn.TransformerEncoder(cross_layer, num_layers=cross_layers)
        # Fusion GIU hinh dang v96 (width 128) + student head ONLY.
        self.frame_features = nn.Sequential(nn.Linear(8, width), nn.GELU())
        self.macro = nn.Sequential(nn.Linear(2 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.micro = nn.Sequential(nn.Linear(3 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.gate = nn.Linear(width, width)
        self.action = nn.Sequential(nn.Linear(6, width), nn.GELU())
        self.student = nn.Sequential(nn.Linear(4 * width, width), nn.GELU(),
                                     nn.Dropout(dropout), nn.Linear(width, 1))

    def context(self, sequence, flat):
        if sequence.ndim != 4 or sequence.shape[1:] != (5, 128, 6):
            raise ValueError("Expected [batch, 5, 128, 6] closed-candle contexts")
        if flat.shape[-1] != self.n_flat:
            raise ValueError(f"Expected flat {self.n_flat}, got {flat.shape[-1]}")
        n = len(sequence)
        device = sequence.device
        pos128 = self.frame_pos(torch.arange(FRAME_LEN, device=device)).unsqueeze(0)
        frames = []
        for i in range(5):  # encoder shared tren 5 frames (weight-shared, nhu v96)
            z = self.frame_in(sequence[:, i]) + pos128
            z = self.frame_enc(z)
            frames.append(self.frame_pool(torch.cat((z[:, -1], z.mean(1)), -1)))
        stacked = torch.stack(frames, 1)
        pos5 = self.cross_pos(torch.arange(N_FRAMES, device=device)).unsqueeze(0)
        scanned = self.cross_enc(stacked + pos5) + stacked  # outer residual (parity v35/v96)
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
        logits = self.student(torch.cat((ma, mi, ac, (ma + mi) * ac), -1)).squeeze(-1)
        return logits


def deterministic_best_index(logits_row, candidates, eps=TIE_BREAK_EPS):
    """Tie-break deterministic pre-spec v132 (TREN LOGITS free units, BO fill-desc).

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
        raise ValueError("v132 tie_break_eps phai 1e-6")
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


def predict_attn_logits(model, sequence, flat, batch_size=32):
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
