"""oc_netting final numbers (LIGHT): 5y stats + full-path DD for the dev4 pick.

Dev years (0-3) from tmp/engine_dev.pkl, recent year (4, scored ONCE) from
tmp/engine_full.pkl; full-path DD via stitched per-shift series + v388.mix
(same convention as v421/oc_governor). G2 REF rows from the store (labelled).
No 1m. Writes tmp/final.json.

  .venv/Scripts/python.exe research/tournament/oc_netting/compute_fullpath.py
"""
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
    rm = _load("reset_for_netfinal", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_for_netfinal", RD / "v388/v388_bot_stop_distance.py")
    dev = pickle.loads((HERE / "tmp/engine_dev.pkl").read_bytes())
    full = pickle.loads((HERE / "tmp/engine_full.pkl").read_bytes())
    stored = pickle.loads(STORED.read_bytes())
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"][STRAT]

    rows = {}
    # 5y stats: dev years from dev runs, recent year (ONCE) from full runs.
    for r, src in (("G2REF", None), ("N1", None), ("N2", None)):
        if r == "G2REF":
            yy = [rm.year_reset(stored, STRAT, y) for y in range(5)]
        else:
            runs_dev = {s: {"N1": dev[s]["N1"]} for s in dev}
            runs_full = {s: {"N1": full[s]["N1"]} for s in full}
            yy = [rm.year_reset(runs_dev, "N1", y) for y in range(4)]
            yy.append(rm.year_reset(runs_full, "N1", 4))
        geo5 = 100 * (np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / 5) - 1)
        geo4 = 100 * (np.prod([1 + y["R"] / 100 for y in yy[:4]]) ** (1 / 4) - 1)
        rows[r] = dict(years=[(y["R"], y["DD"]) for y in yy],
                       dev4_R=round(float(geo4), 3), dev4_W=min(y["R"] for y in yy[:4]),
                       dev4_DD=max(y["DD"] for y in yy[:4]),
                       dev4_losing=sum(y["R"] < 0 for y in yy[:4]),
                       recent_R=yy[4]["R"], recent_DD=yy[4]["DD"],
                       R5=round(float(geo5), 3), W5=min(y["R"] for y in yy),
                       DD5=max(y["DD"] for y in yy), losing5=sum(y["R"] < 0 for y in yy))
        print(r, rows[r], flush=True)

    # Full-path DD: stitch dev + full per shift for N1 (== N2 path-wise).
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    stitched = {}
    for s in range(4):
        d, f = dev[s]["N1"], full[s]["N1"]
        td = pd.to_datetime(d["t"], utc=True)
        tf = pd.to_datetime(f["t"], utc=True)
        cut = td.max()
        keep = tf > cut
        stitched[s] = {"N1": {"t": d["t"] + [t for t, k in zip(f["t"], keep) if k],
                              "eq": d["eq"] + [e for e, k in zip(f["eq"], keep) if k],
                              "eq_min": d["eq_min"] + [e for e, k in zip(f["eq_min"], keep) if k]}}
    e, mn = v388.mix(stitched, "N1", g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    dd_c = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
    dd_m = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    rows["N1"]["full_path_dd"] = max(dd_c, dd_m)
    rows["N2"]["full_path_dd"] = max(dd_c, dd_m)  # N2 == N1 path-wise
    rows["G2REF"]["full_path_dd"] = exp["full_path_dd"]
    print("N1/N2 full-path close/marked/gate:", dd_c, dd_m, max(dd_c, dd_m), flush=True)
    print("G2REF full-path (stored):", exp["full_path_dd"], flush=True)
    (HERE / "tmp/final.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
