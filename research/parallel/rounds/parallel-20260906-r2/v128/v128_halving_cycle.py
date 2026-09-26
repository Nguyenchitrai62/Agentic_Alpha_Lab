"""v128: Bitcoin halving-cycle phase features on the v114 extended panel (registry parallel-20260906-r2 / v128, track B).

Halving dates (public, known in advance): 2012-11-28, 2016-07-09, 2020-05-11, 2024-04-20 (next expected 2028-04).
Market-wide features at bar t: hv_days = days since the last halving / 1461; hv_sin, hv_cos = sin/cos(2*pi*hv_days).
Added to the v92/v94 features; books retrained on the v114 panel; primary: v115 portfolio (0.25/0.25/0.5 with unchanged
v103, 15% target, ungoverned, v110 engine) evaluated as the PHASE MEAN over the six rebalance phases (v126 method);
reference: the same phase mean without the features. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v128/v128_halving_cycle.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v125", HERE.parent / "v125" / "v125_tranching.py")
v125 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v125)
v115, v103, v110 = v125.v115, v125.v103, v125.v110
HALVINGS = pd.to_datetime(["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"], utc=True)
PD = 6


def add_cycle(p):
    t = p["t"]
    last = HALVINGS[np.searchsorted(HALVINGS.values, t.values, side="right") - 1]
    days = (t - pd.DatetimeIndex(last)).dt.total_seconds().to_numpy() / 86400 / 1461
    return p.assign(hv_days=days, hv_sin=np.sin(2 * np.pi * days), hv_cos=np.cos(2 * np.pi * days))


def phase_mean(ext, p92, p94, f94, fl, p103):
    lo = pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    R_lo, R_ls, R_fl = v125.raw_lo(lo), v125.raw_ls(ls), v125.raw_ls(fl)
    per = {}
    for ph in range(PD):
        W_lo, W94, W103 = v125.phased(R_lo, [ph]), v125.phased(R_ls, [ph]), v125.phased(R_fl, [ph])
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103.t.min()]
        b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
        b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)
        b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
        per[ph] = {sc: v110.summarize(*v110.run(p103, 0.25 * b_lo + 0.25 * b94 + 0.5 * b103, 0.15, False, fee, slip)) for sc, (fee, slip) in ext.v92.SCEN.items()}
    ic = {a: round(float(g[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4) for a, g in lo.groupby(lo.t.apply(lambda x: max(a for a in ext.v92.ANCHORS if x >= pd.Timestamp(a, tz="UTC"))))}
    summ = {sc: dict(monthly_pct=round(float(np.mean([per[p][sc]["monthly_pct"] for p in per])), 3),
                     full_path_dd_max=max(per[p][sc]["full_path_dd"] for p in per),
                     yearly_mean=[round(float(np.mean([per[p][sc]["yearly"][i]["net_pct"] for p in per])), 2) for i in range(5)]) for sc in ext.v92.SCEN}
    return dict(ic_v92=ic, summary=summ, per_phase={p: {sc: (per[p][sc]["monthly_pct"], per[p][sc]["full_path_dd"]) for sc in per[p]} for p in per})


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    base = ext.v92.build()
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    out = {"version": "v128"}
    for key, p92 in (("primary_cycle_features", add_cycle(base)), ("reference_no_cycle", base)):
        ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
        p94 = ext.v94.add_targets(p92)
        f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
        out[key] = phase_mean(ext, p92, p94, f94, fl, p103)
        print(key, out[key]["ic_v92"], out[key]["summary"], flush=True)
    out["primary_phase_mean"] = {sc: dict(monthly_pct=v["monthly_pct"], worst_year_dd=v["full_path_dd_max"]) for sc, v in out["primary_cycle_features"]["summary"].items()}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v128_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
