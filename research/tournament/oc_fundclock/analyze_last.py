"""oc_fundclock stage-last scoring (CPU-only, run ONCE).

Loads tmp/runs_last.pkl (REF + dev4 pick), asserts REF Y4 reproduces v421 G2
Y4 (4.648/12.90) exactly, then 5y means + full-path DD + wins.
Writes tmp/last_table.json.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
EXP_Y4 = (4.648, 12.90)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    pick = json.loads((HERE / "tmp/dev_table.json").read_text())["pick"]
    rows = ["REF"] if pick == "none-eligible" else ["REF", pick]
    print("last rows:", rows, flush=True)
    v388 = _load("v388_an_fcl", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_an_fcl", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(rows) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}
    table = {}
    for v in rows:
        runs = {s: {v: last[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(runs, v, y) for y in range(5)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        assert (yrs[4]["R"], yrs[4]["DD"]) == EXP_Y4 if v == "REF" else True, \
            (v, yrs[4])
        geo5 = round(100 * (np.prod([1 + r / 100 for r in Rs]) ** (1 / 5) - 1), 3)
        geo4 = round(100 * (np.prod([1 + r / 100 for r in Rs[:4]]) ** (1 / 4) - 1), 3)
        g1 = v388.Y1 + pd.Timedelta(hours=12)
        e, mn = v388.mix(runs, v, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fdd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        wins = []
        for y in range(5):
            nb = sum(last[s][v]["wins"][y]["nb"] for s in range(4))
            wb = sum(last[s][v]["wins"][y]["wb"] for s in range(4))
            nr = sum(last[s][v]["wins"][y]["nr"] for s in range(4))
            wr = sum(last[s][v]["wins"][y]["wr"] for s in range(4))
            wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                             book_win=round(wb / nb, 4) if nb else None,
                             rung_win=round(wr / nr, 4) if nr else None,
                             all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
        table[v] = dict(years_R=Rs, years_DD=DDs, R5y=geo5, Rdev4=geo4,
                        W5y=round(min(Rs), 3), DDmax_y=round(max(DDs), 2),
                        fullDD=fdd, DDmax=round(max(max(DDs), fdd), 2),
                        losing=sum(r < 0 for r in Rs), wins=wins)
        print(f"{v}: 5y={geo5} W5={table[v]['W5y']} DDmax={table[v]['DDmax']} "
              f"Y4=({Rs[4]}/{DDs[4]})", flush=True)
    if "REF" in table:
        print(f"REF Y4 reproduces G2 {EXP_Y4} EXACTLY", flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(
        {"table": table, "pick": pick}, indent=1))
    print("saved tmp/last_table.json", flush=True)


if __name__ == "__main__":
    main()
