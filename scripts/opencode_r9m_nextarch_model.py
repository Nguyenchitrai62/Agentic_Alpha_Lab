"""Opencode R9-M (v35 nextarch): Selective-SSM (Mamba-style, pure-PyTorch) + multitask.

Hoan toan KHAC ho v28 (TCN-deep + Transformer-encoder), A1 (TCN nho), A2 (MLP),
v33 (GRU): encoder la state-space TUYEN TINH co chon loc theo input (dt/B/C phu
thuoc input, A am on dinh), recurrence tien-only -> causal nghiem ngat.

Input DONG BANG nhu v28: sequence (n,5,128,6) + flat (n,133).
Heads + mapping v8 DONG BANG nhu v28 (so sanh cong bang).
Loss = base v28 (objective + 1.0*CE_dir + 1.0*pinball + 0.5*excMSE)
       + coverage-floor hinge (DONG BANG configs/opencode_v35_nextarch.json):
         en_best = max_k score[k,0]; mean_pos = mean(relu(en_best));
         coverage_loss = 3.0 * relu(1 - mean_pos/5e-4)^2.
Policy floor (eval, pre-spec): gate en_best > 0, fallback top-8/fold-test.
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch import nn
from torch.nn import functional as F

from agentic_alpha_lab.models.macro_micro_value import objective

QUANTS = (0.1, 0.5, 0.9)
LOSS_W_DIR, LOSS_W_Q, LOSS_W_E = 1.0, 1.0, 0.5
COV_LAMBDA, COV_FLOOR_POS = 3.0, 5e-4
POLICY_MARGIN, POLICY_N_MIN = 0.0, 8


class SelectiveSSM1D(nn.Module):
    """Mot lop state-space chon loc (Mamba-style), pure-PyTorch, causal tuyet doi.

    x -> norm -> depthwise causal conv (left-pad) -> SiLU -> selective scan:
      h_t = exp(dt_t * A) * h_{t-1} + (dt_t * B_t) * x_t ; y_t = C_t . h_t + D * x_t
    voi dt/B/C phu thuoc input (tinh chon loc), A = -exp(A_log) < 0 (on dinh).
    y = y * SiLU(gate(x)) -> out_proj + residual.
    """

    def __init__(self, d_model, d_state=16, conv_k=4, dropout=0.1):
        super().__init__()
        self.d_model, self.d_state = d_model, d_state
        self.left = conv_k - 1
        self.norm = nn.LayerNorm(d_model)
        self.in_proj = nn.Linear(d_model, d_model)
        self.conv = nn.Conv1d(d_model, d_model, conv_k, groups=d_model)
        self.dt_proj = nn.Linear(d_model, d_model)
        self.B_proj = nn.Linear(d_model, d_state)
        self.C_proj = nn.Linear(d_model, d_state)
        self.A_log = nn.Parameter(torch.randn(d_model, d_state) * 0.5 - 1.0)
        self.D = nn.Parameter(torch.ones(d_model))
        self.gate_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        if x.ndim != 3:
            raise ValueError("Expected [batch, time, dim]")
        res = x
        xn = self.norm(x)
        xc = self.in_proj(xn).transpose(1, 2)
        if self.left:
            xc = F.pad(xc, (self.left, 0))
        xc = F.silu(self.conv(xc).transpose(1, 2))
        A = -torch.exp(self.A_log)  # (D, N) am
        dt = F.softplus(self.dt_proj(xc)).clamp(1e-3, 0.5)  # (B, T, D)
        B = self.B_proj(xc)  # (B, T, N)
        C = self.C_proj(xc)  # (B, T, N)
        h = torch.zeros(x.shape[0], self.d_model, self.d_state,
                        device=x.device, dtype=xc.dtype)
        ys = []
        for t in range(xc.shape[1]):  # recurrence tien-only -> causal
            dA = torch.exp(dt[:, t].unsqueeze(-1) * A)  # (B, D, N)
            h = h * dA + (dt[:, t].unsqueeze(-1) * B[:, t].unsqueeze(1)) * xc[:, t].unsqueeze(-1)
            ys.append((h * C[:, t].unsqueeze(1)).sum(-1) + self.D * xc[:, t])
        y = torch.stack(ys, 1) * F.silu(self.gate_proj(xn))
        return self.dropout(self.out_proj(y)) + res


class SelectiveSSMTemporal(nn.Module):
    def __init__(self, candidates, width=192, frame_dim=64, frame_state=16,
                 frame_layers=2, cross_state=16, dropout=0.1, n_flat=133):
        super().__init__()
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
        frames = []
        for i in range(5):  # encoder shared tren 5 frames (weight-shared)
            z = self.frame_in(sequence[:, i])
            for layer in self.frame_ssm:
                z = layer(z)
            frames.append(self.frame_pool(torch.cat((z[:, -1], z.mean(1)), -1)))
        scanned = self.cross_ssm(torch.stack(frames, 1)) + torch.stack(frames, 1)
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


def pinball(pred, target, quants=QUANTS):
    e = target.unsqueeze(1) - pred
    q = torch.tensor(quants, dtype=pred.dtype, device=pred.device).unsqueeze(0)
    return torch.maximum(q * e, (q - 1) * e).mean()


def coverage_floor_loss(score, lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS):
    """Hinge coverage-floor (kha vi, causal, train-batch-only).

    Phat khi mean mass duong cua batch < floor (model 'nhat').
    Tra ve (loss, mean_pos, en_best_mean) de log.
    """
    en_best = score[..., 0].amax(dim=1)
    mean_pos = F.relu(en_best).mean()
    gap = F.relu(1.0 - mean_pos / floor_pos)
    return lambda_cov * gap * gap, mean_pos.detach(), en_best.detach().mean()


def multitask_loss_cov(score, aux, dlogits, quant, exc, labels, ydir, yret, yup, ydn,
                       lambda_cov=COV_LAMBDA, floor_pos=COV_FLOOR_POS):
    base = objective(score, aux, labels)
    counts = torch.bincount(ydir, minlength=3).float() + 1.0
    cw = (counts.sum() / (3 * counts)).to(dlogits.dtype)
    ce = F.cross_entropy(dlogits, ydir, weight=cw)
    qb = pinball(quant, yret)
    ex = F.mse_loss(torch.log1p(exc),
                    torch.log1p(torch.stack([yup, ydn], -1)))
    cov, mean_pos, en_mean = coverage_floor_loss(score, lambda_cov, floor_pos)
    total = base + LOSS_W_DIR * ce + LOSS_W_Q * qb + LOSS_W_E * ex + cov
    return total, {"base": base.detach(), "ce": ce.detach(), "qb": qb.detach(),
                   "ex": ex.detach(), "cov": cov.detach(),
                   "mean_pos": mean_pos, "en_mean": en_mean}


def expected_net_best(score):
    """en_best = max_k unconditional net (score[...,0]), mapping v8."""
    import numpy as np
    s = score if isinstance(score, np.ndarray) else score.detach().cpu().numpy()
    return s[..., 0].max(axis=1)


def apply_coverage_floor_policy(en_best, margin=POLICY_MARGIN, n_min=POLICY_N_MIN):
    """Policy floor pre-spec (eval): gate en_best > margin + fallback top-n_min.

    Tra ve indices (numpy) — dam bao >= min(n_min, len) tin hieu moi fold-test.
    """
    import numpy as np
    en = np.asarray(en_best, dtype=np.float64)
    gate = np.flatnonzero(en > margin)
    if len(gate) >= n_min:
        return np.sort(gate)
    top = np.argsort(-en, kind="stable")[:min(n_min, len(en))]
    return np.sort(np.union1d(gate, top).astype(np.int64))


def predict_ssm(model, sequence, flat, batch_size=32):
    """Map v8 (giong temporal_value.predict): ch0 = net/fill, ch4 = logit(fill)."""
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


def count_params(model):
    return sum(p.numel() for p in model.parameters())
