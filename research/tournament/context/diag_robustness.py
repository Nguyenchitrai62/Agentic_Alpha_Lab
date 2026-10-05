"""context: DISCLOSED post-score robustness diagnostics (not variants, no selection): HGB early-stopping seed sensitivity of V1 / V2
(sklearn's early_stopping='auto' uses a random 10 % holdout of the TRAINING rows, so random_state matters), and a T / hour alignment check.

  .venv/Scripts/python.exe research/tournament/context/diag_robustness.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import run_variants as RV
from run_variants import H, ALL, BASE, MKT, MONO, hgb


def main():
    d = H.load()
    keep = (pd.read_parquet(H.FILLS).t_fill < H.DEV_END).to_numpy()
    bo = pd.read_parquet(RV.HERE.parent / "data/bar_open.parquet")[keep].reset_index(drop=True)
    assert (bo.hour.to_numpy() == d["T"].dt.hour.to_numpy()).all(), "bar_open hour != T hour"
    mf = pd.read_parquet(RV.HERE / "market_features.parquet")
    F = pd.concat([bo[[c for c in BASE if c != "k"]], d[["k"]], mf[MKT]], axis=1)[ALL]
    X = F.to_numpy(float)
    y = np.clip(d["y1.0"].to_numpy(float), -0.10, 0.08)
    half = (d.j % 2).to_numpy()
    out = {}
    for name, mono in (("hgb_mkt", None), ("hgb_mono", MONO)):
        rows = []
        for off in (101, 202, 303, 404, 505):
            size = np.full(len(d), np.nan)
            for yi, a0, tr, te in H.folds(d):
                mu = float(y[tr].mean())
                ms = [hgb(off + 10 * yi + h, mono, ALL).fit(X[tr & (half == h)], y[tr & (half == h)]) for h in (0, 1)]
                pa, pb = (m.predict(X[te]) for m in ms)
                size[te] = np.where((pa > 2 * mu) & (pb > 2 * mu), 1.5, np.where((pa < 0) & (pb < 0), 0.5, 1.0))
            r = H.score(d, size, f"{name}_seed{off}")
            rows.append(dict(seed=off, gains=[y_["gain"] for y_ in r["years"]], total=r["total_gain"], graduates=r["graduates"]))
            print(rows[-1], flush=True)
        out[name] = rows
    (RV.HERE / "diag_robustness.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
