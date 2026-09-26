"""v129: size the v115 books by a forecast of forward volatility instead of trailing vol42 (registry parallel-20260906-r2 / v129).

Vol model per panel (v114 panel for the v92/v94 books with v92 features; v103 panel with v92 + flow features for the v103
book): target fv = log(std of open-to-open 4h log returns over bars t+2..t+43) (the 42 bars the position is exposed to);
HistGradientBoostingRegressor(v92 hyperparameters) trained per anchor with the v92 cutoff/embargo (rows need
t + 44*4h < cutoff). pvol = exp(prediction). In each book's OOS prediction frame the sizing column vol42 is replaced by
pvol before the audited weight formulas (signals and model targets unchanged); each book keeps its own causal vol target.
Portfolio: v115 (0.25/0.25/0.5, 15% target, ungoverned, v110 engine), evaluated as the PHASE MEAN over the six rebalance
phases (v126 method, v125 helpers). Reference: the same with vol42 (= v126 phase mean). Also reported: Spearman of
pvol and of vol42 with the realized forward vol per anchor. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v129/v129_vol_forecast_sizing.py
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
spec = importlib.util.spec_from_file_location("v125", HERE.parent / "v125" / "v125_tranching.py")
v125 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v125)
v115, v103, v110 = v125.v115, v125.v103, v125.v110
PD, HV = 6, 42


def add_fv(panel):
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        r = np.log(g["open"]).diff()
        g["fv"] = np.log(r.rolling(HV).std().shift(-(HV + 1)))  # std of r[t+2..t+43]
        out.append(g)
    return pd.concat(out, ignore_index=True)


def vol_predict(panel, feats, anchors, embargo_bars):
    p = add_fv(panel)
    res, q = [], {}
    for a in anchors:
        A = pd.Timestamp(a, tz="UTC")
        cutoff = A - pd.Timedelta(hours=4 * embargo_bars)
        tr = p[(p.t < cutoff) & p.fv.notna() & np.isfinite(p.fv)]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (HV + 2)) < cutoff]
        te = p[(p.t >= A) & (p.t < A + pd.Timedelta(days=365))].copy()
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300, l2_regularization=1.0, random_state=0)
        te["pvol"] = np.exp(m.fit(tr[feats], tr["fv"]).predict(te[feats]))
        g = te.dropna(subset=["fv"])
        q[a] = dict(spearman_pvol=round(float(g["pvol"].corr(np.exp(g["fv"]), method="spearman")), 3),
                    spearman_vol42=round(float(g["vol42"].corr(np.exp(g["fv"]), method="spearman")), 3))
        res.append(te[["t", "sym", "pvol"]])
    return pd.concat(res, ignore_index=True), q


def phase_mean(ext, p92, p103, lo, ls, fl):
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
    return {sc: dict(monthly_pct=round(float(np.mean([per[p][sc]["monthly_pct"] for p in per])), 3),
                     worst_year_dd=max(per[p][sc]["full_path_dd"] for p in per),
                     yearly_mean=[round(float(np.mean([per[p][sc]["yearly"][i]["net_pct"] for p in per])), 2) for i in range(5)],
                     per_phase=[(per[p][sc]["monthly_pct"], per[p][sc]["full_path_dd"]) for p in per]) for sc in ext.v92.SCEN}


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
    pv92, q92 = vol_predict(p92, ext.v92.FEATS, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, q103 = vol_predict(p103, f103, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    print("vol forecast quality v114 panel", q92, "v103 panel", q103, flush=True)

    def swap(df, pv):
        d = df.merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    out = {"version": "v129", "vol_quality": {"v114_panel": q92, "v103_panel": q103}}
    out["primary_phase_mean"] = phase_mean(ext, p92, p103, swap(lo, pv92), swap(ls, pv92), swap(fl, pv103))
    print("vol-forecast sizing", {sc: (v["monthly_pct"], v["worst_year_dd"]) for sc, v in out["primary_phase_mean"].items()}, flush=True)
    out["reference_vol42_phase_mean"] = phase_mean(ext, p92, p103, lo, ls, fl)
    print("vol42 sizing (reference)", {sc: (v["monthly_pct"], v["worst_year_dd"]) for sc, v in out["reference_vol42_phase_mean"].items()}, flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v129_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
