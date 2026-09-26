"""v131: signal-strength timing of the v115 books (registry parallel-20260906-r2 / v131, track A).

The audited weight rules normalise each book to full gross whenever any asset has a signal, discarding the overall
prediction magnitude. For each book, strength_t = mean over assets of |pred| at bar t (after the book's gating: long-only
book uses max(pred,0) where the daily ribbon != -1); k_t = clip(strength_t / median(strength over the trailing 360 days,
bars before t), 0.5, 2.0), held with the book's daily rebalance schedule. Each book = weights * own vol scale * k (vol
scales computed on the un-multiplied weights, so the vol target cannot undo k). Portfolio: v115 (0.25/0.25/0.5, 15%
target, ungoverned, v110 engine) evaluated as the PHASE MEAN over six rebalance phases (v126 method); reference = v126
(2.311/2.09/1.815%/month). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v131/v131_signal_strength.py
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
PD = 6


def strength(df, long_only):
    g = df.copy()
    s = g["pred"].clip(lower=0).where(g["rib"] != -1, 0.0) if long_only else g["pred"].abs()
    st = s.groupby(g["t"]).mean().sort_index()
    med = st.rolling(360 * PD, min_periods=60 * PD).median().shift(1)
    return (st / med).clip(0.5, 2.0).fillna(1.0)


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    R_lo, R_ls, R_fl = v125.raw_lo(lo), v125.raw_ls(ls), v125.raw_ls(fl)
    K = {"lo": strength(lo, True), "ls": strength(ls, False), "fl": strength(fl, False)}
    per = {}
    for ph in range(PD):
        W_lo, W94, W103 = v125.phased(R_lo, [ph]), v125.phased(R_ls, [ph]), v125.phased(R_fl, [ph])
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103.t.min()]
        keep = pd.Series(np.arange(len(idx)) % PD == ph, index=idx)
        k = {n: v.reindex(idx).where(keep).ffill().fillna(1.0) for n, v in K.items()}
        b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0) * k["lo"], axis=0)
        b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0) * k["ls"], axis=0)
        b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0) * k["fl"], axis=0)
        per[ph] = {sc: v110.summarize(*v110.run(p103, 0.25 * b_lo + 0.25 * b94 + 0.5 * b103, 0.15, False, fee, slip)) for sc, (fee, slip) in ext.v92.SCEN.items()}
        print("phase", ph, {sc: (per[ph][sc]["monthly_pct"], per[ph][sc]["full_path_dd"]) for sc in per[ph]}, flush=True)
    out = {"version": "v131", "k_mean_by_book": {n: round(float(v[v.index >= pd.Timestamp(ext.v92.ANCHORS[0], tz="UTC")].mean()), 3) for n, v in K.items()}}
    out["primary_phase_mean"] = {sc: dict(monthly_pct=round(float(np.mean([per[p][sc]["monthly_pct"] for p in per])), 3),
                                          worst_year_dd=max(per[p][sc]["full_path_dd"] for p in per),
                                          yearly_mean=[round(float(np.mean([per[p][sc]["yearly"][i]["net_pct"] for p in per])), 2) for i in range(5)],
                                          per_phase=[(per[p][sc]["monthly_pct"], per[p][sc]["full_path_dd"]) for p in per]) for sc in ext.v92.SCEN}
    out["reference_v126_phase_mean"] = {"normal": 2.311, "fee_stress": 2.09, "execution_stress": 1.815}
    print("v131 phase mean", {sc: (v["monthly_pct"], v["worst_year_dd"]) for sc, v in out["primary_phase_mean"].items()}, out["k_mean_by_book"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v131_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
