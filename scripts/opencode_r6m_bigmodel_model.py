"""Opencode R6-M (v28 bigmodel): TCN-deep + Transformer-encoder + multitask heads.

Kien truc DONG BANG (configs/opencode_v28_bigmodel.json):
  sequence (n,5,128,6) -> 5 TCN encoder doc lap (6->64, dilations 1..16)
  -> project 64->192 + frame/age embedding -> Transformer 4 lop x 8 heads
  -> macro/micro fusion (nhu TemporalValue, frame path dung price40 = flat[:,:40])
  -> heads: score (16 actions x 2) + regime aux (map A1) + direction 3-class
     + quantile P10/P50/P90 + excursion MFE/MAE (map A2/v26, H=48, band 8bps).
Loss DONG BANG: objective(score,aux,labels) + 1.0*CE_dir + 1.0*pinball + 0.5*excMSE.
Muc tieu 2-8M params (uoc ~2.8M; so do trong smoke).
"""
import torch  # noqa: F401  (torch truoc pandas)
from torch import nn
from torch.nn import functional as F

from agentic_alpha_lab.models.macro_micro_value import objective

QUANTS = (0.1, 0.5, 0.9)
LOSS_W_DIR, LOSS_W_Q, LOSS_W_E = 1.0, 1.0, 0.5


class CausalBlock(nn.Module):
    def __init__(self, width, dilation, dropout):
        super().__init__()
        self.left = 2 * dilation
        self.convs = nn.ModuleList([nn.Conv1d(width, width, 3, dilation=dilation) for _ in range(2)])
        self.norms = nn.ModuleList([nn.LayerNorm(width) for _ in range(2)])
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        residual = x
        for conv, norm in zip(self.convs, self.norms):
            x = conv(F.pad(x, (self.left, 0)))
            x = self.dropout(F.gelu(norm(x.transpose(1, 2)).transpose(1, 2)))
        return x + residual


class BigTemporalMultitask(nn.Module):
    def __init__(self, candidates, width=192, tcn_width=64, dropout=0.1,
                 layers=4, heads=8, dilations=(1, 2, 4, 8, 16), n_flat=133):
        super().__init__()
        self.n_flat = n_flat
        self.register_buffer("feature_mean", torch.zeros(n_flat))
        self.register_buffer("feature_scale", torch.ones(n_flat))
        self.register_buffer("candidates", torch.as_tensor(candidates, dtype=torch.float32).contiguous())
        self.register_buffer("candidate_scale", torch.tensor([1., 1.5, 3., 3., 6., 7.]))
        self.encoders = nn.ModuleList([
            nn.Sequential(nn.Conv1d(6, tcn_width, 1),
                          *[CausalBlock(tcn_width, d, dropout) for d in dilations])
            for _ in range(5)])
        self.project = nn.Linear(tcn_width, width)
        self.frame_embedding = nn.Parameter(torch.randn(1, 5, 1, width) * .02)
        self.age_embedding = nn.Parameter(torch.randn(1, 1, 16, width) * .02)
        self.layers = nn.ModuleList([
            nn.TransformerEncoderLayer(width, heads, 4 * width, dropout,
                                       activation="gelu", batch_first=True, norm_first=True)
            for _ in range(layers)])
        self.norm = nn.LayerNorm(width)
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
        frames = torch.stack([enc(sequence[:, i].transpose(1, 2))[:, :, 7::8].transpose(1, 2)
                              for i, enc in enumerate(self.encoders)], dim=1)
        token = (self.project(frames) + self.frame_embedding + self.age_embedding).reshape(n, 80, -1)
        for layer in self.layers:
            token = layer(token)
        normalized = ((flat - self.feature_mean) / self.feature_scale).clamp(-10, 10)
        frame = self.norm(token).reshape(n, 5, 16, -1)[:, :, -1] + \
            self.frame_features(normalized[:, :40].reshape(n, 5, 8))
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


def multitask_loss(score, aux, dlogits, quant, exc, labels, ydir, yret, yup, ydn):
    base = objective(score, aux, labels)
    counts = torch.bincount(ydir, minlength=3).float() + 1.0
    cw = (counts.sum() / (3 * counts)).to(dlogits.dtype)
    ce = F.cross_entropy(dlogits, ydir, weight=cw)
    qb = pinball(quant, yret)
    ex = F.mse_loss(torch.log1p(exc),
                    torch.log1p(torch.stack([yup, ydn], -1)))
    return base + LOSS_W_DIR * ce + LOSS_W_Q * qb + LOSS_W_E * ex


def predict_big(model, sequence, flat, batch_size=32):
    """Map v8 (giong temporal_value.predict): ch0 = net/fill, ch4 = logit(fill)."""
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
