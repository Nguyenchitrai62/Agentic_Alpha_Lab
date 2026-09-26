"""v97: fixed tree ensemble on the audited v92 pipeline (registry parallel-20260906-r2 / v97, track B).

Members (fixed in advance): HistGradientBoostingRegressor with max_features=0.7 for seeds 0..4 at depths
3, 4 and 6 (15 models; other hyperparameters as v92) plus ExtraTreesRegressor(n_estimators=300,
min_samples_leaf=300, max_features=0.5, random_state=0) on median-imputed features (medians from the
training rows only). Prediction = mean of the 16 members. Book: v92 long-only with causal 20% vol target;
reference: 50/50 with the audited v94 long/short book as in v96.

  python research/parallel/rounds/parallel-20260906-r2/v97/v97_tree_ensemble.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")


def train_predict_ensemble(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * v92.EMBARGO_BARS)
    tr = panel[(panel.t < cutoff) & panel.y.notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (v92.H + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    preds = []
    for depth in (3, 4, 6):
        for seed in range(5):
            m = HistGradientBoostingRegressor(max_depth=depth, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
                                              l2_regularization=1.0, max_features=0.7, random_state=seed)
            m.fit(tr[feats], tr["y"])
            preds.append(m.predict(te[feats]))
    med = tr[feats].median()
    et = ExtraTreesRegressor(n_estimators=300, min_samples_leaf=300, max_features=0.5, random_state=0, n_jobs=-1)
    et.fit(tr[feats].fillna(med), tr["y"])
    preds.append(et.predict(te[feats].fillna(med)))
    te["pred"] = np.mean(preds, axis=0)
    te["pred_hgb_only"] = np.mean(preds[:-1], axis=0)
    return te, len(tr)


def book(panel, W, label):
    s = v92.vol_target_scale(panel, W)
    res = {}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, s, fee, slip)
        yearly = []
        for a in v92.ANCHORS:
            a0 = pd.Timestamp(a, tz="UTC")
            m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
            yearly.append(dict(anchor=a, **v92.stats(net[m], turn[m])))
        nets = [y["net_pct"] for y in yearly]
        geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
        res[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
    n = res["normal"]
    print(label, "| monthly", n["monthly_pct"], "worstDD", n["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in n["yearly"]], flush=True)
    return res


def main():
    panel = v92.build()
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    v92.FEATS = feats
    preds, ics = [], {}
    for a in v92.ANCHORS:
        te, ntr = train_predict_ensemble(panel, a, feats)
        preds.append(te)
        ics[a] = dict(train_rows=ntr, ic_ensemble=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4),
                      ic_hgb_only=round(float(te[["pred_hgb_only", "y"]].corr(method="spearman").iloc[0, 1]), 4))
        print(a, ics[a], flush=True)
    oos = pd.concat(preds, ignore_index=True)
    out = {"version": "v97", "ic": ics}
    out["ensemble_long_only"] = book(panel, v92.weights_from(oos, "model"), "v97 ensemble long-only")
    # reference: 50/50 with the audited v94 long/short book (each with its own vol target), as in v96
    panel94 = v94.add_targets(v92.build())
    feats94 = [c for c in panel94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([v94.train_predict(panel94, a, feats94)[0] for a in v92.ANCHORS], ignore_index=True)
    W_ls = v94.weights_ls(ls, True)
    W_lo = v92.weights_from(oos, "model")
    idx = W_lo.index.union(W_ls.index)
    W = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(panel, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W_ls.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel94, W_ls).reindex(idx).fillna(1.0), axis=0)
    res = {}
    for sc, (fee, slip) in v92.SCEN.items():
        net, turn = v92.simulate(panel, W, 1.0, fee, slip)
        yearly = [dict(anchor=a, **v92.stats(net[(net.index >= pd.Timestamp(a, tz="UTC")) & (net.index < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))],
                                             turn[(turn.index >= pd.Timestamp(a, tz="UTC")) & (turn.index < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))]))
                  for a in v92.ANCHORS]
        geo = np.prod([1 + y["net_pct"] / 100 for y in yearly]) ** (1 / 5) - 1
        res[sc] = dict(yearly=yearly, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3), worst_year_dd=max(y["max_drawdown_percent"] for y in yearly))
    out["reference_blend_with_v94"] = res
    n = res["normal"]
    print("v97 ensemble + v94 LS 50/50 (reference) | monthly", n["monthly_pct"], "worstDD", n["worst_year_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in n["yearly"]])
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v97_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
