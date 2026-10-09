"""oc_voltilt scoring: dev validation + dev4 table + last-year ONCE (all three rows).

Stage dev (tmp/runs_dev.pkl): REF must reproduce v421_result G2 years 0..3
(R and DD) EXACTLY, else STOP. Then dev4 table + robust pick
(REF vs V_RV6 vs V_GARCH) on dev4 only.
Stage last (tmp/runs_last.pkl, full window [DEV0, Y1)): determinism check
(dev segments equal stage-1); all three rows scored ONCE; REF Y4 must equal
v421 G2 Y4 to the digit; full-path DD via v388.mix.
CPU-only.
"""
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

ROWS = ["REF", "V_RV6", "V_GARCH"]
EXP_REF_DEV = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
EXP_REF_Y4 = (4.648, 12.90)
EXP_REF_FULLDD = 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def full_dd(v388, runs, v):
    g1 = pd.Timestamp("2025-09-24 12:00", tz="UTC")
    e, mn = v388.mix(runs, v, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    return round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)


def main():
    v388 = _load("v388_analyze_vt", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_analyze_vt", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    dev = pickle.loads((HERE / "tmp/runs_dev.pkl").read_bytes())
    assert all(set(dev[s].keys()) == set(ROWS) for s in range(4)), \
        {s: sorted(dev[s]) for s in range(4)}

    # ---- reproduction gate: REF vs v421 G2 ----
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
        fdd = full_dd(v388, runs, v)
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
        t = dict(years_R=Rs, years_DD=DDs, Rdev4=geo, Wdev4=round(min(Rs), 3),
                 DDdev4=round(max(DDs), 2), fullDDdev=fdd,
                 DDmax=round(max(max(DDs), fdd), 2),
                 losing=sum(r < 0 for r in Rs), wins=wins)
        table[v] = t
        print(f"{v}: Rdev4={geo} W={t['Wdev4']} DDmax_year={t['DDdev4']} fullDD={fdd} "
              f"losing={t['losing']}", flush=True)
        print(f"   years R={Rs} DD={DDs}", flush=True)
        print(f"   all_win={[w['all_win'] for w in wins]} fills_rung={[w['nr'] for w in wins]} "
              f"book={[w['nb'] for w in wins]}", flush=True)

    cands = {k: table[k] for k in ("REF", "V_RV6", "V_GARCH")
             if table[k]["DDmax"] <= 20 and table[k]["losing"] == 0}
    if cands:
        hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
        pool = hot or cands
        pick = max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))
    else:
        pick = "none-eligible"
    print("PICK on dev4 only:", pick, flush=True)
    (HERE / "tmp/dev_table.json").write_text(json.dumps(
        {"table": table, "pick": pick}, indent=1))
    print("saved tmp/dev_table.json", flush=True)

    # ---- stage last: all three rows scored ONCE ----
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    assert all(set(last[s].keys()) == set(ROWS) for s in range(4)), \
        {s: sorted(last[s]) for s in range(4)}
    for v in ROWS:
        runs2 = {s: {v: last[s][v]["run"]} for s in range(4)}
        for y in range(4):
            a = rm.year_reset(runs2, v, y)
            assert (a["R"], a["DD"]) == (table[v]["years_R"][y], table[v]["years_DD"][y]), \
                (v, y, (a["R"], a["DD"]))
    print("determinism OK: stage-last dev segments equal stage-dev", flush=True)

    out = {}
    for v in ROWS:
        src = {s: {v: last[s][v]["run"]} for s in range(4)}
        y4 = rm.year_reset(src, v, 4)
        e, mn = v388.mix(src, v, v388.Y1 + pd.Timedelta(hours=12))
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fdd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        nb = sum(last[s][v]["wins"][4]["nb"] for s in range(4))
        wb = sum(last[s][v]["wins"][4]["wb"] for s in range(4))
        nr = sum(last[s][v]["wins"][4]["nr"] for s in range(4))
        wr = sum(last[s][v]["wins"][4]["wr"] for s in range(4))
        out[v] = dict(Rlast=y4["R"], DDlast=y4["DD"], full_path_dd=fdd,
                      book_trades=nb, book_win=round(wb / nb, 4) if nb else None,
                      rung_trades=nr, rung_win=round(wr / nr, 4) if nr else None,
                      all_win=round((wb + wr) / (nb + nr), 4) if (nb and nr) else None)
        print(v, out[v], flush=True)

    assert (out["REF"]["Rlast"], out["REF"]["DDlast"]) == EXP_REF_Y4, out["REF"]
    assert out["REF"]["full_path_dd"] == EXP_REF_FULLDD, out["REF"]
    print("REF last-year reproduces v421 G2 Y4 EXACTLY", flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(out, indent=1))
    print("saved tmp/last_table.json", flush=True)


if __name__ == "__main__":
    main()
