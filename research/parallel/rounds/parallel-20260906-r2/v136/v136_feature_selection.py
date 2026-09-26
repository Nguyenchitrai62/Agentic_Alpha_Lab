"""v136: nested permutation-importance feature selection for all v133 models (registry parallel-20260906-r2 / v136).

For each model (v92 y, each v94 horizon, each v103 horizon) and anchor: inner-train = training rows whose label is
realized before (cutoff - 730 days - embargo); validation = training rows in the last 730 days before the cutoff. Fit
the model (v92 hyperparameters) on inner-train, compute sklearn permutation_importance on validation (scoring = Spearman
rank correlation of prediction vs target, n_repeats=3, random_state=0, max 20000 validation rows sampled with seed 0),
keep features with mean importance > 0 (at least 5 kept: top-5 by importance otherwise), refit on all training rows with
the kept features, predict the test year. Everything else = v133 (v114 panel for v92/v94, v103 panel, vol-forecast
sizing, tranching, v115 portfolio 15% target). Reports three scenarios with full-path DD, kept features per anchor, and
reference v133 (2.44/2.222/1.95). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v136/v136_feature_selection.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import make_scorer

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v129", HERE.parent / "v129" / "v129_vol_forecast_sizing.py")
v129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v129)
v125, v115, v103, v110 = v129.v125, v129.v115, v129.v103, v129.v110
PD = 6
KEPT = {}


def hgb():
    return HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)


def spearman(y, p):
    return pd.Series(p).corr(pd.Series(np.asarray(y)), method="spearman")


def select_fit_predict(panel, anchor, feats, target, h, embargo_bars, tag):
    A = pd.Timestamp(anchor, tz="UTC")
    cutoff = A - pd.Timedelta(hours=4 * embargo_bars)
    tr = panel[(panel.t < cutoff) & panel[target].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
    val_start = cutoff - pd.Timedelta(days=730)
    val = tr[tr.t >= val_start]
    itr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < val_start - pd.Timedelta(hours=4 * embargo_bars)]
    if len(val) > 20000:
        val = val.sample(20000, random_state=0)
    m = hgb().fit(itr[feats], itr[target])
    imp = permutation_importance(m, val[feats], val[target], scoring=make_scorer(spearman), n_repeats=3, random_state=0)
    order = np.argsort(-imp.importances_mean)
    kept = [feats[i] for i in order if imp.importances_mean[i] > 0]
    if len(kept) < 5:
        kept = [feats[i] for i in order[:5]]
    KEPT.setdefault(tag, {})[anchor] = kept
    te = panel[(panel.t >= A) & (panel.t < A + pd.Timedelta(days=365))].copy()
    return hgb().fit(tr[kept], tr[target]).predict(te[kept]), te


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92 = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    ext.v92.FEATS = f92
    lo, ls, fl = [], [], []
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    for a in ext.v92.ANCHORS:
        pr, te = select_fit_predict(p92, a, f92, "y", ext.v92.H, ext.v92.EMBARGO_BARS, "v92")
        lo.append(te.assign(pred=pr))
        preds = [select_fit_predict(p94, a, f94, f"y{h}", h, ext.v94.EMBARGO_BARS, f"v94_h{h}")[0] for h in ext.v94.HORIZONS]
        te94 = p94[(p94.t >= pd.Timestamp(a, tz="UTC")) & (p94.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))].copy()
        ls.append(te94.assign(pred=np.mean(preds, axis=0)))
        preds = [select_fit_predict(p103, a, f103, f"y{h}", h, v103.EMBARGO, f"v103_h{h}")[0] for h in v103.HS]
        te103 = p103[(p103.t >= pd.Timestamp(a, tz="UTC")) & (p103.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))].copy()
        fl.append(te103.assign(pred=np.mean(preds, axis=0)))
        print(a, {k: len(v[a]) for k, v in KEPT.items()}, flush=True)
    lo, ls, fl = (pd.concat(x, ignore_index=True) for x in (lo, ls, fl))
    ic = {a: dict(v92=round(float(g[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4)) for a, g in
          ((a, lo[(lo.t >= pd.Timestamp(a, tz="UTC")) & (lo.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))]) for a in ext.v92.ANCHORS)}
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
    out = {"version": "v136", "kept_features": KEPT, "ic_v92": ic}
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print(sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_scenarios"] = res
    out["reference_v133"] = {"normal": 2.44, "fee_stress": 2.222, "execution_stress": 1.95}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v136_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
