"""Reproduce G2 baseline (v421 R2B1D17BFG2) to the digit before any overlay.

Expected (v421_result.json): dev [(2.588/10.86),(3.282/16.91),(6.045/15.81),
(10.677/8.27)], Y4 (4.648/12.90), 5y 5.41, full-path DD 16.82.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421"

EXP_DEV = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
EXP_Y4 = (4.648, 12.90)
EXP_5Y = 5.41
EXP_FULL = 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    import pickle
    runs = pickle.loads((V421 / "v421_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}, set(runs)
    strat = "R2B1D17BFG2"
    rm = _load("reset_ck", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_ck", RD / "v388/v388_bot_stop_distance.py")
    got_dev = [(rm.year_reset(runs, strat, y)["R"],
                rm.year_reset(runs, strat, y)["DD"]) for y in range(4)]
    y4 = rm.year_reset(runs, strat, 4)
    import numpy as np
    import pandas as pd
    yrs5 = [rm.year_reset(runs, strat, y)["R"] for y in range(5)]
    geo5 = round(100 * (np.prod([1 + r / 100 for r in yrs5]) ** (1 / 5) - 1), 3)
    e, mn = v388.mix(runs, strat, v388.Y1 + pd.Timedelta(hours=12))
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    print("dev:", got_dev, flush=True)
    print("y4:", (y4["R"], y4["DD"]), "5y:", geo5, "full:", full, flush=True)
    assert [(round(r, 3), round(d, 2)) for r, d in got_dev] == \
        [(round(r, 3), round(d, 2)) for r, d in EXP_DEV], got_dev
    assert (y4["R"], y4["DD"]) == EXP_Y4, (y4["R"], y4["DD"])
    assert geo5 == EXP_5Y, geo5
    assert full == EXP_FULL, full
    print("G2 reproduction OK: 5.41 / 16.91 / 16.82 to the digit", flush=True)


if __name__ == "__main__":
    print("python version check", sys.version.split()[0], flush=True)
    main()
