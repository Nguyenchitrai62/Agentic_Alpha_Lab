"""oc_btcresid last-year scoring ONCE (CPU-only).

Reads tmp/dev_table.json for the frozen dev4 pick, scores REF + pick + its
matched control on stage-last runs (tmp/runs_last.pkl): per-year reset rows
for years 0..4, 5y geo mean, full-path DD. Every Y4 number is labelled
scored-once. REF Y4 must reproduce v421 G2 Y4 to the digit.
Writes tmp/last_table.json.
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

EXP_REF_Y4 = (4.648, 12.90)
EXP_REF_FULLDD = 16.82


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    dev = json.loads((HERE / "tmp/dev_table.json").read_text())
    pick = dev["pick"]
    ctl = {"V1": "C1", "V2": "C2"}.get(pick)
    rows = ["REF"] if pick == "none-eligible" else ["REF", pick, ctl]
    print("last-year rows (ONCE):", rows, flush=True)
    v388 = _load("v388_an_brl", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_an_brl", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    last = pickle.loads((HERE / "tmp/runs_last.pkl").read_bytes())
    for s in range(4):
        missing = [v for v in rows if v not in last.get(s, {})]
        assert not missing, (s, sorted(last.get(s, {})), rows)

    table = {}
    for v in rows:
        runs = {s: {v: last[s][v]["run"]} for s in range(4)}
        yrs = [rm.year_reset(runs, v, y) for y in range(5)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        geo5 = round(100 * (np.prod([1 + r / 100 for r in Rs]) ** (1 / 5) - 1), 3)
        e, mn = v388.mix(runs, v, v388.Y1 + pd.Timedelta(hours=12))
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        dd_m = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        dd_c = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
        wins = []
        for y in range(5):
            nb = sum(last[s][v]["wins"][y]["nb"] for s in range(4))
            wb = sum(last[s][v]["wins"][y]["wb"] for s in range(4))
            nr = sum(last[s][v]["wins"][y]["nr"] for s in range(4))
            wr = sum(last[s][v]["wins"][y]["wr"] for s in range(4))
            wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                             book_win=round(wb / nb, 4) if nb else None,
                             all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
        table[v] = dict(years_R=Rs, years_DD=DDs, R5y=geo5,
                        W5y=round(min(Rs), 3), DDmax_year=round(max(DDs), 2),
                        full_path_dd=dict(marked=dd_m, close=dd_c, full=max(dd_m, dd_c)),
                        losing=sum(r < 0 for r in Rs), wins=wins,
                        fee_mean_shift=round(float(sum(
                            last[s][v].get("stats", {}).get("fees", 0.0)
                            for s in range(4)) / 4), 6),
                        funding_mean_shift=round(float(sum(
                            last[s][v].get("stats", {}).get("funding", 0.0)
                            for s in range(4)) / 4), 6))
        print(f"{v}: 5y={geo5} W5y={table[v]['W5y']} full={max(dd_m, dd_c)} "
              f"Y4=({Rs[4]}/{DDs[4]})", flush=True)
    assert (table["REF"]["years_R"][4], table["REF"]["years_DD"][4]) == EXP_REF_Y4, \
        table["REF"]
    assert table["REF"]["full_path_dd"]["full"] == EXP_REF_FULLDD, table["REF"]
    print("REF reproduces v421 G2 Y4 + full-path DD EXACTLY", flush=True)
    (HERE / "tmp/last_table.json").write_text(json.dumps(
        {"rows": rows, "pick": pick, "table": table}, indent=1))
    print("saved tmp/last_table.json", flush=True)


if __name__ == "__main__":
    main()
