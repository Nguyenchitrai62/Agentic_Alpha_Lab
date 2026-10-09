"""oc_governor analysis (read-only on tmp/ + stored runs): selection + GV3 dd-gap."""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
STORED = RD / "v421/v421_runs.pkl"
STRAT = "R2B1D17BFG2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    rm = _load("reset_for_govana", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_for_govana", RD / "v388/v388_bot_stop_distance.py")
    dev = pickle.loads((HERE / "tmp" / "engine_dev.pkl").read_bytes())
    full = pickle.loads((HERE / "tmp" / "engine_full.pkl").read_bytes())
    stored = pickle.loads(STORED.read_bytes())
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"][STRAT]

    # 5y stats: dev years from dev runs, recent year from full runs (scored ONCE)
    rows = {}
    for r in ("G2REF", "GV1", "GV2", "GV3"):
        src_dev = dev if r in dev[0] else None
        if r == "G2REF":
            yy = [rm.year_reset(stored, STRAT, y) for y in range(5)]
        else:
            runs_dev = {s: {r: dev[s][r]} for s in dev}
            runs_full = {s: {r: full[s][r]} for s in full}
            yy = [rm.year_reset(runs_dev, r, y) for y in range(4)]
            yy.append(rm.year_reset(runs_full, r, 4))
        geo5 = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / 5) - 1)
        geo4 = 100 * (np.prod([1 + y["R"] / 100 for y in yy[:4]]) ** (1 / 4) - 1)
        rows[r] = dict(years=[(y["R"], y["DD"]) for y in yy],
                       dev4_R=round(float(geo4), 3),
                       dev4_W=min(y["R"] for y in yy[:4]),
                       dev4_DD=max(y["DD"] for y in yy[:4]),
                       dev4_losing=sum(y["R"] < 0 for y in yy[:4]),
                       recent_R=yy[4]["R"], recent_DD=yy[4]["DD"],
                       R5=round(float(geo5), 3),
                       W5=min(y["R"] for y in yy),
                       DD5=max(y["DD"] for y in yy),
                       losing5=sum(y["R"] < 0 for y in yy))
        print(r, rows[r], flush=True)

    # full-path DD via v388.mix (dev+full stitched per shift for GVx; stored for G2)
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    for r in ("GV1", "GV2", "GV3"):
        stitched = {}
        for s in range(4):
            d, f = dev[s][r], full[s][r]
            # dev covers live ..2025-09-24+sh, full covers ..Y1+sh; stitch: dev bars + full bars after dev end
            td = pd.to_datetime(d["t"], utc=True)
            tf = pd.to_datetime(f["t"], utc=True)
            cut = td.max()
            keep = tf > cut
            stitched[s] = {r: {"t": d["t"] + [t for t, k in zip(f["t"], keep) if k],
                               "eq": d["eq"] + [e for e, k in zip(f["eq"], keep) if k],
                               "eq_min": d["eq_min"] + [e for e, k in zip(f["eq_min"], keep) if k]}}
        e, mn = v388.mix(stitched, r, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        rows[r]["full_path_dd"] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        print(r, "full-path DD", rows[r]["full_path_dd"], flush=True)
    rows["G2REF"]["full_path_dd"] = exp["full_path_dd"]

    # GV3 pass1 vs pass2 combined dd gap (hourly grid, full window)
    g0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    grid = pd.date_range(g0, g1, freq="1h")
    Es1 = []
    for s in range(4):
        e1, _ = v388.hourly(stored[s][STRAT], g0, g1)
        Es1.append(e1.to_numpy(float))
    E1 = np.mean(np.stack(Es1), axis=0)
    dd1 = 1 - E1 / np.maximum.accumulate(E1)
    Es2 = []
    for s in range(4):
        d, f = dev[s]["GV3"], full[s]["GV3"]
        td = pd.to_datetime(d["t"], utc=True)
        tf = pd.to_datetime(f["t"], utc=True)
        cut = td.max()
        t_all = list(td) + [t for t in tf if t > cut]
        e_all = list(d["eq"]) + [e for e, t in zip(f["eq"], tf) if t > cut]
        e2 = pd.Series(np.asarray(e_all, float), index=pd.DatetimeIndex(t_all)).reindex(grid, method="ffill").fillna(1.0)
        Es2.append(e2.to_numpy(float))
    E2 = np.mean(np.stack(Es2), axis=0)
    dd2 = 1 - E2 / np.maximum.accumulate(E2)
    gap = dict(max_abs=round(float(np.max(np.abs(dd2 - dd1))), 5),
                mean_abs=round(float(np.mean(np.abs(dd2 - dd1))), 5),
                max_dd1=round(float(dd1.max()), 4), max_dd2=round(float(dd2.max()), 4))
    print("GV3 pass1-vs-pass2 combined-dd gap:", gap, flush=True)

    (HERE / "tmp" / "analysis.json").write_text(json.dumps(dict(rows=rows, gv3_dd_gap=gap), indent=1, default=str))
    print("wrote tmp/analysis.json", flush=True)


if __name__ == "__main__":
    main()
