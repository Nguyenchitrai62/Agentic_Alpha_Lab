"""context: pre-registered variants V1 hgb_mkt, V2 hgb_mono, V3 ens (+ reference R0, not a candidate). See PLAN.md.

Each fold: train on harness.folds training rows only (t_exit < anchor - 7 d, any coin), two halves by j % 2, deployed rule
(1.5 if both halves > 2 mu, 0.5 if both < 0, else 1.0). Each variant is scored ONCE with harness.score.

  .venv/Scripts/python.exe research/tournament/context/run_variants.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import harness as H  # noqa: E402
from build_market_features import FEATS as MKT  # noqa: E402

BASE = ["bo_sp30", "k", "bo_volreg", "bo_trend", "bo_btc_sp30", "bo_dd24", "hour"]
ALL = BASE + MKT
MONO = {"m_tr7": 1, "bo_trend": 1, "m_vts": -1}


def hgb(seed, mono=None, cols=None):
    cst = None if mono is None else [mono.get(c, 0) for c in cols]
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                         monotonic_cst=cst, random_state=seed)


class Ens:
    """Average of HGB, ExtraTrees (median-imputed) and Ridge (standardised, median-imputed); all statistics from the training rows."""

    def __init__(self, seed):
        self.seed = seed

    def fit(self, X, y):
        self.med = np.nanmedian(X, 0)
        Xi = np.where(np.isfinite(X), X, self.med)
        self.mu, self.sd = Xi.mean(0), Xi.std(0) + 1e-12
        self.h = hgb(self.seed).fit(X, y)
        self.e = ExtraTreesRegressor(n_estimators=200, min_samples_leaf=200, max_features=0.5, n_jobs=2, random_state=self.seed).fit(Xi, y)
        self.r = Ridge(alpha=10.0).fit((Xi - self.mu) / self.sd, y)
        return self

    def predict(self, X):
        Xi = np.where(np.isfinite(X), X, self.med)
        return (self.h.predict(X) + self.e.predict(Xi) + self.r.predict((Xi - self.mu) / self.sd)) / 3.0


def make(name, seed):
    if name == "hgb_mkt" or name == "R0_base7":
        return hgb(seed)
    if name == "hgb_mono":
        return hgb(seed, MONO, ALL)
    if name == "ens":
        return Ens(seed)
    raise ValueError(name)


def perm_importance(models, X, y, half, cols, rng, n=15000, reps=3):
    """MSE increase when a column is permuted, on sampled TRAINING rows of each half (in-sample), averaged over halves."""
    imp = np.zeros(len(cols))
    for h, m in enumerate(models):
        idx = np.flatnonzero(half == h)
        idx = rng.choice(idx, min(n, len(idx)), replace=False)
        Xs, ys = X[idx], y[idx]
        base = np.mean((m.predict(Xs) - ys) ** 2)
        for c in range(len(cols)):
            acc = 0.0
            for _ in range(reps):
                Xp = Xs.copy()
                Xp[:, c] = rng.permutation(Xp[:, c])
                acc += np.mean((m.predict(Xp) - ys) ** 2) - base
            imp[c] += acc / reps / len(models)
    return dict(sorted(zip(cols, (float(v) for v in imp)), key=lambda kv: -kv[1]))


def main():
    t0 = time.time()
    d = H.load()
    fills = pd.read_parquet(H.FILLS)
    keep = (fills.t_fill < H.DEV_END).to_numpy()
    bo = pd.read_parquet(HERE.parent / "data/bar_open.parquet")[keep].reset_index(drop=True)
    assert len(bo) == len(d) and (bo.j.to_numpy() == d.j.to_numpy()).all() and (bo.sym.to_numpy() == d.sym.to_numpy()).all() \
        and (bo.r.to_numpy() == d.r.to_numpy()).all(), "bar_open misaligned"
    mf = pd.read_parquet(HERE / "market_features.parquet")
    assert len(mf) == len(d) and (mf.sym.to_numpy() == d.sym.to_numpy()).all() and (mf["T"].to_numpy() == d["T"].to_numpy()).all()
    F = pd.concat([bo[[c for c in BASE if c != "k"]], d[["k"]], mf[MKT]], axis=1)[ALL]
    y = np.clip(d["y1.0"].to_numpy(float), -0.10, 0.08)
    half = (d.j % 2).to_numpy()
    yd = d.y_dep.to_numpy(float)
    fl = H.folds(d)
    summary = {}
    for name, cols in (("hgb_mkt", ALL), ("hgb_mono", ALL), ("ens", ALL), ("R0_base7", BASE)):
        X = F[cols].to_numpy(float)
        size = np.full(len(d), np.nan)
        pred = np.full(len(d), np.nan)
        diag = {}
        for yi, a0, tr, te in fl:
            mu = float(y[tr].mean())
            ms = [make(name, 10 * yi + h).fit(X[tr & (half == h)], y[tr & (half == h)]) for h in (0, 1)]
            pa, pb = (m.predict(X[te]) for m in ms)
            s = np.where((pa > 2 * mu) & (pb > 2 * mu), 1.5, np.where((pa < 0) & (pb < 0), 0.5, 1.0))
            size[te], pred[te] = s, (pa + pb) / 2
            ic = float(pd.Series((pa + pb) / 2).corr(pd.Series(yd[te]), method="spearman"))
            diag[str(a0.date())] = dict(train_rows=int(tr.sum()), mu=round(mu, 5), share_up=round(float((s == 1.5).mean()), 3),
                                        share_down=round(float((s == 0.5).mean()), 3), ic_pred_ydep=round(ic, 4),
                                        ic_sizedep_ydep=round(float(pd.Series(d.size_dep.to_numpy()[te]).corr(pd.Series(yd[te]), method="spearman")), 4))
            if yi == len(fl) - 1:
                diag["perm_importance_2024fold_train"] = perm_importance(ms, X[tr], y[tr], half[tr], cols, np.random.default_rng(1))
            print(name, a0.date(), diag[str(a0.date())], f"{time.time() - t0:.0f}s", flush=True)
        res = H.score(d, size, name)
        res["diagnostics"] = diag
        res["candidate"] = name != "R0_base7"
        (HERE / f"score_{name}.json").write_text(json.dumps(res, indent=1))
        summary[name] = dict(total_gain=res["total_gain"], graduates=res["graduates"], gains=[r["gain"] for r in res["years"]])
        print(json.dumps({k: v for k, v in res.items() if k != "diagnostics"}, indent=1), flush=True)
    print(json.dumps(summary, indent=1))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
