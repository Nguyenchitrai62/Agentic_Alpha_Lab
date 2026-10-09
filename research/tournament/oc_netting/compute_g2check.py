"""oc_netting Stage 0 (LIGHT): reproduce G2 baseline from stored runs BEFORE any overlay/engine.

G2 = R2B1D17BFG2 in v421_runs.pkl / v421_result.json:
  5y R 5.410 / W 2.588 / max-yearly-DD 16.91 / full-path DD 16.82.
Asserts all four to the digit; else stops (PLAN §3).

  .venv/Scripts/python.exe research/tournament/oc_netting/compute_g2check.py
LIGHT: one process, no 1m, stored runs only.
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
V421_RES = RD / "v421/v421_result.json"
STRAT = "R2B1D17BFG2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    rm = _load("reset_for_netg2", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_for_netg2", RD / "v388/v388_bot_stop_distance.py")
    runs = pickle.loads(STORED.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    assert STRAT in runs[0], list(runs[0])
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]

    yy = [rm.year_reset(runs, STRAT, y) for y in range(5)]
    R5 = round(float(np.prod([1 + y["R"] / 100 for y in yy]) ** (1 / 5) - 1) * 100, 3)
    W5 = min(y["R"] for y in yy)
    DD5 = max(y["DD"] for y in yy)
    print("per-year (R, DD):", [(y["R"], y["DD"]) for y in yy], flush=True)
    print(f"R5={R5} W5={W5} DD5={DD5}", flush=True)

    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, STRAT, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    dd_c = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
    dd_m = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    full = max(dd_c, dd_m)
    print(f"full-path close={dd_c} marked={dd_m} gate={full}", flush=True)

    assert [y["R"] for y in yy] == [r for r, _ in exp["years"]], (yy, exp)
    assert [y["DD"] for y in yy] == [d for _, d in exp["years"]], (yy, exp)
    assert R5 == exp["R"] and W5 == exp["W"] and DD5 == exp["DD"], ((R5, W5, DD5), exp)
    assert full == exp["full_path_dd"], (full, exp)
    print("G2 reproduction OK: 5.41 / 16.91 / 16.82 to the digit", flush=True)
    (HERE / "tmp" / "g2check.json").write_text(json.dumps(dict(
        years=[(y["R"], y["DD"]) for y in yy], R=R5, W=W5, DD=DD5,
        full_path_dd=full, full_close=dd_c, full_marked=dd_m), indent=1))


if __name__ == "__main__":
    main()
