"""v165 Kaggle kernel: deep tabular multi-task ensemble (MLP-PLR and FT-Transformer) on the exported full-information panel.

Registry parallel-20260906-r2 / v165. Rows = (t, asset) samples, 70 features, targets y6, y18, y (=y42), y84 (clipped
vol-normalised forward returns) and fv (log forward realised vol). Walk-forward anchors 2021-09-24 .. 2025-09-24 (UTC):
per target the training rows need t < anchor - EMB*4h and t + (h+1)*4h < that cutoff (EMB: y6/y18 78, y 102, y84 144,
fv 102, h from meta). Inner validation = the last 365 days of training time (rows with t >= cutoff_y6 - 365d), trained
rows end 102 bars before it; early stopping on the masked validation MSE of the return targets (patience 5, max 60 epochs).
Preprocessing (training rows only): per feature median/IQR robust scaling, clip +-5, NaN -> 0 plus a missing-indicator per
feature that has NaNs. Architectures:
  mlp_plr: periodic numerical embeddings (k=16 frequencies, sigma 1, per feature linear -> 16) -> concat -> 3 x [Linear 256,
           ReLU, Dropout 0.15] -> 5 heads
  ft:      per-feature token (linear 64) + CLS -> 3 transformer layers (d 64, 4 heads, ff 128, dropout 0.1) -> CLS -> 5 heads
AdamW (lr 1e-3, wd 1e-4 mlp / 1e-5 ft), batch 1024, loss = masked MSE over the five targets (fv weight 0.5). Seeds 0..5 per
architecture. Outputs /kaggle/working/v165_out/pred_<anchor>.parquet with t, sym and, for each architecture, the seed-mean
predictions p6, p18, p42, p84, pfv; plus logs and summary.json.

  python train_v165.py --data <dir> --out <dir> [--smoke]
"""

from __future__ import annotations

import torch  # noqa: F401  (import before pandas on Windows GPU hosts)
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
TARGETS = ("y6", "y18", "y", "y84", "fv")
HORIZON = {"y6": 6, "y18": 18, "y": 42, "y84": 84, "fv": 43}
EMB = {"y6": 78, "y18": 78, "y": 102, "y84": 144, "fv": 102}
H4 = 4 * 3600 * 10**9
LOSS_W = torch.tensor([1.0, 1.0, 1.0, 1.0, 0.5])


class PLR(torch.nn.Module):
    def __init__(self, n, k=16, d=16, sigma=1.0):
        super().__init__()
        self.c = torch.nn.Parameter(torch.randn(n, k) * sigma)
        self.lin = torch.nn.Parameter(torch.randn(n, 2 * k, d) / np.sqrt(2 * k))
        self.b = torch.nn.Parameter(torch.zeros(n, d))

    def forward(self, x):
        v = 2 * np.pi * self.c[None] * x[..., None]
        e = torch.cat([torch.sin(v), torch.cos(v)], -1)
        return torch.relu(torch.einsum("bnk,nkd->bnd", e, self.lin) + self.b)


class MLPPLR(torch.nn.Module):
    def __init__(self, n):
        super().__init__()
        self.emb = PLR(n)
        layers, w = [], n * 16
        for _ in range(3):
            layers += [torch.nn.Linear(w, 256), torch.nn.ReLU(), torch.nn.Dropout(0.15)]
            w = 256
        self.body = torch.nn.Sequential(*layers)
        self.head = torch.nn.Linear(256, len(TARGETS))

    def forward(self, x):
        return self.head(self.body(self.emb(x).flatten(1)))


class FT(torch.nn.Module):
    def __init__(self, n, d=64):
        super().__init__()
        self.w = torch.nn.Parameter(torch.randn(n, d) * 0.1)
        self.b = torch.nn.Parameter(torch.zeros(n, d))
        self.cls = torch.nn.Parameter(torch.zeros(1, 1, d))
        layer = torch.nn.TransformerEncoderLayer(d, 4, 128, dropout=0.1, batch_first=True, norm_first=True)
        self.enc = torch.nn.TransformerEncoder(layer, 3)
        self.head = torch.nn.Sequential(torch.nn.LayerNorm(d), torch.nn.Linear(d, len(TARGETS)))

    def forward(self, x):
        tok = x[..., None] * self.w[None] + self.b[None]
        tok = torch.cat([self.cls.expand(len(x), -1, -1), tok], 1)
        return self.head(self.enc(tok)[:, 0])


def prep(X, tr_mask):
    med = np.nanmedian(X[tr_mask], 0)
    q75, q25 = np.nanpercentile(X[tr_mask], 75, 0), np.nanpercentile(X[tr_mask], 25, 0)
    iqr = np.where((q75 - q25) > 0, q75 - q25, 1.0)
    med = np.where(np.isfinite(med), med, 0.0)
    Z = np.clip((X - med) / iqr, -5, 5)
    miss = np.isnan(X)
    has_nan = miss[tr_mask].any(0)
    Z = np.nan_to_num(Z)
    return np.concatenate([Z, miss[:, has_nan].astype(np.float32)], 1).astype(np.float32)


