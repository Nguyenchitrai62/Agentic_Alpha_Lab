"""v119: nested time-series hyperparameter selection for the v92 model on the v114 panel (registry parallel-20260906-r2 / v119).

For each anchor, within its training rows only (v92 cutoff/embargo): validation = rows with t in the last 730 days
before the cutoff; inner-train = rows with t + (H+1)*4h < val_start - EMBARGO_BARS*4h (labels realized before an inner
embargo). Grid (fixed): max_depth in (3, 4, 6) x min_samples_leaf in (300, 1000); learning_rate 0.03, max_iter 400,
l2 1.0, random_state 0. Score = pooled Spearman IC on validation. The best config is refit on all training rows and
predicts the test year. Primary: v92 long-only book (v92 vol target) on the v114 panel. Secondary: 50/50 with the
v114-panel v94 long/short book (v96 structure). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v119/v119_nested_cv.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v114 = _load("v114", "v114/v114_bitstamp_history.py")
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
GRID = [(d, l) for d in (3, 4, 6) for l in (300, 1000)]


def hgb(d, l):
    return HistGradientBoostingRegressor(max_depth=d, learning_rate=0.03, max_iter=400, min_samples_leaf=l, l2_regularization=1.0, random_state=0)


def main():
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    v92, v94 = ext.v92, ext.v94
    v92.load_asset = ext.load_asset_ext
    panel = v92.build()
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar")]
    v92.FEATS = feats
    step = pd.Timedelta(hours=4)
    preds, info = [], {}
    for a in v92.ANCHORS:
        A = pd.Timestamp(a, tz="UTC")
        cutoff = A - v92.EMBARGO_BARS * step
        tr = panel[(panel.t < cutoff) & panel.y.notna()]
        tr = tr[tr.t + (v92.H + 1) * step < cutoff]
        val_start = cutoff - pd.Timedelta(days=730)
        val = tr[tr.t >= val_start]
        itr = tr[tr.t + (v92.H + 1) * step < val_start - v92.EMBARGO_BARS * step]
        scores = {}
        for d, l in GRID:
            m = hgb(d, l).fit(itr[feats], itr["y"])
            scores[f"d{d}_l{l}"] = round(float(pd.Series(m.predict(val[feats])).corr(val["y"].reset_index(drop=True), method="spearman")), 4)
        best = max(scores, key=scores.get)
        d, l = (int(x[1:]) for x in best.split("_"))
        te = panel[(panel.t >= A) & (panel.t < A + pd.Timedelta(days=365))].copy()
        te["pred"] = hgb(d, l).fit(tr[feats], tr["y"]).predict(te[feats])
        preds.append(te)
        info[a] = dict(val_scores=scores, chosen=best, ic_test=round(float(te[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4))
        print(a, info[a], flush=True)
    oos = pd.concat(preds, ignore_index=True)
    W_lo = v92.weights_from(oos, "model")
    out = {"version": "v119", "selection": info}
    out["primary_v92_lo_nested"] = v103.evaluate(panel, W_lo, "v119 v92 LO nested", scale=v92.vol_target_scale(panel, W_lo))
    p94 = v94.add_targets(panel)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = v94.weights_ls(pd.concat([v94.train_predict(p94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True), True)
    idx = W_lo.index.union(W94.index)
    W96 = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(panel, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W94.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel, W94).reindex(idx).fillna(1.0), axis=0)
    out["secondary_v96_blend"] = v103.evaluate(panel, W96, "v119 v96 blend", scale=1.0)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v119_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
