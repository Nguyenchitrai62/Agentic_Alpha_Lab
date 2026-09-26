"""v146: relative (cross-sectional) positioning features on top of v144 (registry v146, track B).

v139 showed absolute positioning levels (open interest, long/short ratios) help 2022-24 but drift in the hidden year.
v146 adds ONLY their cross-sectional versions to the v103 panel of v144: xs_c = c - mean over majors at t and
xr_c = percentile rank at t, for c in oi_chg6, oi_chg42, top_ls_z, crowd_ls_z, taker_ls6 (v139 definitions, last metrics
row <= bar close - 5 min; NaN before the data exists). Raw positioning columns are NOT model inputs. Everything else =
v144 (v142 xs books, vol-forecast sizing with the original feature sets, tranching, realistic 10 bps 1m execution,
governor). Rows as v144; primary = 0.25 governed. Reference v144: 2.361/16.89, 2.955/18.28, 3.374/19.63. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v146/v146_relative_positioning.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v144 = _load("v144", "v144/v144_deploy_v3.py")
v139 = _load("v139", "v139/v139_positioning.py")
REL = ("oi_chg6", "oi_chg42", "top_ls_z", "crowd_ls_z", "taker_ls6")


def books(rel_cols):
    """Copy of v144.books_v142 with the relative positioning columns added to the v103 model inputs only."""
    import numpy as np  # noqa: F401
    v142, v129, v125, v115, v103 = v144.v142, v144.v129, v144.v125, v144.v115, v144.v103
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    p92 = ext.v92.build()
    f92_base = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    p92x = v142.add_xs(p92, v142.BASE)
    ext.v92.FEATS = [c for c in p92x.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92x, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92x)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103_base = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    pos = pd.concat([v139.pos_features(g.sort_values("t"), s) for s, g in p103.groupby("sym")], ignore_index=True)
    q = p103.merge(pos[["t", "sym"] + list(REL)], on=["t", "sym"], how="left")
    for c in REL:
        g = q.groupby("t")[c]
        q[f"xs_{c}"] = q[c] - g.transform("mean")
        q[f"xr_{c}"] = g.rank(pct=True)
    q = q.drop(columns=list(REL))
    p103x = v142.add_xs(q, v142.BASE + v142.FLOWX)
    f103 = [c for c in p103x.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    rel_cols.extend(c for c in f103 if c.endswith(REL))
    fl = pd.concat([v103.train_predict(p103x, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    pv92, _ = v129.vol_predict(p92, f92_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)
    pv103, _ = v129.vol_predict(p103, f103_base, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

    def swap(df, pv):
        d = df.merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    ph = list(range(6))
    W_lo = v125.phased(v125.raw_lo(swap(lo, pv92)), ph)
    W94 = v125.phased(v125.raw_ls(swap(ls, pv92)), ph)
    W103 = v125.phased(v125.raw_ls(swap(fl, pv103)), ph)
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    bk = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)         + 0.25 * W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)         + 0.5 * W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    return p103, bk


def main():
    rel_cols = []
    p103, bk = books(rel_cols)
    print("added columns", rel_cols, flush=True)
    out = {"version": "v146", "added_columns": rel_cols, **v144.simulate(p103, bk)}
    out["reference_v144"] = {"t15": (2.361, 16.89), "t20": (2.955, 18.28), "t25": (3.374, 19.63)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v146_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
