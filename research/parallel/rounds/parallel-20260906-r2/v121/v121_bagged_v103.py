"""v121: bagged v103 short-horizon model inside the v115 portfolio (registry parallel-20260906-r2 / v121, track B).

v103 model replaced by a bag of 10 members per horizon (y6, y18): member m trains on a random 70% of the training
calendar days (sampled without replacement with numpy seed m; all rows of a chosen day kept) with
HistGradientBoostingRegressor(v92 hyperparameters, max_features=0.7, random_state=m); prediction = mean over members and
horizons. Primary: v115 portfolio (0.25 v92 LO + 0.25 v94 LS on the v114 panel + 0.5 bagged-v103 LS; 15% target,
ungoverned, v110 engine). Secondary: the bagged LS book alone (own 20% vol target). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v121/v121_bagged_v103.py
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


v115 = _load("v115", "v115/v115_candidate.py")
v103, v110 = v115.v103, v115.v110
N_MEMBERS, FRAC = 10, 0.7


def train_predict_bag(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * v103.EMBARGO)
    te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
    preds = []
    for h in v103.HS:
        tr = panel[(panel.t < cutoff) & panel[f"y{h}"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        days = np.sort(tr.t.dt.floor("D").unique())
        for m in range(N_MEMBERS):
            pick = np.random.default_rng(m).choice(days, size=int(FRAC * len(days)), replace=False)
            sub = tr[tr.t.dt.floor("D").isin(pick)]
            mdl = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
                                                l2_regularization=1.0, max_features=0.7, random_state=m)
            preds.append(mdl.fit(sub[feats], sub[f"y{h}"]).predict(te[feats]))
    te["pred"] = np.mean(preds, axis=0)
    return te


def main():
    # v115 books with the v103 book swapped for the bagged one
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    W_lo = ext.v92.weights_from(pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True), "model")
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = ext.v94.weights_ls(pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True), True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    oos, ic = [], {}
    for a in ext.v92.ANCHORS:
        te = train_predict_bag(p103, a, f103)
        oos.append(te)
        ic[a] = {f"ic_y{h}": round(float(te[["pred", f"y{h}"]].corr(method="spearman").iloc[0, 1]), 4) for h in v103.HS}
        print(a, ic[a], flush=True)
    W103 = ext.v94.weights_ls(pd.concat(oos, ignore_index=True), True)
    out = {"version": "v121", "ic": ic}
    out["secondary_bagged_ls"] = v103.evaluate(p103, W103, "bagged v103 LS")
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print("v121 portfolio", sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_portfolio"] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v121_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
