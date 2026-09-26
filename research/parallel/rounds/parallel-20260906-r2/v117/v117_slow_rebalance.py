"""v117: slower rebalancing of the 7-day books inside the v115 portfolio (registry parallel-20260906-r2 / v117, track A).

v115 exactly, except the v92 long-only and v94 long/short weight rules keep every k-th 4h row (k = 12, every 2 days,
primary; k = 42, weekly, secondary; v115 uses k = 6) and forward-fill between; the v103 book stays daily. Weight
formulas are the audited v92.weights_from / v94.weights_ls with the rebalance step as a parameter (the annualisation
constant cancels in the gross normalisation). Portfolio: v110 engine at target 0.15, ungoverned (v115 primary settings).
Reference: k = 6 (= v115). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v117/v117_slow_rebalance.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v114 = _load("v114", "v114/v114_bitstamp_history.py")
v103 = _load("v103", "v103/v103_flow_short_horizon.py")
v110 = _load("v110", "v110/v110_dd_governor.py")
PD = 6
SYMS = 5


def lo_weights(df, k):
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = (g["pred"].clip(lower=0) / 0.5).where(g["rib"] != -1, 0.0).clip(upper=1.0)
        W[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    n_assets = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(W.abs().sum(axis=1).clip(lower=1e-9), axis=0).mul(W.abs().sum(axis=1).gt(0), axis=0)
    W = W.mul((n_assets / SYMS).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % k == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def ls_weights(df, k):
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        long_ = (g["pred"].clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != -1, 0.0)
        short = ((-g["pred"]).clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != 1, 0.0)
        W[s] = (long_ - short) / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    gross, active = W.abs().sum(axis=1), W.ne(0).sum(axis=1)
    W = W.div(gross.where(gross > 0, 1.0), axis=0).mul((active / SYMS).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % k == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def main():
    v114.v113.cb_bars = v114.cb_bars_ext
    ext = v114.v113
    v92, v94 = ext.v92, ext.v94
    v92.load_asset = ext.load_asset_ext
    p92 = v92.build()
    v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([v92.train_predict(p92, a)[0] for a in v92.ANCHORS], ignore_index=True)
    p94 = v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([v94.train_predict(p94, a, f94)[0] for a in v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    W103 = v94.weights_ls(pd.concat([v103.train_predict(p103, a, f103)[0] for a in v92.ANCHORS], ignore_index=True), True)
    assert np.allclose(lo_weights(lo, 6).to_numpy(), v92.weights_from(lo, "model").to_numpy())
    assert np.allclose(ls_weights(ls, 6).to_numpy(), v94.weights_ls(ls, True).to_numpy())
    out = {"version": "v117"}
    for key, k in (("primary_k12", 12), ("secondary_k42", 42), ("reference_k6_v115", 6)):
        W_lo, W94 = lo_weights(lo, k), ls_weights(ls, k)
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103.t.min()]
        b_lo = W_lo.reindex(idx).fillna(0.0).mul(v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
        b94 = W94.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)
        b103 = W103.reindex(idx).fillna(0.0).mul(v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
        books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
        res = {}
        for sc, (fee, slip) in v92.SCEN.items():
            res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
            print(key, sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"], y["fills"]) for y in res[sc]["yearly"]], flush=True)
        out[key] = res
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v117_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
