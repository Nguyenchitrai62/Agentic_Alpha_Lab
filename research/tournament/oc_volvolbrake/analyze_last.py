"""oc_volvolbrake stage-last scoring (CPU-only, scored ONCE).

Loads tmp/runs_last.pkl for REF + dev4 pick + its matched control ONLY.
Validates REF Y4 reproduces v421 G2 Y4 to the digit, then builds 5y geo means
and full-path DD via v388.mix. Writes tmp/last_table.json.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
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
    v388 = _load("v388_an_vvl", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_an_vvl", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = json.loads((HERE / "tmp/dev_table.json").read_text())
    pick = dev["pick"]
    if pick == "none-eligible":
        rows = ["REF"]
    else:
        ctrl = "C1" if pick == "V1" else "C2"
        rows = ["REF", pick, ctrl]
    print("last-stage rows (scored ONCE):", rows, flush=True)
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(rows) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}

    runs_ref = {s: {"REF": last[s]["REF"]["run"]} for s in range(4)}
    y4 = rm.year_reset(runs_ref, "REF", 4)
    assert (y4["R"], y4["DD"]) == EXP_Y4, (y4["R"], y4["DD"])
    print(f"REF Y4 reproduces v421 G2 EXACTLY: {(y4['R'], y4['DD'])}", flush=True)

    table = {}
    for v in rows:
        runs = {s: {v: last[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(runs, v, y) for y in range(5)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        geo5 = round(100 * (np.prod([1 + r / 100 for r in Rs]) ** (1 / 5) - 1), 3)
        geo4 = round(100 * (np.prod([1 + r / 100 for r in Rs[:4]]) ** (1 / 4) - 1), 3)
        g1 = v388.Y1 + pd.Timedelta(hours=12)
        e, mn = v388.mix(runs, v, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fdd_m = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        fdd_c = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
        wins = []
        for y in range(5):
            nb = sum(last[s][v]["wins"][y]["nb"] for s in range(4))
            wb = sum(last[s][v]["wins"][y]["wb"] for s in range(4))
            nr = sum(last[s][v]["wins"][y]["nr"] for s in range(4))
            wr = sum(last[s][v]["wins"][y]["wr"] for s in range(4))
            wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                             book_win=round(wb / nb, 4) if nb else None,
                             all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
        table[v] = dict(years_R=Rs, years_DD=DDs, R5y=geo5, Rdev4=geo4,
                        W5y=round(min(Rs), 3), DD5y=round(max(DDs), 2),
                        full_marked=fdd_m, full_close=fdd_c,
                        full=max(fdd_m, fdd_c), wins=wins)
        print(f"{v}: 5y={geo5} Y4={(Rs[4], DDs[4])} full={max(fdd_m, fdd_c)}", flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(
        {"rows": rows, "pick": pick, "table": table}, indent=1))
    print("saved tmp/last_table.json", flush=True)


if __name__ == "__main__":
    main()
