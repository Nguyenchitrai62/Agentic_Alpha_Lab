"""Opencode R69-M (v159 regimemoe): shared SSM encoder + TWO expert value+ranking heads + frozen router.

Kien truc: tai dung VERBATIM SelectiveSSM1D + encoder/context/action wiring tu
scripts/opencode_r9m_nextarch_model.py (causal). Giu NGUYEN score head goc lam
expert-quiet + them 1 score head DONG KICH THUOC lam expert-rest
(Linear 4*width->width + GELU + Dropout + Linear width->2, 148034 params moi).
Aux heads (regime/dir/quant/exc) DUNG CHUNG 1 lan tu shared context.
Router FROZEN past-only (vol_low & fund_low -> quiet else rest, EXACT v103 rule,
NO learned gating, 0 params) — chi selection/export, KHONG trong loss.
Loss DONG BANG configs/opencode_v159_regimemoe.json:
  [2.0*value_quiet(z) + 0.5*rank_quiet_weighted(trade_q, opt_B) + 3.0*cov_quiet(trade_q)]
+ [2.0*value_rest(z) + 0.5*rank_rest_uniform(trade_r) + 3.0*cov_rest(trade_r)]
+ 1.0*CE_dir + 1.0*pinball P10/P50/P90 + 0.5*MSE-log1p MFE/MAE (H=48, shared).
Value scale-at-origin: 1 cap (mu,sigma) train-only past-only DUNG CHUNG 2 experts.
KHONG CLIP tren selection path (giu raw order end-to-end, giu v41/v145).
Sizing cap CHI tren file rieng ROUTED +-2.0%.
Tie-break deterministic VERBATIM v40/v41/v145 tren expert-duoc-chon RAW.
Calibrate-first THUC THI o audit local sau tren VAL-PRED EXPORT ROUTED RAW.
"""

import torch  # noqa: F401  (torch truoc pandas)
from torch import nn
from torch.nn import functional as F

from agentic_alpha_lab.models.macro_micro_value import objective  # noqa: F401 (ghi nhan goc; v159 dung objective chuan-hoa rieng moi expert)
from agentic_alpha_lab.models.ranked_loss import pairwise_expected_rank_loss  # noqa: F401 (ghi nhan goc; v159 dung ban weighted/uniform per-row)

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
LOSS_W_VALUE, LOSS_W_RANK_Q, LOSS_W_RANK_R, LOSS_W_DIR, LOSS_W_Q, LOSS_W_E = 2.0, 0.5, 0.5, 1.0, 1.0, 0.5
RANK_TEMP_PCT, RANK_TIE_PCT = 1.0, 0.25
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4
SIZING_CAP = 2.0
TIE_BREAK_EPS = 1e-6
SIGMA_FLOOR = 1e-6
UPWEIGHT_LLIKE = 2.0
VOL_CUT_V56 = 0.01338037015711381
FUND_ABS = 0.0001


