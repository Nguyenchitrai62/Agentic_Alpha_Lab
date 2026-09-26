"""v126: rebalance-hour dispersion diagnostic for the v115 portfolio (registry parallel-20260906-r2 / v126).

v115 primary (0.25 v92 LO + 0.25 v94 LS on the v114 panel + 0.5 v103 LS; 15% target; ungoverned; v110 engine) run six
times, each with all three books rebalancing daily at a single phase p in 0..5 (keep rows with position % 6 == p). Phase
0 = v115. Reports each phase and the mean/min/max across phases: the phase mean is the timing-luck-free estimate of the
v115 result. Diagnostic, no selection. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v126/v126_phase_dispersion.py
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
    out = {"version": "v126", "phases": {}}
    for ph in range(v125.PD):
        W_lo, W94, W103 = v125.phased(R_lo, [ph]), v125.phased(R_ls, [ph]), v125.phased(R_fl, [ph])
        idx = W_lo.index.union(W94.index).union(W103.index)
        idx = idx[idx >= p103.t.min()]
        b_lo = W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p92, W_lo).reindex(idx).fillna(1.0), axis=0)
        b94 = W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p92, W94).reindex(idx).fillna(1.0), axis=0)
        b103 = W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
        res = {}
        for sc, (fee, slip) in ext.v92.SCEN.items():
            res[sc] = v110.summarize(*v110.run(p103, 0.25 * b_lo + 0.25 * b94 + 0.5 * b103, 0.15, False, fee, slip))
        out["phases"][f"p{ph}"] = res
        print("phase", ph, "first rebalance hour", str(W_lo.index[ph])[11:16], {sc: (res[sc]["monthly_pct"], res[sc]["full_path_dd"]) for sc in res}, flush=True)
    out["summary"] = {sc: dict(mean=round(float(np.mean([out["phases"][p][sc]["monthly_pct"] for p in out["phases"]])), 3),
                               min=min(out["phases"][p][sc]["monthly_pct"] for p in out["phases"]),
                               max=max(out["phases"][p][sc]["monthly_pct"] for p in out["phases"]),
                               max_full_dd=max(out["phases"][p][sc]["full_path_dd"] for p in out["phases"])) for sc in ext.v92.SCEN}
    out["primary_phase_mean"] = out["summary"]
    print("summary", out["summary"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v126_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
