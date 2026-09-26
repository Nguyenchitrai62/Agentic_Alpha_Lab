"""v142: cross-sectional (relative-to-other-majors) features for the directional books (registry v142, track C).

For key features c, add xs_c = c - mean over the majors present at the same bar t, and xr_c = percentile rank of c among
them (0..1). v114 panel (v92/v94 books): c in ret42, ret180, snr42, snr180, d50, d200, vol_ratio, volz, f7. v103 panel:
the same plus tbr_6, flow_42, tbr_z. Models/targets/embargoes/books unchanged (features appended); v133 pipeline
(vol-forecast sizing with the original feature sets, tranching, v115 portfolio 15% target). Differs from v102, which
traded a market-neutral book; here the relative features inform the directional models. Reference v133:
2.44/2.222/1.95. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v142/v142_cross_sectional_features.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v129", HERE.parent / "v129" / "v129_vol_forecast_sizing.py")
v129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v129)
v125, v115, v103, v110 = v129.v125, v129.v115, v129.v103, v129.v110
PD = 6
BASE = ("ret42", "ret180", "snr42", "snr180", "d50", "d200", "vol_ratio", "volz", "f7")
FLOWX = ("tbr_6", "flow_42", "tbr_z")


def add_xs(p, cols):
    p = p.copy()
    for c in cols:
        g = p.groupby("t")[c]
        p[f"xs_{c}"] = p[c] - g.transform("mean")
        p[f"xr_{c}"] = g.rank(pct=True)
    return p


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92_base = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    p92x = add_xs(p92, BASE)
    ext.v92.FEATS = [c for c in p92x.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92x, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92x)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103_base = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    p103x = add_xs(p103, BASE + FLOWX)
    f103 = [c for c in p103x.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl, ic = [], {}
    for a in ext.v92.ANCHORS:
        te, _ = v103.train_predict(p103x, a, f103)
        fl.append(te)
        g = lo[(lo.t >= pd.Timestamp(a, tz="UTC")) & (lo.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))]
        ic[a] = dict(v92=round(float(g[["pred", "y"]].corr(method="spearman").iloc[0, 1]), 4),
                     v103_y6=round(float(te[["pred", "y6"]].corr(method="spearman").iloc[0, 1]), 4))
        print(a, ic[a], flush=True)
    fl = pd.concat(fl, ignore_index=True)
    pv92, _ = v129.vol_predict(p92, f92_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

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
    out = {"version": "v142", "ic": ic}
    res = {}
    for sc, (fee, slip) in ext.v92.SCEN.items():
        res[sc] = v110.summarize(*v110.run(p103, books, 0.15, False, fee, slip))
        print(sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
    out["primary_scenarios"] = res
    out["reference_v133"] = {"normal": 2.44, "fee_stress": 2.222, "execution_stress": 1.95}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v142_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