def compute_value_stats(labels_train):
    """Thong ke train-only past-only cho chuan-hoa (labels percent, zeros giu nguyen).

    labels_train: (n_train,16,3) hoac (n_train,16) ch0. Tra ve (mu, sigma_eff) float.
    1 cap DUNG CHUNG cho ca hai experts (pre-spec v159).
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


def apply_sizing_cap_numpy(trade, cap=SIZING_CAP):
    """Sizing-cap RIENG tren ROUTED (numpy): clip trade percent ve +-cap."""
    import numpy as np
    trade = np.asarray(trade, dtype=np.float64)
    if not float(cap) == 2.0:
        raise ValueError("v159 sizing cap phai 2.0 percent")
    return np.clip(trade, -float(cap), float(cap))


def compute_upweights(vol_high, fund_high, factor=UPWEIGHT_LLIKE):
    """Upweight vector EXACT v103 rule (opt_B): w=2.0 neu (vol_high==0 & fund_high==0) else 1.0.

    Dung CHO expert-quiet ranking. Expert-rest dung uniform (w=1.0).
    """
    import numpy as np
    vh = np.asarray(vol_high).reshape(-1)
    fh = np.asarray(fund_high).reshape(-1)
    if vh.shape != fh.shape:
        raise ValueError("vol/fund shape mismatch")
    if not float(factor) == 2.0:
        raise ValueError("v159 upweight factor phai 2.0")
    like = (vh == 0) & (fh == 0)
    w = np.where(like, float(factor), 1.0).astype(np.float64)
    return w, like.astype(bool)


def compute_router_mask(vol_high, fund_high):
    """Router frozen EXACT v103 rule: quiet NEU (vol_high==0 & fund_high==0) else rest.

    Past-only descriptors tai decision T. KHONG learned gating, KHONG fit.
    Tra ve bool array (True = quiet-expert).
    """
    import numpy as np
    vh = np.asarray(vol_high).reshape(-1)
    fh = np.asarray(fund_high).reshape(-1)
    if vh.shape != fh.shape:
        raise ValueError("vol/fund shape mismatch for router")
    return ((vh == 0) & (fh == 0))


def router_stats(mask):
    """Thong ke record moi fold/seed: counts + fracs (past-only descriptors)."""
    import numpy as np
    m = np.asarray(mask).reshape(-1).astype(bool)
    n = int(m.size)
    n_q = int(m.sum())
    return {"n": n, "n_quiet": n_q, "n_rest": int(n - n_q),
            "frac_quiet": float(n_q / n) if n else float("nan"),
            "frac_rest": float((n - n_q) / n) if n else float("nan")}


def upweight_stats(weights, like):
    """Thong ke record moi fold/seed: frac/mean/ESS (past-only descriptors)."""
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


def per_row_pairwise(expected, labels,
                     temperature_percent=RANK_TEMP_PCT,
                     tie_band_percent=RANK_TIE_PCT):
    """Pairwise ranking VERBATIM logic per-row (kem WAIT=0). Tra ve per_row (m,)."""
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
    if not torch.isfinite(per_row).all():
        raise ValueError("Nonfinite per-row ranking loss")
    return per_row


def weighted_pairwise_rank_loss(expected, labels, weights=None,
                                temperature_percent=RANK_TEMP_PCT,
                                tie_band_percent=RANK_TIE_PCT):
    """Pairwise ranking VERBATIM per-row + weighted mean (opt_B cho quiet; None/uniform cho rest)."""
    per_row = per_row_pairwise(expected, labels, temperature_percent, tie_band_percent)
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
    """Tie-break deterministic pre-spec v159 (giu VERBATIM v40/v41/v145, tren expert-duoc-chon RAW).

    expected_row: (16,) expected tradeable percent cua EXPERT DUOC CHON (RAW, khong clip).
    fill_row: (16,) fill logit cua EXPERT DUOC CHON (score_e[...,1]).
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
        raise ValueError("v159 tie_break_eps phai 1e-6")
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


class RegimeMoESSMTemporal(SelectiveSSMTemporal):
    """Shared SSM encoder + TWO expert score heads (quiet + rest), aux shared.

    Encoder/context/action/aux wiring GIU NGUYEN SelectiveSSMTemporal (causal).
    score (goc) -> expert-quiet; score_rest (moi, DONG KICH THUOC) -> expert-rest.
    Forward tra ve (score_quiet_z, score_rest_z, aux_z, dlogits, quant, exc).
    Router KHONG trong model (frozen ngoai, past-only descriptors).
    """

    def __init__(self, candidates, width=192, frame_dim=64, frame_state=16,
                 frame_layers=2, cross_state=16, dropout=0.1, n_flat=133):
        super().__init__(candidates, width=width, frame_dim=frame_dim,
                         frame_state=frame_state, frame_layers=frame_layers,
                         cross_state=cross_state, dropout=dropout, n_flat=n_flat)
        # Hai expert heads DOC LAP (moi head DONG KICH THUOC score goc v35/v41 de
        # state_dict khong share-storage; tong = 600875 - 148034 + 2*148034 = 748909).
        # Xoa score goc (giu 1 head lam quiet + 1 head lam rest, khong giu head thua).
        del self.score
        self.score_quiet = nn.Sequential(
            nn.Linear(4 * width, width), nn.GELU(),
            nn.Dropout(dropout), nn.Linear(width, 2))
        self.score_rest = nn.Sequential(
            nn.Linear(4 * width, width), nn.GELU(),
            nn.Dropout(dropout), nn.Linear(width, 2))

    def forward(self, sequence, flat):
        macro, micro = self.context(sequence, flat)
        action = self.action(self.candidates / self.candidate_scale)
        k, n = len(action), len(sequence)
        ma = macro[:, None].expand(-1, k, -1)
        mi = micro[:, None].expand(-1, k, -1)
        ac = action[None].expand(n, -1, -1)
        feat = torch.cat((ma, mi, ac, (ma + mi) * ac), -1)
        score_q = self.score_quiet(feat)
        score_r = self.score_rest(feat)
        ctx = torch.cat((macro, micro), -1)
        return (score_q, score_r, self.regime(macro).squeeze(-1), self.dir(ctx),
                self.quant(ctx), F.softplus(self.exc(ctx)))


