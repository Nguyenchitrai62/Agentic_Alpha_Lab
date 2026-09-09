"""Opencode R32-M (v96 big-Transformer): Transformer-encoder TAI DUNG discipline v41 + encoder moi.

Kien truc (moi, hoan toan khac SSM/TCN/GRU/MLP):
  frame encoder SHARED: Linear(6->320) + learned pos (128) + 5 x PreNorm
    TransformerEncoderLayer (d_model=320, nhead=8, ff=1024, GELU, norm_first=True,
    batch_first=True), pool concat(last,mean) -> Linear(640->320).
  cross-frame: learned pos (5) + 2 x PreNorm TransformerEncoderLayer (320/8/1024)
    + outer residual (wiring parity voi v35 cross_ssm + stack).
  fusion/heads: GIU NGUYEN hinh dang v35/v41 (frame_features/macro/micro/gate/
    action/score/regime/dir/quant/exc, width 320) de so sanh cong bang objective.
  Forward signature DONG BANG v41: forward(sequence, flat) -> (score, aux, dir,
    quant, exc); score[...,0] = Z (chuan-hoa), score[...,1] = fill logit.

CAUSAL MASKING — KHONG CAN, GHI NHAN RO RANG:
  Moi frame window chi gom NEN DONG QUA KHU truoc signal time T (cache
  sequences.npy xay tu closed candles; audit v35/v47 da verify close_last<=T
  5628/5628). Cross-frame sap xep 5 frames past-only theo thoi gian. Khong co
  autoregressive decoding (moi decision doc lap, one-shot scoring 16 candidates).
  Vay full bidirectional self-attention TRONG window past-only khong the thay
  tuong lai tuong doi voi T -> live-faithful, khong can causal mask. Mask chi
  can neu decode tuong lai hoac window lan sang T (khong xay ra o day).

XLA-TOLERABLE (target DEFAULT T4x2; TPU la future option, KHONG phai submit nay):
  Chi dung: nn.Embedding (pos lookup), nn.Linear, nn.LayerNorm, nn.Dropout,
  nn.MultiheadAttention (softmax-based math path; stable_backend tat fastpath
  nen tranh fused kernels thieu XLA lowering), GELU, softmax/log_softmax,
  clamp/mean/cat. KHONG co: recurrence Python-loop theo timestep (diem gay XLA
  cua SSM), dynamic shapes (co dinh 128/5/16), data-dependent control flow
  trong forward, custom autograd, in-place mutation. Khong phat hien op nao
  gay vo XLA; ghi nhan: MuAttn fastpath-disabled la lua chon chu dong cho XLA.

Loss DONG BANG configs/opencode_v96_transformer.json (DOI vs v41 o ranking):
  1.0*value_objective_chuan_hoa(score_z,aux_z,labels,mu_train,sigma_train) [v41 verbatim]
  + 2.0*ListNet-listwise TREN TRADEABLE percent (PRIMARY: 2.0 >= 1.0 value)
  + 1.0*CE_dir + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48)
  + 3.0*coverage-hinge TREN TRADEABLE (en_best_trade = max_k trade).
De-chuan-hoa: trade = score_z*sigma + mu (percent, affine giu thu tu).
KHONG CLIP tren selection path (giu raw order end-to-end, bai hoc v40 REJECTED).
Sizing cap CHI tren file rieng: capped_sizing = clip(trade, +-2.0 percent).
Tie-break deterministic (v40/v41 verbatim, tren raw tradeable).
Calibrate-first (isotonic outlier-robust past-only TRUOC choose) THUC THI o audit
local sau tren VAL-PRED EXPORT RAW (val_predictions.npy), khong o day.
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch import nn
from torch.nn import functional as F

from agentic_alpha_lab.models.macro_micro_value import objective  # noqa: F401 (ghi nhan goc; v96 dung objective chuan-hoa rieng nhu v41)

from opencode_r9m_nextarch_model import (  # noqa: F401  (tai dung heads/fusion wiring + utils v35)
    POLICY_MARGIN,
    POLICY_N_MIN,
    apply_coverage_floor_policy,
    count_params,
    coverage_floor_loss,
    expected_net_best,
    pinball,
)

QUANTS = (0.1, 0.5, 0.9)
LOSS_W_VALUE, LOSS_W_RANK, LOSS_W_DIR, LOSS_W_Q, LOSS_W_E = 1.0, 2.0, 1.0, 1.0, 0.5
RANK_TEMP_PCT = 1.0
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4
SIZING_CAP, SIZING_CAP_MODE = 2.0, "clip"
TIE_BREAK_EPS = 1e-6
SIGMA_FLOOR = 1e-6

# Kich thuoc encoder (dong bang config v96; doi so nao cung phai sua config + do lai params).
D_MODEL, NHEAD, FF_DIM = 320, 8, 1024
FRAME_LAYERS, CROSS_LAYERS = 5, 2
FRAME_LEN, N_FRAMES = 128, 5


def compute_value_stats(labels_train):
    """Thong ke train-only past-only cho chuan-hoa (labels percent, zeros giu nguyen).

    labels_train: (n_train,16,3) hoac (n_train,16) ch0. Tra ve (mu, sigma_eff) float.
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


