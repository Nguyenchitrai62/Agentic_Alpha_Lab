"""v122: 28-day horizon long/short book added to the v115 portfolio (registry parallel-20260906-r2 / v122, track C).

On the v114 extended panel: target y168 = clip(log(open[t+169]/open[t+1]) / (vol42*sqrt(168)), +-4); one HGB (v92
hyperparameters) per anchor with embargo 168 + 60 bars; book = audited v94 weights_ls (shorts on, daily) with its own
20% vol target. Primary: v115 portfolio with books 0.2 v92 LO + 0.2 v94 LS + 0.4 v103 LS + 0.2 y168 LS (15% target,
ungoverned, v110 engine). Secondary: the y168 LS book alone. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v122/v122_monthly_book.py
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
H168, EMB168 = 168, 168 + 60


def add_y168(panel):
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        o = g["open"].to_numpy()
        n = len(g)
        fwd = np.full(n, np.nan)
        fwd[: n - 1 - H168] = np.log(o[1 + H168:] / o[1: n - H168])
        g["y168"] = np.clip(fwd / (g["vol42"].to_numpy() * np.sqrt(H168)), -4, 4)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    W_lo = ext.v92.weights_from(pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True), "model")
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W94 = ext.v94.weights_ls(pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True), True)
    pm = add_y168(p92)
    preds, ic = [], {}
    for a in ext.v92.ANCHORS:
        A = pd.Timestamp(a, tz="UTC")
        cutoff = A - pd.Timedelta(hours=4 * EMB168)
        tr = pm[(pm.t < cutoff) & pm.y168.notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (H168 + 1)) < cutoff]
        te = pm[(pm.t >= A) & (pm.t < A + pd.Timedelta(days=365))].copy()
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
        te["pred"] = m.fit(tr[f94], tr["y168"]).predict(te[f94])
        preds.append(te)
        ic[a] = dict(train_rows=len(tr), ic_y168=round(float(te[["pred", "y168"]].corr(method="spearman").iloc[0, 1]), 4))
        print(a, ic[a], flush=True)
    W168 = ext.v94.weights_ls(pd.concat(preds, ignore_index=True), True)
    out = {"version": "v122", "ic": ic}
    out["secondary_y168_ls"] = v103.evaluate(p92, W168, "y168 LS", scale=ext.v94.vol_target_scale(p92, W168))
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W103 = ext.v94.weights_ls(pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True), True)
    idx = W_lo.index.union(W94.index).union(W103.index).union(W168.index)
    idx = idx[idx >= p103.t.min()]

    def sc_(W, p):
        return W.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p, W).reindex(idx).fillna(1.0), axis=0)

    b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
    books = 0.2 * b_lo + 0.2 * sc_(W94, p92) + 0.4 * sc_(W103, p103) + 0.2 * sc_(W168, p92)
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print("v122 portfolio", sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_portfolio"] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v122_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
