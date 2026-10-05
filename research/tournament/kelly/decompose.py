"""Post-hoc decomposition (NOT a pre-registered variant, written after the V1-V3 scores; never used to pick a variant).
Asks where the V2 gain comes from: pure inverse-variance sizing by the volatility proxy (no model), a mean-only continuous size
(no variance term), and the per-symbol split of the V2 gain. Writes decompose.json."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import kelly_sizing as K

H = K.H


def main():
    d = K.build()
    X = d[K.FEATS].to_numpy(float)
    y = d.y_dep.to_numpy(float)
    half = (d.j.to_numpy() % 2).astype(int)
    inv = np.full(len(d), np.nan); meanonly = np.full(len(d), np.nan); v2 = np.full(len(d), np.nan)
    for yi, a0, tr, te in H.folds(d):
        sg = d.sig.to_numpy(); sg = np.where(np.isfinite(sg), sg, np.nanmedian(sg[tr]))
        inv[te] = 1 / sg[te] ** 2
        mo, mt = K.fit_pred(lambda: HistGradientBoostingRegressor(**K.HGB), X, y, tr, te, half)
        meanonly[te] = np.clip(K.scale_c(np.maximum(mo, 0)) * np.maximum(mt, 0), 0, 2)
        rm = HistGradientBoostingRegressor(**K.HGB).fit(X[tr], np.abs(y[tr] - mo))
        so, st = [np.sqrt(np.pi / 2) * np.maximum(rm.predict(X[m]), 1e-4) for m in (tr, te)]
        v2[te] = np.clip(K.scale_c(np.maximum(mo, 0) / so ** 2) * np.maximum(mt, 0) / st ** 2, 0, 2)
    out = {"inverse_var_sig_only": H.score(d, inv, "inverse_var_sig_only"), "mean_only_continuous": H.score(d, meanonly, "mean_only_continuous")}
    # per-symbol split of the V2 gain (equal exposure rescale per year as in harness.score)
    rows = []
    for yi, a0, tr, te in H.folds(d):
        sd, sn = d.size_dep.to_numpy()[te], v2[te]
        sn = sn * sd.mean() / sn.mean()
        g = pd.DataFrame(dict(sym=d.sym.to_numpy()[te], dep=sd * y[te], new=sn * y[te], sd=sd, sn=sn)).groupby("sym").sum()
        g["gain"] = g.new - g.dep
        g["year"] = str(a0.date())
        rows.append(g.reset_index())
    ps = pd.concat(rows)
    out["v2_gain_by_symbol"] = ps.groupby("sym")[["gain", "sd", "sn"]].sum().round(3).to_dict(orient="index")
    out["v2_gain_by_symbol_year"] = ps.pivot(index="sym", columns="year", values="gain").round(3).to_dict(orient="index")
    (K.HERE / "decompose.json").write_text(json.dumps(out, indent=1))
    pd.DataFrame(dict(mean_only_continuous=meanonly)).to_parquet(K.HERE / "sizes_meanonly.parquet")
    for k in ("inverse_var_sig_only", "mean_only_continuous"):
        print(k, out[k]["total_gain"], out[k]["graduates"], [r["gain"] for r in out[k]["years"]])
    print(json.dumps(out["v2_gain_by_symbol"], indent=1)); print(json.dumps(out["v2_gain_by_symbol_year"], indent=1))


if __name__ == "__main__":
    main()
