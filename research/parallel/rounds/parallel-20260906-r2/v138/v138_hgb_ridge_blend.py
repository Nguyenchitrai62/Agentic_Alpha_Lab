"""v138: model diversity - every v133 model = average of HGB and a ridge regression (registry v138).

For each model (v92 y; v94 horizons 18/42/84; v103 horizons 6/18) and anchor, with the audited cutoffs/embargoes:
HGB (v92 hyperparameters) as before, plus Ridge(alpha=10) on the same features after training-median imputation and
training mean/std standardisation (clipped to +-5). Blend = HGB_pred + sd_h * (ridge_pred / sd_r) averaged with weight
0.5 each, where sd_h and sd_r are the std of each model's in-sample training predictions (keeps the HGB scale that the
weight rules expect). Everything else = v133 (v114 panel for v92/v94, v103 panel, v129 vol-forecast sizing, v125
tranching, v115 portfolio 15% target, v110 engine). Reports per-anchor IC of HGB/ridge/blend for v92 and the three
scenarios. Reference v133: 2.44/2.222/1.95. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v138/v138_hgb_ridge_blend.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v129", HERE.parent / "v129" / "v129_vol_forecast_sizing.py")
v129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v129)
v125, v115, v103, v110 = v129.v125, v129.v115, v129.v103, v129.v110
PD = 6
ICS = {}


def fit_blend(tr, te, feats, target, tag, anchor):
    h = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
    h.fit(tr[feats], tr[target])
    med, X = tr[feats].median(), tr[feats]
    Xf = X.fillna(med)
    mu, sd = Xf.mean(), Xf.std().replace(0, 1.0)
    z = lambda d: ((d[feats].fillna(med) - mu) / sd).clip(-5, 5).fillna(0.0)
    r = Ridge(alpha=10.0).fit(z(tr), tr[target])
    sd_h, sd_r = float(np.std(h.predict(X))), float(np.std(r.predict(z(tr)))) or 1.0
    ph, pr = h.predict(te[feats]), r.predict(z(te))
    blend = 0.5 * ph + 0.5 * sd_h * pr / sd_r
    if tag == "v92":
        y = te[target]
        ICS[anchor] = {k: round(float(pd.Series(p, index=te.index).corr(y, method="spearman")), 4) for k, p in (("hgb", ph), ("ridge", pr), ("blend", blend))}
    return blend


def window(panel, anchor, target, h, embargo_bars):
    A = pd.Timestamp(anchor, tz="UTC")
    cutoff = A - pd.Timedelta(hours=4 * embargo_bars)
    tr = panel[(panel.t < cutoff) & panel[target].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
    te = panel[(panel.t >= A) & (panel.t < A + pd.Timedelta(days=365))].copy()
    return tr, te


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92 = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    ext.v92.FEATS = f92
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    lo, ls, fl = [], [], []
    for a in ext.v92.ANCHORS:
        tr, te = window(p92, a, "y", ext.v92.H, ext.v92.EMBARGO_BARS)
        lo.append(te.assign(pred=fit_blend(tr, te, f92, "y", "v92", a)))
        preds = []
        for h in ext.v94.HORIZONS:
            tr, te = window(p94, a, f"y{h}", h, ext.v94.EMBARGO_BARS)
            preds.append(fit_blend(tr, te, f94, f"y{h}", "v94", a))
        ls.append(te.assign(pred=np.mean(preds, axis=0)))
        preds = []
        for h in v103.HS:
            tr, te = window(p103, a, f"y{h}", h, v103.EMBARGO)
            preds.append(fit_blend(tr, te, f103, f"y{h}", "v103", a))
        fl.append(te.assign(pred=np.mean(preds, axis=0)))
        print(a, ICS.get(a), flush=True)
    lo, ls, fl = (pd.concat(x, ignore_index=True) for x in (lo, ls, fl))
    pv92, _ = v129.vol_predict(p92, f92, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

    def swap(df, pv):
        d = df.merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    ph = list(range(PD))
    W_lo = v125.phased(v125.raw_lo(swap(lo, pv92)), ph)
    W94 = v125.phased(v125.raw_ls(swap(ls, pv92)), ph)
    W103 = v125.phased(v125.raw_ls(swap(fl, pv103)), ph)
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    books = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.25 * W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    out = {"version": "v138", "ic_v92": ICS}
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print(sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_scenarios"] = res
    out["reference_v133"] = {"normal": 2.44, "fee_stress": 2.222, "execution_stress": 1.95}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v138_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