def listnet_loss(trade, labels, temperature_percent=RANK_TEMP_PCT):
    """ListNet listwise PRIMARY (v96 moi; thay pairwise cua v41 lam so chinh).

    trade: (n,16) unconditional tradeable percent (de-chuan-hoa, KHONG CLIP).
    labels: (n,16,3); ch0 realized utility percent (0 neu unfilled).
    target = softmax(realized/tau); loss = CE(target, log_softmax(trade/tau)).
    Don vi percent hai ve (tau=1.0%) nen so sanh duoc voi diagnostic cu.
    """
    if trade.ndim != 2 or trade.shape[1] != 16 or labels.ndim != 3:
        raise ValueError("Expected (n,16) trade and (n,16,3) labels")
    if not torch.isfinite(trade).all() or not torch.isfinite(labels).all():
        raise ValueError("Nonfinite listwise inputs")
    if not float(temperature_percent) == 1.0:
        raise ValueError("v96 listnet temperature phai 1.0 percent")
    tau = float(temperature_percent)
    realized = labels[..., 0].float()
    pred = trade.float()
    target = F.softmax(realized / tau, dim=-1)
    logp = F.log_softmax(pred / tau, dim=-1)
    loss = -(target * logp).sum(dim=-1).mean()
    if not torch.isfinite(loss):
        raise ValueError("Nonfinite listwise loss")
    return loss


def apply_sizing_cap(trade, cap=SIZING_CAP):
    """Sizing-cap RIENG (torch): clip trade percent ve +-cap. KHONG dung cho selection."""
    if not float(cap) == 2.0:
        raise ValueError("v96 sizing cap phai 2.0 percent")
    return torch.clamp(trade, -float(cap), float(cap))


def apply_sizing_cap_numpy(trade, cap=SIZING_CAP):
    """Numpy mirror cua sizing-cap rieng (chi cho file sizing + demo, khong train/selection)."""
    import numpy as np
    trade = np.asarray(trade, dtype=np.float64)
    if not float(cap) == 2.0:
        raise ValueError("v96 sizing cap phai 2.0 percent")
    return np.clip(trade, -float(cap), float(cap))


def deterministic_best_index(expected_row, fill_row, candidates, eps=TIE_BREAK_EPS):
    """Tie-break deterministic pre-spec v96 (VERBATIM v40/v41, tren RAW TRADEABLE).

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
        raise ValueError("v96 tie_break_eps phai 1e-6")
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


class TransformerTemporal(nn.Module):
    """Transformer-encoder big-model v96 (~8-12M, so dem trong config).

    Input DONG BANG v35/v41: sequence (n,5,128,6) + flat (n,133).
    Output DONG BANG v41: (score (n,16,2) [z, fill-logit], aux (n,),
      dlogits (n,3), quant (n,3), exc (n,2)).
    """

    def __init__(self, candidates, width=D_MODEL, frame_dim=D_MODEL,
                 frame_layers=FRAME_LAYERS, cross_layers=CROSS_LAYERS,
                 nhead=NHEAD, ff_dim=FF_DIM, dropout=0.1, n_flat=133):
        super().__init__()
        if not (frame_dim == width == D_MODEL and nhead == NHEAD and ff_dim == FF_DIM
                and frame_layers == FRAME_LAYERS and cross_layers == CROSS_LAYERS):
            raise ValueError("v96 dims phai dong bang config (320/8/1024/5/2)")
        self.n_flat = n_flat
        self.register_buffer("feature_mean", torch.zeros(n_flat))
        self.register_buffer("feature_scale", torch.ones(n_flat))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale", torch.tensor([1., 1.5, 3., 3., 6., 7.]))
        # Frame encoder shared (weight-shared tren 5 frames, nhu SSM cu).
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
        # Fusion/heads GIU NGUYEN hinh dang v35 (width 320 thay 192).
        self.frame_features = nn.Sequential(nn.Linear(8, width), nn.GELU())
        self.macro = nn.Sequential(nn.Linear(2 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.micro = nn.Sequential(nn.Linear(3 * width, width), nn.GELU(), nn.Dropout(dropout))
        self.gate = nn.Linear(width, width)
        self.action = nn.Sequential(nn.Linear(6, width), nn.GELU())
        self.score = nn.Sequential(nn.Linear(4 * width, width), nn.GELU(),
                                   nn.Dropout(dropout), nn.Linear(width, 2))
        self.regime = nn.Linear(width, 1)
        self.dir = nn.Linear(2 * width, 3)
        self.quant = nn.Linear(2 * width, 3)
        self.exc = nn.Linear(2 * width, 2)

    def context(self, sequence, flat):
        if sequence.ndim != 4 or sequence.shape[1:] != (5, 128, 6):
            raise ValueError("Expected [batch, 5, 128, 6] closed-candle contexts")
        if flat.shape[-1] != self.n_flat:
            raise ValueError(f"Expected flat {self.n_flat}, got {flat.shape[-1]}")
        n = len(sequence)
        device = sequence.device
        pos128 = self.frame_pos(torch.arange(FRAME_LEN, device=device)).unsqueeze(0)
        frames = []
        for i in range(5):  # encoder shared tren 5 frames (weight-shared, nhu SSM cu)
            z = self.frame_in(sequence[:, i]) + pos128
            z = self.frame_enc(z)
            frames.append(self.frame_pool(torch.cat((z[:, -1], z.mean(1)), -1)))
        stacked = torch.stack(frames, 1)
        pos5 = self.cross_pos(torch.arange(N_FRAMES, device=device)).unsqueeze(0)
        scanned = self.cross_enc(stacked + pos5) + stacked  # outer residual (parity v35)
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
        score = self.score(torch.cat((ma, mi, ac, (ma + mi) * ac), -1))
        ctx = torch.cat((macro, micro), -1)
        return (score, self.regime(macro).squeeze(-1), self.dir(ctx),
                self.quant(ctx), F.softplus(self.exc(ctx)))


def standardized_value_objective(score_z, aux_z, labels, mu, sigma):
    """Value objective chuan-hoa v96 (VERBATIM v41, weight giam 2.0 -> 1.0).

    payoff = MSE(score_z0, (target-mu)/sigma); aux = MSE(aux_z, direction/sigma);
    fill BCE giu nguyen. Tra ve scalar (payoff + 0.1*fill + 0.1*aux).
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


