"""v326: POOLED-EXPERIENCE deep sequence member PD (Kaggle GPU) - registry v326.

Why: four deep-learning members failed when trained on the 5 majors (v90 TCN+Transformer, v143, v165 MLP-PLR / FT-Transformer, v167 GRU: IC ~0) -
~100k rows. Pooled survivorship-free experience (5 majors + 72 U2020 alts, training only; v316 / v317 audits PASS) gives ~1M rows, and it lifted
the tree member (PT: IC 2023 0.17 vs 0.08). v326 asks whether a sequence model can use that experience.
DATA: artifacts/kaggle/v326/ds/pooled_panel.parquet (v326_export_panel.py: the v317 panel - 43 features: v92 + 17 TV + BTC cross + asset id;
targets y18 / y42 / y84 = v94 vol-normalised forward open-to-open returns clipped +-4; 4h bars; t = bar open).
WALK-FORWARD (anchors 2021-09-24 .. 2025-09-24): cutoff = anchor - (84 + 60) bars; a training row needs t < cutoff and its label of horizon h
ending before the cutoff (t + 4h (h + 1) < cutoff; per-horizon loss mask). Normalisation: per-feature median / IQR of the training rows of THAT
anchor, clip +-5, NaN -> 0. Validation for early stopping = the last 10% (by time) of the training rows; nothing at or after the cutoff.
MODEL: input = the last 42 bars (7 days) of the 43 features of the symbol (windows that cross a gap of > 4h are dropped from training), GRU(43 -> 64,
1 layer) -> linear(64 -> 3) for (y18, y42, y84) / 4; masked MSE; AdamW lr 1e-3, weight decay 1e-4, batch 2048, <= 20 epochs, patience 3 on the
validation loss; FIVE seeds (0..4), member prediction = mean over seeds of the mean of the three horizon outputs (as v94 averages its horizons).
OUTPUT: predictions for the MAJORS rows of each anchor year (t in [anchor, anchor + 365 d)): t, sym, pred, pred_s0..pred_s4; per-anchor / per-seed
validation loss and test-year Spearman IC (vs y42) in log.json.
Scoring happens locally (v326_score.py, fixed together with this script): books = v94.weights_ls(shorts=True) of pred; MANUAL rows on the M2 setting
(pullback 0.75 sigma_4h / 3 bars, cap 2, target 0.25): D0 M2 = (2A + 2PT + D)/5 | D1 (2A + 2PD + D)/5 | D2 (2A + PT + PD + D)/5; choice on dev
folds k = 2, 3 (v310 robust fitness), TRANSFER if the choice beats D0 in both folds; final on dev4, the most recent year once.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
HS = (18, 42, 84)
EMB = 84 + 60
L = 42
SEEDS = (0, 1, 2, 3, 4)


def find(name):
    for base in (Path("/kaggle/input"), Path(".")):
        hits = sorted(base.rglob(name))
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


class GRU(nn.Module):
    def __init__(self, nf):
        super().__init__()
        self.gru = nn.GRU(nf, 64, batch_first=True)
        self.head = nn.Linear(64, 3)

    def forward(self, x):
        h, _ = self.gru(x)
        return self.head(h[:, -1])


def main():
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    out_dir = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path("artifacts/kaggle/v326/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(find("pooled_panel.parquet"))
    feats = find("features.txt").read_text().split("\n")
    df["t"] = pd.to_datetime(df["t"], utc=True)
    smoke = bool(os.environ.get("V326_SMOKE"))
    if smoke:  # local logic check only: 4 symbols, one anchor, one epoch, two seeds
        df = df[df.sym.isin(["BTCUSDT", "ETHUSDT", "AAVEUSDT", "ADAUSDT"])]
    df = df.sort_values(["sym", "t"]).reset_index(drop=True)
    X_all = df[feats].to_numpy(np.float32)
    Y_all = (df[[f"y{h}" for h in HS]].to_numpy(np.float32) / 4.0)
    t_ns = df["t"].astype("int64").to_numpy()
    sym = df["sym"].to_numpy()
    # window end positions: index i with i - L + 1 .. i in the same symbol and no gap > 4h inside
    same = np.r_[False, sym[1:] == sym[:-1]]
    gap_ok = np.r_[False, (np.diff(t_ns) == 4 * 3600 * 10 ** 9)] & same
    run = np.zeros(len(df), int)
    for i in range(1, len(df)):
        run[i] = run[i - 1] + 1 if gap_ok[i] else 0
    valid_end = run >= L - 1
    log = {"device": dev, "rows": int(len(df)), "anchors": {}}
    preds_out = []
    for a in (ANCHORS[2:3] if smoke else ANCHORS):
        a0 = pd.Timestamp(a, tz="UTC").value
        cutoff = a0 - EMB * 4 * 3600 * 10 ** 9
        lab_ok = np.stack([t_ns + 4 * 3600 * 10 ** 9 * (h + 1) < cutoff for h in HS], 1) & np.isfinite(Y_all)
        tr_rows = (t_ns < cutoff) & valid_end & lab_ok.any(1)
        med = np.nanmedian(X_all[t_ns < cutoff], axis=0)
        iqr = np.nanpercentile(X_all[t_ns < cutoff], 75, axis=0) - np.nanpercentile(X_all[t_ns < cutoff], 25, axis=0)
        iqr = np.where(iqr > 0, iqr, 1.0)
        Xn = np.clip((X_all - med) / iqr, -5, 5)
        Xn = np.nan_to_num(Xn, nan=0.0).astype(np.float32)
        Xt = torch.from_numpy(Xn).to(dev)
        Ym = torch.from_numpy(np.where(lab_ok, np.nan_to_num(Y_all, nan=0.0), 0.0).astype(np.float32)).to(dev)
        Mk = torch.from_numpy(lab_ok.astype(np.float32)).to(dev)
        idx_tr = np.where(tr_rows)[0]
        order = idx_tr[np.argsort(t_ns[idx_tr], kind="stable")]
        n_val = max(1, len(order) // 10)
        idx_fit, idx_val = order[:-n_val], order[-n_val:]
        te_rows = np.where((df["is_major"].to_numpy() == 1) & (t_ns >= a0) & (t_ns < a0 + 365 * 86400 * 10 ** 9) & valid_end)[0]
        offs = torch.arange(-L + 1, 1, device=dev)

        def batch(ix):
            ii = torch.as_tensor(ix, device=dev)[:, None] + offs[None, :]
            return Xt[ii], Ym[ix], Mk[ix]
        seed_preds, info = [], {}
        for sd in (SEEDS[:2] if smoke else SEEDS):
            torch.manual_seed(sd); np.random.seed(sd)
            net = GRU(len(feats)).to(dev)
            opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
            best, best_state, bad = 1e9, None, 0
            for ep in range(1 if smoke else 20):
                net.train()
                perm = np.random.permutation(idx_fit)
                for s0 in range(0, len(perm), 2048):
                    xb, yb, mb = batch(perm[s0:s0 + 2048])
                    loss = (((net(xb) - yb) ** 2) * mb).sum() / mb.sum().clamp(min=1)
                    opt.zero_grad(); loss.backward(); opt.step()
                net.eval()
                with torch.no_grad():
                    vl, vn = 0.0, 0.0
                    for s0 in range(0, len(idx_val), 8192):
                        xb, yb, mb = batch(idx_val[s0:s0 + 8192])
                        vl += float((((net(xb) - yb) ** 2) * mb).sum()); vn += float(mb.sum())
                    vl /= max(vn, 1)
                if vl < best - 1e-6:
                    best, best_state, bad = vl, {k: v.detach().clone() for k, v in net.state_dict().items()}, 0
                else:
                    bad += 1
                    if bad >= 3:
                        break
            net.load_state_dict(best_state)
            net.eval()
            with torch.no_grad():
                p = np.concatenate([net(batch(te_rows[s0:s0 + 8192])[0]).mean(1).cpu().numpy() for s0 in range(0, len(te_rows), 8192)])
            seed_preds.append(p)
            ic = float(pd.Series(p).corr(pd.Series(Y_all[te_rows, 1]), method="spearman")) if a != ANCHORS[-1] else None
            info[sd] = dict(val_loss=round(best, 6), epochs=ep + 1, test_ic=None if ic is None else round(ic, 4))
            print(a, "seed", sd, info[sd], flush=True)
        P = np.stack(seed_preds, 1)
        o = pd.DataFrame({"t": df["t"].to_numpy()[te_rows], "sym": sym[te_rows], "pred": P.mean(1)})
        for j in range(P.shape[1]):
            o[f"pred_s{SEEDS[j]}"] = P[:, j]
        preds_out.append(o)
        ens_ic = float(pd.Series(P.mean(1)).corr(pd.Series(Y_all[te_rows, 1]), method="spearman")) if a != ANCHORS[-1] else None
        log["anchors"][a] = dict(train_rows=int(len(idx_fit)), val_rows=int(len(idx_val)), test_rows=int(len(te_rows)), seeds=info,
                                 ensemble_test_ic=None if ens_ic is None else round(ens_ic, 4))
        print(a, "ensemble IC", ens_ic, flush=True)
        del Xt, Ym, Mk
        torch.cuda.empty_cache() if dev == "cuda" else None
    pd.concat(preds_out, ignore_index=True).to_parquet(out_dir / "v326_pd_preds.parquet")
    (out_dir / "log.json").write_text(json.dumps(log, indent=1))
    print("done", flush=True)


if __name__ == "__main__":
    main()
