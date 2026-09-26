"""v112: sign classifiers instead of clipped-return regression on the v103 setup (registry parallel-20260906-r2 / v112).

Same panel/features/embargo/horizons as v103 (v92 + order-flow features; y6, y18). For each horizon an
HistGradientBoostingClassifier (max_depth 4, learning_rate 0.03, max_iter 400, min_samples_leaf 300, l2 1.0,
random_state 0) predicts P(y_h > 0). Prediction = 2 * mean_h P(up) - 1 (range -1..1), fed to the audited v94
weights_ls (shorts on, daily) with its own 20% vol target. Secondary: 50/50 with the v96 books (as v103).
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v112/v112_sign_classifier.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v92 = _load("v92", "v92/v92_pooled_hgb_vt.py")
v94 = _load("v94", "v94/v94_long_short_ensemble.py")
v103 = _load("v103", "v103/v103_flow_short_horizon.py")


def train_predict(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * v103.EMBARGO)
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    probs = []
    for h in v103.HS:
        tr = panel[(panel.t < cutoff) & panel[f"y{h}"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        m = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
        m.fit(tr[feats], (tr[f"y{h}"] > 0).astype(int))
        probs.append(m.predict_proba(te[feats])[:, 1])
    te["pred"] = 2 * np.mean(probs, axis=0) - 1
    return te


def main():
    panel = v103.build()
    feats = [c for c in panel.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    oos, ic = [], {}
    for a in v92.ANCHORS:
        te = train_predict(panel, a, feats)
        oos.append(te)
        ic[a] = {f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in v103.HS}
        print(a, ic[a], flush=True)
    oos = pd.concat(oos, ignore_index=True)
    out = {"version": "v112", "ic": ic}
    W = v94.weights_ls(oos, True)
    out["primary_long_short"] = v103.evaluate(panel, W, "v112 LS")
    p92 = v92.build()
    v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    W_lo = v92.weights_from(pd.concat([v92.train_predict(p92, a)[0] for a in v92.ANCHORS], ignore_index=True), "model")
    p94 = v94.add_targets(v92.build())
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = v94.weights_ls(pd.concat([v94.train_predict(p94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True), True)
    idx = W_lo.index.union(W94.index).union(W.index)
    v96 = 0.5 * W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W94.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(p94, W94).reindex(idx).fillna(1.0), axis=0)
    W112 = W.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(panel, W).reindex(idx).fillna(1.0), axis=0)
    out["secondary_blend_v96"] = v103.evaluate(p92, 0.5 * v96 + 0.5 * W112, "0.5 v96 + 0.5 v112", scale=1.0)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v112_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