def run_anchor(df, feats, anchor_ns, device, archs, seeds, max_epochs):
    t = df["t"].to_numpy()
    cut = {k: anchor_ns - EMB[k] * H4 for k in TARGETS}
    Y = df[list(TARGETS)].to_numpy(np.float32)
    M = ~np.isnan(Y)
    for j, k in enumerate(TARGETS):
        M[:, j] &= (t < cut[k]) & (t + (HORIZON[k] + 1) * H4 < cut[k])
    val_start = cut["y6"] - 365 * 86400 * 10**9
    tr = M.any(1) & (t < val_start - 102 * H4)
    va = M.any(1) & (t >= val_start) & (t < cut["y6"])
    te = (t >= anchor_ns) & (t < anchor_ns + 365 * 86400 * 10**9)
    X = prep(df[feats].to_numpy(np.float64), tr)
    Xt, Yt, Mt = (torch.tensor(a, device=device) for a in (X, np.nan_to_num(Y), M))
    lw = LOSS_W.to(device)
    tr_idx, va_idx, te_idx = np.where(tr)[0], np.where(va)[0], np.where(te)[0]
    out, log = {}, []
    for arch in archs:
        preds = []
        for seed in seeds:
            torch.manual_seed(seed)
            np.random.seed(seed)
            m = (MLPPLR(X.shape[1]) if arch == "mlp_plr" else FT(X.shape[1])).to(device)
            opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-4 if arch == "mlp_plr" else 1e-5)
            best, state, bad = 1e9, None, 0
            for ep in range(max_epochs):
                m.train()
                perm = np.random.permutation(tr_idx)
                for b in range(0, len(perm), 1024):
                    i = torch.tensor(perm[b:b + 1024], device=device)
                    loss = (((m(Xt[i]) - Yt[i]) ** 2) * Mt[i] * lw).sum() / (Mt[i] * lw).sum().clamp(min=1)
                    opt.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
                    opt.step()
                m.eval()
                with torch.no_grad():
                    i = torch.tensor(va_idx, device=device)
                    mv = Mt[i][:, :4]
                    vl = float((((m(Xt[i])[:, :4] - Yt[i][:, :4]) ** 2) * mv).sum() / mv.sum().clamp(min=1))
                log.append(dict(arch=arch, seed=seed, epoch=ep, val=round(vl, 5)))
                if vl < best - 1e-5:
                    best, state, bad = vl, {k: v.detach().clone() for k, v in m.state_dict().items()}, 0
                else:
                    bad += 1
                    if bad >= 5:
                        break
            m.load_state_dict(state)
            m.eval()
            with torch.no_grad():
                P = []
                for b in range(0, len(te_idx), 4096):
                    P.append(m(Xt[torch.tensor(te_idx[b:b + 4096], device=device)]).cpu().numpy())
                preds.append(np.concatenate(P))
        out[arch] = np.mean(preds, 0)
    return te_idx, out, log, dict(train_rows=int(tr.sum()), val_rows=int(va.sum()), test_rows=int(te.sum()), n_inputs=int(X.shape[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    data = Path(a.data)
    meta = json.loads((data / "meta.json").read_text())
    df = pd.read_parquet(data / "v165_panel.parquet").sort_values(["t", "sym"]).reset_index(drop=True)
    feats = meta["features"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    archs = ("mlp_plr", "ft")
    seeds = (0,) if a.smoke else tuple(range(6))
    anchors = ANCHORS[-1:] if a.smoke else ANCHORS
    summary = {"device": device, "features": len(feats), "archs": archs, "seeds": len(seeds), "anchors": {}}
    for an in anchors:
        t0 = time.time()
        ns = pd.Timestamp(an, tz="UTC").value
        te_idx, P, log, info = run_anchor(df, feats, ns, device, archs, seeds, 2 if a.smoke else 60)
        res = df.iloc[te_idx][["t", "sym"]].reset_index(drop=True)
        for arch, p in P.items():
            for j, k in enumerate(("p6", "p18", "p42", "p84", "pfv")):
                res[f"{arch}_{k}"] = p[:, j]
        res.to_parquet(out / f"pred_{an}.parquet", index=False)
        (out / f"log_{an}.json").write_text(json.dumps(log))
        summary["anchors"][an] = dict(**info, seconds=round(time.time() - t0, 1))
        print(an, summary["anchors"][an], flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))


def _kaggle_default_argv():
    if len(sys.argv) == 1 and Path("/kaggle/input").exists():
        cand = [p.parent for p in Path("/kaggle/input").rglob("v165_panel.parquet")]
        sys.argv += ["--data", str(cand[0]), "--out", "/kaggle/working/v165_out"]


if __name__ == "__main__":
    _kaggle_default_argv()
    main()
