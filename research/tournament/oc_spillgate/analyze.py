"""oc_spillgate scoring: dev validation + dev4 table + robust pick (CPU-only).

Stage dev (tmp/runs_dev.pkl): REF must reproduce v421_result G2 years 0..3
(R and DD) EXACTLY, else STOP. Then dev4 table for REF/S1/S2/C1/C2 + robust
pick among S1/S2 on dev4 only + exposure-beats-control flags.
Writes tmp/dev_table.json.
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

ROWS = ["REF", "S1", "S2", "C1", "C2"]
EXP_REF_DEV = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v388 = _load("v388_an_sp", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_an_sp", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    assert all(set(dev[s].keys()) == set(ROWS) for s in range(4)), \
        {s: sorted(dev[s]) for s in range(4)}

    runs = {s: {"REF": dev[s]["REF"]["run"]} for s in range(4)}
    got = [rm.year_reset(runs, "REF", y) for y in range(4)]
    for y in range(4):
        assert (got[y]["R"], got[y]["DD"]) == (EXP_REF_DEV[y][0], EXP_REF_DEV[y][1]), \
            ("REF", y, (got[y]["R"], got[y]["DD"]), EXP_REF_DEV[y])
    print(f"REF reproduces v421 G2 dev years 0..3 EXACTLY: "
          f"{[(g['R'], g['DD']) for g in got]}", flush=True)

    table = {}
    for v in ROWS:
        runs = {s: {v: dev[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(runs, v, y) for y in range(4)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        geo = round(100 * (np.prod([1 + r / 100 for r in Rs]) ** (1 / 4) - 1), 3)
        g1 = pd.Timestamp("2025-09-24 12:00", tz="UTC")
        e, mn = v388.mix(runs, v, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fdd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        wins = []
        for y in range(4):
            nb = sum(dev[s][v]["wins"][y]["nb"] for s in range(4))
            wb = sum(dev[s][v]["wins"][y]["wb"] for s in range(4))
            nr = sum(dev[s][v]["wins"][y]["nr"] for s in range(4))
            wr = sum(dev[s][v]["wins"][y]["wr"] for s in range(4))
            wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                             book_win=round(wb / nb, 4) if nb else None,
                             rung_win=round(wr / nr, 4) if nr else None,
                             all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
        gs1, gs2 = [], []
        for y in range(4):
            a = [dev[s][v]["mult"][str(y)]["gated_share_s1"] for s in range(4)
                 if dev[s][v]["mult"][str(y)]["gated_share_s1"] is not None]
            b = [dev[s][v]["mult"][str(y)]["gated_share_s2"] for s in range(4)
                 if dev[s][v]["mult"][str(y)]["gated_share_s2"] is not None]
            gs1.append(round(float(np.mean(a)), 6) if a else None)
            gs2.append(round(float(np.mean(b)), 6) if b else None)
        t = dict(years_R=Rs, years_DD=DDs, Rdev4=geo, Wdev4=round(min(Rs), 3),
                 DDdev4=round(max(DDs), 2), fullDDdev=fdd,
                 DDmax=round(max(max(DDs), fdd), 2),
                 losing=sum(r < 0 for r in Rs), wins=wins,
                 gated_s1=gs1, gated_s2=gs2)
        table[v] = t
        print(f"{v}: Rdev4={geo} W={t['Wdev4']} DDmax_year={t['DDdev4']} fullDD={fdd} "
              f"losing={t['losing']} gs1={gs1} gs2={gs2}", flush=True)
        print(f"   years R={Rs} DD={DDs}", flush=True)
        print(f"   all_win={[w['all_win'] for w in wins]} book_win={[w['book_win'] for w in wins]}",
              flush=True)

    cands = {k: table[k] for k in ("S1", "S2")
             if table[k]["DDmax"] <= 20 and table[k]["losing"] == 0}
    if cands:
        hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
        pool = hot or cands
        pick = max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))
    else:
        pick = "none-eligible"
    beats = {}
    for s, c in (("S1", "C1"), ("S2", "C2")):
        beats[s] = bool(table[s]["Rdev4"] > table[c]["Rdev4"]
                        and table[s]["DDmax"] <= table[c]["DDmax"])
    print("PICK on dev4 only (S1/S2):", pick, flush=True)
    print("beats-control:", beats, flush=True)
    (HERE / "tmp/dev_table.json").write_text(json.dumps(
        {"table": table, "pick": pick, "beats_control": beats}, indent=1))
    print("saved tmp/dev_table.json", flush=True)


if __name__ == "__main__":
    main()
