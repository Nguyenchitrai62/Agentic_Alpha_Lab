"""v132: universe breadth - add DOGE, TRX, ADA (top-10 non-stable large caps) as TRADED assets (registry v132).

Research only: trading these needs the user's approval (the user limited trading to BTC/ETH/SOL and large caps).
All v115 books are rebuilt on 8 assets (5 majors + DOGEUSDT, TRXUSDT, ADAUSDT from data/raw/xs_universe_20260924; no
spot prefix for the new assets; asset ids 5-7): v92 LO and v94 LS on the v114 panel, v103 LS on the v103 panel; the
partial-exposure rule uses 8 assets. Carry sleeve unchanged (majors). Portfolio v115 (0.25/0.25/0.5, 15% target,
ungoverned, v110 engine) evaluated as the PHASE MEAN over six rebalance phases (v129.phase_mean). Reference: the 5-asset
phase mean (v126: 2.311/2.09/1.815%/month). Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v132/v132_breadth.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v129", HERE.parent / "v129" / "v129_vol_forecast_sizing.py")
v129 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v129)
v125, v115, v103 = v129.v125, v129.v115, v129.v103
SYMS8 = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "TRXUSDT", "ADAUSDT")


def main():
    ext = v115.v114.v113
    v115.v114.v113.cb_bars = v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    for mod in (ext.v92, ext.v94.v92, v103.v92):
        mod.SYMS = SYMS8
    v125.SYMS = len(SYMS8)
    p92 = ext.v92.build()
    ext.v92.FEATS = [c for c in p92.columns if c not in ("y", "t", "open", "sym", "bar")]
    lo = pd.concat([ext.v92.train_predict(p92, a)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p94 = ext.v94.add_targets(p92)
    f94 = [c for c in p94.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    ls = pd.concat([ext.v94.train_predict(p94, a, f94)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    p103 = v103.build()
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    fl = pd.concat([v103.train_predict(p103, a, f103)[0] for a in ext.v92.ANCHORS], ignore_index=True)
    ic = {}
    for name, df, col in (("v92", lo, "y"), ("v94", ls, "y42"), ("v103", fl, "y6")):
        for s, g in df.groupby("sym"):
            ic.setdefault(name, {})[s] = round(float(g[["pred", col]].corr(method="spearman").iloc[0, 1]), 4)
    print("per-asset OOS IC", ic, flush=True)
    out = {"version": "v132", "assets": SYMS8, "ic_by_asset": ic}
    out["primary_phase_mean"] = v129.phase_mean(ext, p92, p103, lo, ls, fl)
    out["reference_5asset_v126"] = {"normal": 2.311, "fee_stress": 2.09, "execution_stress": 1.815}
    print("8-asset phase mean", {sc: (v["monthly_pct"], v["worst_year_dd"]) for sc, v in out["primary_phase_mean"].items()}, flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v132_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