def standardized_value_objective_single(score_z, aux_z, labels, mu, sigma):
    """Value objective chuan-hoa cho 1 expert (giu VERBATIM v41/v145).

    score_z[...,0]: z-pred expert; aux_z: z-aux SHARED (chi tinh 1 lan o caller
    neu muon tranh double-count — o day giu cong thuc de caller quyet dinh).
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


def multitask_loss_moe(score_q, score_r, aux, dlogits, quant, exc, labels, ydir,
                       yret, yup, ydn, mu, sigma, weights_quiet=None,
                       value_w=LOSS_W_VALUE, rank_w_q=LOSS_W_RANK_Q,
                       rank_w_r=LOSS_W_RANK_R, lambda_cov=COV_LAMBDA,
                       floor_pos=COV_FLOOR_POS,
                       rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    """Full v159 MoE loss: 2 experts (value+rank+coverage rieng) + aux shared 1 lan.

    score_q/score_r: (m,16,2) z moi expert. aux/dlogits/quant/exc: shared.
    weights_quiet: (m,) opt_B (2.0 L-like else 1.0) CHO quiet; rest luon uniform.
    Tra ve (total, parts incl rank_per_row moi expert).
    """
    base_q = standardized_value_objective_single(score_q, aux, labels, mu, sigma)
    base_r = standardized_value_objective_single(score_r, aux, labels, mu, sigma)
    trade_q = score_q.float()[..., 0] * float(sigma) + float(mu)
    trade_r = score_r.float()[..., 0] * float(sigma) + float(mu)
    rank_q, per_q = weighted_pairwise_rank_loss(trade_q, labels, weights_quiet,
                                                temperature_percent=rank_temp,
                                                tie_band_percent=rank_tie)
    rank_r, per_r = weighted_pairwise_rank_loss(trade_r, labels, None,
                                                temperature_percent=rank_temp,
                                                tie_band_percent=rank_tie)
    counts = torch.bincount(ydir, minlength=3).float() + 1.0
    cw = (counts.sum() / (3 * counts)).to(dlogits.dtype)
    ce = F.cross_entropy(dlogits, ydir, weight=cw)
    qb = pinball(quant, yret)
    ex = F.mse_loss(torch.log1p(exc),
                     torch.log1p(torch.stack([yup, ydn], -1)))
    trade_q_full = torch.cat([trade_q.unsqueeze(-1), score_q[..., 1:]], dim=-1)
    trade_r_full = torch.cat([trade_r.unsqueeze(-1), score_r[..., 1:]], dim=-1)
    cov_q, mean_pos_q, en_mean_q = coverage_floor_loss(trade_q_full, lambda_cov, floor_pos)
    cov_r, mean_pos_r, en_mean_r = coverage_floor_loss(trade_r_full, lambda_cov, floor_pos)
    total = (value_w * base_q + rank_w_q * rank_q + cov_q
             + value_w * base_r + rank_w_r * rank_r + cov_r
             + LOSS_W_DIR * ce + LOSS_W_Q * qb + LOSS_W_E * ex)
    if not torch.isfinite(total):
        raise ValueError("Nonfinite MoE training loss")
    return total, {"base_q": base_q.detach(), "rank_q": rank_q.detach(),
                   "cov_q": cov_q.detach(), "mean_pos_q": mean_pos_q,
                   "en_mean_q": en_mean_q, "rank_per_row_q": per_q,
                   "base_r": base_r.detach(), "rank_r": rank_r.detach(),
                   "cov_r": cov_r.detach(), "mean_pos_r": mean_pos_r,
                   "en_mean_r": en_mean_r, "rank_per_row_r": per_r,
                   "ce": ce.detach(), "qb": qb.detach(), "ex": ex.detach()}


# Alias giu tuong thich import style v38/v39/v40/v41/v145 (train/smoke goi multitask_loss_cov_rank).
def multitask_loss_cov_rank(score_q, score_r, aux, dlogits, quant, exc, labels, ydir,
                            yret, yup, ydn, mu=None, sigma=None, weights=None,
                            value_w=LOSS_W_VALUE,
                            rank_w_q=LOSS_W_RANK_Q, rank_w_r=LOSS_W_RANK_R,
                            lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS,
                            rank_temp=RANK_TEMP_PCT, rank_tie=RANK_TIE_PCT):
    if mu is None or sigma is None:
        raise ValueError("v159 can mu/sigma train-window (past-only) cho moi fold")
    return multitask_loss_moe(
        score_q, score_r, aux, dlogits, quant, exc, labels, ydir,
        yret, yup, ydn, mu, sigma, weights,
        value_w=value_w, rank_w_q=rank_w_q, rank_w_r=rank_w_r,
        lambda_cov=lambda_cov, floor_pos=floor_pos,
        rank_temp=rank_temp, rank_tie=rank_tie)


def predict_moe_raw(model, sequence, flat, mu, sigma, batch_size=32):
    """Map v8 RAW TRADEABLE moi expert (selection path, KHONG CLIP; giu VERBATIM v41/v145).

    Tra ve (block_q, block_r): moi block (n,16,6) voi ch0 = trade/fill, ch4 = logit(fill).
    unconditional = ch0*fill = tradeable (percent, khong bound) moi expert.
    """
    model.eval()
    device = next(model.parameters()).device
    out_q, out_r = [], []
    with torch.no_grad():
        for s in range(0, len(flat), batch_size):
            xs = torch.as_tensor(sequence[s:s + batch_size], dtype=torch.float32, device=device)
            xf = torch.as_tensor(flat[s:s + batch_size], dtype=torch.float32, device=device)
            score_q, score_r, *_ = model(xs, xf)
            for score, out in ((score_q, out_q), (score_r, out_r)):
                z0 = score[..., 0]
                trade0 = z0 * float(sigma) + float(mu)
                fill = score[..., 1].sigmoid().clamp(1e-6, 1 - 1e-6)
                block = torch.zeros((*score.shape[:2], 6), device=device)
                block[..., 0], block[..., 4] = trade0 / fill, torch.logit(fill)
                out.append(block.cpu())
    import numpy as np
    return torch.cat(out_q).numpy(), torch.cat(out_r).numpy()


def route_blocks(block_q, block_r, mask_quiet):
    """Chon block theo router frozen: quiet neu mask True else rest. Tra ve routed (n,16,6)."""
    import numpy as np
    bq = np.asarray(block_q)
    br = np.asarray(block_r)
    m = np.asarray(mask_quiet).reshape(-1).astype(bool)
    if bq.shape != br.shape or bq.ndim != 3 or bq.shape[1:] != (16, 6):
        raise ValueError("route_blocks expects two (n,16,6) blocks")
    if m.shape[0] != bq.shape[0]:
        raise ValueError("router mask length mismatch")
    return np.where(m[:, None, None], bq, br)


# predict_ssm la ten chuan driver cu goi; v159 dung predict_moe_raw + route_blocks.
def predict_ssm(model, sequence, flat, batch_size=32, mu=None, sigma=None):
    if mu is None or sigma is None:
        raise ValueError("v159 predict_ssm can mu/sigma train-window (past-only)")
    return predict_moe_raw(model, sequence, flat, mu, sigma, batch_size=batch_size)