def multitask_loss_cov_rank_list(score, aux, dlogits, quant, exc, labels, ydir,
                                 yret, yup, ydn, mu, sigma,
                                 value_w=LOSS_W_VALUE,
                                 rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                                 floor_pos=COV_FLOOR_POS,
                                 rank_temp=RANK_TEMP_PCT):
    """Full v96 loss: value tren Z + ListNet/coverage tren TRADEABLE (de-chuan-hoa).

    score[...,0] la Z. Ranking/coverage tinh tren trade = score_z0*sigma + mu
    (percent). KHONG clip o day. Ranking PRIMARY: rank_w=2.0 >= value_w=1.0.
    """
    base = standardized_value_objective(score, aux, labels, mu, sigma)
    trade = score.float()[..., 0] * float(sigma) + float(mu)
    rank = listnet_loss(trade, labels, temperature_percent=rank_temp)
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
        raise ValueError("Nonfinite transformer training loss")
    return total, {"base": base.detach(), "rank": rank.detach(),
                   "ce": ce.detach(), "qb": qb.detach(), "ex": ex.detach(),
                   "cov": cov.detach(), "mean_pos": mean_pos,
                   "en_mean": en_mean}


# Alias giu tuong thich import style v38/v39/v40/v41 (train/smoke goi multitask_loss_cov_rank).
def multitask_loss_cov_rank(score, aux, dlogits, quant, exc, labels, ydir,
                            yret, yup, ydn, mu=None, sigma=None, value_w=LOSS_W_VALUE,
                            rank_w=LOSS_W_RANK, lambda_cov=COV_LAMBDA,
                            floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=None):
    if mu is None or sigma is None:
        raise ValueError("v96 can mu/sigma train-window (past-only) cho moi fold")
    return multitask_loss_cov_rank_list(
        score, aux, dlogits, quant, exc, labels, ydir,
        yret, yup, ydn, mu, sigma,
        value_w=value_w, rank_w=rank_w, lambda_cov=lambda_cov,
        floor_pos=floor_pos, rank_temp=rank_temp)


def predict_tf_raw(model, sequence, flat, mu, sigma, batch_size=32):
    """Map v8 RAW TRADEABLE v96 (selection path, KHONG CLIP).

    Model xuat Z; de-chuan-hoa: trade = z*sigma + mu (percent);
    ch0 = trade/fill, ch4 = logit(fill). unconditional = ch0*fill = trade.
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


def predict_tf_sizing_capped(model, sequence, flat, mu, sigma, batch_size=32, cap=SIZING_CAP):
    """Sizing copy RIENG v96 (KHONG dung cho selection): clip trade ve +-cap percent."""
    import numpy as np
    raw = predict_tf_raw(model, sequence, flat, mu, sigma, batch_size=batch_size)
    if not float(cap) == 2.0:
        raise ValueError("v96 sizing cap phai 2.0 percent")
    fill = 1 / (1 + np.exp(-np.clip(raw[..., 4], -40, 40)))
    trade = raw[..., 0] * fill
    capped = apply_sizing_cap_numpy(trade, cap=cap)
    out = raw.copy()
    out[..., 0] = capped / fill
    return out


# predict_tf la ten chuan driver goi; tro den ban RAW (selection, khong clip).
def predict_tf(model, sequence, flat, batch_size=32, mu=None, sigma=None):
    if mu is None or sigma is None:
        raise ValueError("v96 predict_tf can mu/sigma train-window (past-only)")
    return predict_tf_raw(model, sequence, flat, mu, sigma, batch_size=batch_size)
