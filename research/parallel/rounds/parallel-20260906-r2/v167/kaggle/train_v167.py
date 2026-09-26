"""v167 Kaggle kernel: temporal GRU over the last 42 bars of the 70 engineered features (registry parallel-20260906-r2 / v167).

Same dataset as v165 (nguynchtrai/v165-majors-full-panel). For every (asset, bar t) sample the input is the asset's own
sequence of the last 42 rows (t-41..t, rows missing at the start -> zero-padded with a mask channel) of the robust-scaled
features (training-row median/IQR, clip +-5, NaN -> 0 + missing indicators, exactly as v165) plus a one-hot asset id.
Model: 2-layer GRU (hidden 96, dropout 0.2) -> last hidden state -> MLP (96 -> 64 -> 5) heads for y6, y18, y (=y42), y84,
fv. Walk-forward anchors, per-target cutoffs/embargoes, inner validation (last 365 days), early stopping (patience 5, max
40 epochs), AdamW lr 1e-3 wd 1e-4, batch 512, masked MSE (fv weight 0.5), seeds 0..5 - all as v165. Outputs
/kaggle/working/v167_out/pred_<anchor>.parquet (t, sym, gru_p6, gru_p18, gru_p42, gru_p84, gru_pfv; seed means).

  python train_v167.py --data <dir> --out <dir> [--smoke]
"""

from __future__ import annotations

import torch  # noqa: F401
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
L = 42
LOSS_W = torch.tensor([1.0, 1.0, 1.0, 1.0, 0.5])


class GRUNet(torch.nn.Module):
    def __init__(self, f):
        super().__init__()
        self.gru = torch.nn.GRU(f, 96, num_layers=2, batch_first=True, dropout=0.2)
        self.head = torch.nn.Sequential(torch.nn.Linear(96, 64), torch.nn.ReLU(), torch.nn.Dropout(0.2), torch.nn.Linear(64, len(TARGETS)))

    def forward(self, x):
        out, _ = self.gru(x)
        return self.head(out[:, -1])


def prep(X, tr_mask):
    med = np.nanmedian(X[tr_mask], 0)
    q75, q25 = np.nanpercentile(X[tr_mask], 75, 0), np.nanpercentile(X[tr_mask], 25, 0)
    iqr = np.where((q75 - q25) > 0, q75 - q25, 1.0)
    med = np.where(np.isfinite(med), med, 0.0)
    Z = np.nan_to_num(np.clip((X - med) / iqr, -5, 5))
    miss = np.isnan(X)
    has_nan = miss[tr_mask].any(0)
    return np.concatenate([Z, miss[:, has_nan].astype(np.float32)], 1).astype(np.float32)


def seq_index(df):
    """For every row, the row indices of the same asset's previous L rows (-1 = padding)."""
    idx = np.full((len(df), L), -1, dtype=np.int64)
    for _, g in df.groupby("sym", sort=False):
        rows = g.sort_values("t").index.to_numpy()
        pos = np.arange(len(rows))[:, None] + np.arange(L)[None, :] - (L - 1)
        idx[rows] = np.where(pos >= 0, rows[pos.clip(min=0)], -1)
    return idx


def gather(Xt, idx_t, onehot_t):
    pad = (idx_t < 0)
    x = Xt[idx_t.clamp(min=0)]
    x[pad] = 0.0
    mask = (~pad).float().unsqueeze(-1)
    return torch.cat([x, mask, onehot_t.unsqueeze(1).expand(-1, L, -1)], -1)


def run_anchor(df, feats, sidx, onehot, anchor_ns, device, seeds, max_epochs):
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
    Xt = torch.tensor(X, device=device)
    It = torch.tensor(sidx, device=device)
    Ot = torch.tensor(onehot, device=device)
    Yt, Mt = torch.tensor(np.nan_to_num(Y), device=device), torch.tensor(M, device=device)
    lw = LOSS_W.to(device)
    tr_idx, va_idx, te_idx = np.where(tr)[0], np.where(va)[0], np.where(te)[0]
    fdim = X.shape[1] + 1 + onehot.shape[1]
    preds, log = [], []
    for seed in seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        m = GRUNet(fdim).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3, weight_decay=1e-4)
        best, state, bad = 1e9, None, 0
        for ep in range(max_epochs):
            m.train()
            perm = np.random.permutation(tr_idx)
            for b in range(0, len(perm), 512):
                i = torch.tensor(perm[b:b + 512], device=device)
                out = m(gather(Xt, It[i], Ot[i]))
                loss = (((out - Yt[i]) ** 2) * Mt[i] * lw).sum() / (Mt[i] * lw).sum().clamp(min=1)
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
                opt.step()
            m.eval()
            with torch.no_grad():
                vl_num, vl_den = 0.0, 0.0
                for b in range(0, len(va_idx), 4096):
                    i = torch.tensor(va_idx[b:b + 4096], device=device)
                    mv = Mt[i][:, :4]
                    vl_num += float((((m(gather(Xt, It[i], Ot[i]))[:, :4] - Yt[i][:, :4]) ** 2) * mv).sum())
                    vl_den += float(mv.sum())
                vl = vl_num / max(vl_den, 1.0)
            log.append(dict(seed=seed, epoch=ep, val=round(vl, 5)))
            if vl < best - 1e-5:
                best, state, bad = vl, {k: v.detach().clone() for k, v in m.state_dict().items()}, 0
            else:
                bad += 1
                if bad >= 5:
                    break
        m.load_state_dict(state)
        m.eval()
        with torch.no_grad():
            P = [m(gather(Xt, It[torch.tensor(te_idx[b:b + 4096], device=device)], Ot[torch.tensor(te_idx[b:b + 4096], device=device)])).cpu().numpy()
                 for b in range(0, len(te_idx), 4096)]
        preds.append(np.concatenate(P))
    return te_idx, np.mean(preds, 0), log, dict(train_rows=int(tr.sum()), val_rows=int(va.sum()), test_rows=int(te.sum()))


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
    syms = sorted(df.sym.unique())
    onehot = np.eye(len(syms), dtype=np.float32)[df["sym"].map({s: i for i, s in enumerate(syms)}).to_numpy()]
    sidx = seq_index(df)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    seeds = (0,) if a.smoke else tuple(range(6))
    anchors = ANCHORS[-1:] if a.smoke else ANCHORS
    summary = {"device": device, "features": len(feats), "seq_len": L, "seeds": len(seeds), "anchors": {}}
    for an in anchors:
        t0 = time.time()
        te_idx, P, log, info = run_anchor(df, feats, sidx, onehot, pd.Timestamp(an, tz="UTC").value, device, seeds, 2 if a.smoke else 40)
        res = df.iloc[te_idx][["t", "sym"]].reset_index(drop=True)
        for j, k in enumerate(("p6", "p18", "p42", "p84", "pfv")):
            res[f"gru_{k}"] = P[:, j]
        res.to_parquet(out / f"pred_{an}.parquet", index=False)
        (out / f"log_{an}.json").write_text(json.dumps(log))
        summary["anchors"][an] = dict(**info, seconds=round(time.time() - t0, 1))
        print(an, summary["anchors"][an], flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))


def _kaggle_default_argv():
    if len(sys.argv) == 1 and Path("/kaggle/input").exists():
        cand = [p.parent for p in Path("/kaggle/input").rglob("v165_panel.parquet")]
        sys.argv += ["--data", str(cand[0]), "--out", "/kaggle/working/v167_out"]


if __name__ == "__main__":
    _kaggle_default_argv()
    main()
