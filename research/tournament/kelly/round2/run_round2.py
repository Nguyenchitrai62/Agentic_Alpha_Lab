"""kelly round 2 (PLAN2.md): W1 meanvar_mkt, W2 meanonly, W3 meanonly_mkt; each scored once with harness.score.

  .venv/Scripts/python.exe research/tournament/kelly/round2/run_round2.py
Writes score_<W>.json, sizes_round2.parquet, summary_round2.json in this folder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "context"))
import kelly_sizing as K  # noqa: E402
from build_market_features import FEATS as MKT  # noqa: E402

H = K.H
CTX = HERE.parents[1] / "context"


def build():
    d = K.build()
    ref = H.load()
    assert len(d) == len(ref) and all((d[c].to_numpy() == ref[c].to_numpy()).all() for c in ("j", "sym", "r")), "row order changed"
    mf = pd.read_parquet(CTX / "market_features.parquet")
    assert len(mf) == len(d) and (mf.sym.to_numpy() == d.sym.to_numpy()).all() and (mf["T"].to_numpy() == d["T"].to_numpy()).all()
    for c in MKT:
        d[c] = mf[c].to_numpy()
    return d


def mean_cf(X, y, tr, te, half):
    """Cross-fitted mean HGB (exactly V2's mean model): OOF on train rows, half-average on test rows, and the two models."""
    oof = np.full(tr.sum(), np.nan); ms = []
    Xtr, ytr, htr = X[tr], y[tr], half[tr]
    for hv in (0, 1):
        m = HistGradientBoostingRegressor(**K.HGB).fit(Xtr[htr == hv], ytr[htr == hv])
        oof[htr != hv] = m.predict(Xtr[htr != hv]); ms.append(m)
    return oof, (ms[0].predict(X[te]) + ms[1].predict(X[te])) / 2, ms


def fit_variant(name, d):
    """Returns sizes (test rows) and per-fold models [(a0, ms, rm or None, c)] for the engine tables."""
    cols = K.FEATS + (MKT if name in ("W1_meanvar_mkt", "W3_meanonly_mkt") else [])
    X = d[cols].to_numpy(float); y = d.y_dep.to_numpy(float); half = (d.j.to_numpy() % 2).astype(int)
    size, models = np.full(len(d), np.nan), []
    for yi, a0, tr, te in H.folds(d):
        oof, mt, ms = mean_cf(X, y, tr, te, half)
        if name == "W1_meanvar_mkt":
            rm = HistGradientBoostingRegressor(**K.HGB).fit(X[tr], np.abs(y[tr] - oof))
            so = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X[tr]), 1e-4)
            c = K.scale_c(np.maximum(oof, 0) / so ** 2)
        else:
            rm = None
            c = K.scale_c(np.maximum(oof, 0))
        models.append((a0, ms, rm, c))
        size[te] = predict(models[-1], X[te])
    return size, models, cols


def predict(model, X):
    a0, ms, rm, c = model
    mu = (ms[0].predict(X) + ms[1].predict(X)) / 2
    if rm is None:
        return np.clip(c * np.maximum(mu, 0), 0, 2)
    sd = np.sqrt(np.pi / 2) * np.maximum(rm.predict(X), 1e-4)
    return np.clip(c * np.maximum(mu, 0) / sd ** 2, 0, 2)


def main():
    d = build()
    v2 = pd.read_parquet(HERE.parent / "sizes.parquet").V2_meanvar.to_numpy()
    rv2 = H.score(d, v2, "V2_meanvar")
    ref = json.loads((HERE.parent / "score_V2_meanvar.json").read_text())
    assert rv2["years"] == ref["years"], "V2 reference mismatch"
    y = d.y_dep.to_numpy()
    out, sizes = {}, {}
    for name in ("W1_meanvar_mkt", "W2_meanonly", "W3_meanonly_mkt"):
        s, models, cols = fit_variant(name, d)
        sizes[name] = s
        res = H.score(d, s, name)
        (HERE / f"score_{name}.json").write_text(json.dumps(res, indent=1))
        extra = []
        for (yi, a0, tr, te), r, r2 in zip(H.folds(d), res["years"], rv2["years"]):
            extra.append(dict(year=r["year"], gain_vs_dep=r["gain"], gain_vs_v2=round(r["S_new"] - r2["S_new"], 4),
                              worst_day=r["worst_day_new"], worst_day_v2=r2["worst_day_new"], ic=r["ic_size_y"],
                              raw_mean_size=round(float(s[te].mean()), 3), raw_mean_v2=round(float(v2[te].mean()), 3),
                              raw_mean_dep=round(float(d.size_dep.to_numpy()[te].mean()), 3),
                              share_0=round(float((s[te] <= 0).mean()), 3), share_2=round(float((s[te] >= 2).mean()), 3)))
        wins = sum(e["gain_vs_v2"] > 0 for e in extra)
        wd = min(e["worst_day"] for e in extra); wd2 = min(e["worst_day_v2"] for e in extra)
        out[name] = dict(total_gain_vs_dep=res["total_gain"], total_gain_vs_v2=round(sum(e["gain_vs_v2"] for e in extra), 4),
                         graduates=res["graduates"], years_beating_v2=wins, worst_day_min=wd, worst_day_min_v2=wd2,
                         table_trigger=bool(wins >= 3 and wd >= wd2), years=extra)
        print(name, json.dumps(out[name]), flush=True)
    pd.DataFrame(sizes).to_parquet(HERE / "sizes_round2.parquet")
    (HERE / "summary_round2.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
