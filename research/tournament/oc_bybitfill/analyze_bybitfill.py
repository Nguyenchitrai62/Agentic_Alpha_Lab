"""oc_bybitfill scoring (CPU-only): dev4 / Y4-diagnostic / 5y + full-path DD + fills.

Reads tmp/runs_<ROW>.pkl (REF/TPm3/RUNp3 x base/S5 full-window runs, 4 phases),
scores with reset_metric.year_reset + v388.mix, checks the reproduction gates
(REF_base == v421 G2 to the digit; REF_S5 == oc_c2bybit REF_S5 to the digit),
writes tmp/bybitfill_table.json. REPORT.md + results.json are written from that
table only.
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
TMP = HERE / "tmp"
C2B = ROOT / "research/tournament/oc_c2bybit"
ROWS = ("REF_base", "TPm3_base", "RUNp3_base", "REF_S5", "TPm3_S5", "RUNp3_S5")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), 3)


def main():
    v388 = _load("v388_bybitfill", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_bybitfill", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    c2 = json.loads((C2B / "tmp/c2bybit_table.json").read_text())["table"]

    runs = {}
    for row in ROWS:
        p = TMP / f"runs_{row}.pkl"
        assert p.exists(), f"missing cache {p} - run compute_bybitfill_engine.py first"
        runs[row] = pickle.loads(p.read_bytes())
        assert set(runs[row]) == {0, 1, 2, 3}, (row, sorted(runs[row]))
        for s in range(4):
            assert row in runs[row][s], (row, s, sorted(runs[row][s]))

    table = {}
    for row in ROWS:
        rr = {s: {row: runs[row][s][row]["run"]} for s in range(4)}
        yrs = [rm.year_reset(rr, row, y) for y in range(5)]
        Rs = [y["R"] for y in yrs]
        DDs = [y["DD"] for y in yrs]
        dev = Rs[:4]
        e, mn = v388.mix(rr, row, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
        wins, fills = [], []
        for y in range(5):
            nb = sum(runs[row][s][row]["wins"][y]["nb"] for s in range(4))
            wb = sum(runs[row][s][row]["wins"][y]["wb"] for s in range(4))
            nr = sum(runs[row][s][row]["wins"][y]["nr"] for s in range(4))
            wr = sum(runs[row][s][row]["wins"][y]["wr"] for s in range(4))
            ntp = sum(runs[row][s][row]["wins"][y].get("ntp", 0) for s in range(4))
            nsl = sum(runs[row][s][row]["wins"][y].get("nsl", 0) for s in range(4))
            nto = sum(runs[row][s][row]["wins"][y].get("nto", 0) for s in range(4))
            wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                             book_win=round(wb / nb, 4) if nb else None,
                             rung_win=round(wr / nr, 4) if nr else None,
                             all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
            fills.append(dict(rung_fill=nr, rung_tp=ntp, rung_sl=nsl, rung_timeout=nto,
                              tp_rate=round(ntp / nr, 4) if nr else None))
        table[row] = dict(years_R=Rs, years_DD=DDs,
                          Rdev4=geo(dev), Wdev4=round(min(dev), 3),
                          DDdev4=round(max(DDs[:4]), 2),
                          losing_dev4=sum(r < 0 for r in dev),
                          R5y=geo(Rs), W5y=round(min(Rs), 3),
                          DD5y=round(max(DDs), 2),
                          losing_5y=sum(r < 0 for r in Rs),
                          full_path_dd=fulldd,
                          DDmax_full=round(max(max(DDs), fulldd), 2),
                          wins=wins, fills=fills)

    # ---- reproduction gate 1: REF_base == v421 G2 to the digit ----
    for y in range(5):
        er, ed = exp["years"][y]
        assert table["REF_base"]["years_R"][y] == er, (y, table["REF_base"]["years_R"][y], er)
        assert table["REF_base"]["years_DD"][y] == ed, (y, table["REF_base"]["years_DD"][y], ed)
    assert table["REF_base"]["R5y"] == exp["R"], (table["REF_base"]["R5y"], exp["R"])
    assert table["REF_base"]["DD5y"] == exp["DD"], table["REF_base"]["DD5y"]
    assert table["REF_base"]["full_path_dd"] == exp["full_path_dd"], table["REF_base"]
    print("REF_base reproduces v421 G2 EXACTLY:", table["REF_base"]["years_R"],
          "full", table["REF_base"]["full_path_dd"], flush=True)

    # ---- reproduction gate 2: REF_S5 == oc_c2bybit REF_S5 to the digit ----
    for y in range(5):
        assert table["REF_S5"]["years_R"][y] == c2["REF_S5"]["years_R"][y], \
            (y, table["REF_S5"]["years_R"][y], c2["REF_S5"]["years_R"][y])
        assert table["REF_S5"]["years_DD"][y] == c2["REF_S5"]["years_DD"][y], \
            (y, table["REF_S5"]["years_DD"][y], c2["REF_S5"]["years_DD"][y])
    assert table["REF_S5"]["Rdev4"] == c2["REF_S5"]["Rdev4"], table["REF_S5"]["Rdev4"]
    assert table["REF_S5"]["R5y"] == c2["REF_S5"]["R5y"], table["REF_S5"]["R5y"]
    assert table["REF_S5"]["full_path_dd"] == c2["REF_S5"]["full_path_dd"], table["REF_S5"]
    print("REF_S5 reproduces oc_c2bybit REF_S5 EXACTLY:", table["REF_S5"]["years_R"],
          "full", table["REF_S5"]["full_path_dd"], flush=True)

    gaps = {}
    for fric in ("base", "S5"):
        for v in ("TPm3", "RUNp3"):
            gaps[f"{v}_{fric}"] = dict(
                dev4=round(table[f"{v}_{fric}"]["Rdev4"] - table[f"REF_{fric}"]["Rdev4"], 3),
                y4_diag=round(table[f"{v}_{fric}"]["years_R"][4] - table[f"REF_{fric}"]["years_R"][4], 3),
                y5=round(table[f"{v}_{fric}"]["R5y"] - table[f"REF_{fric}"]["R5y"], 3))
    # venue gap + recovery share (dev4 and 5y)
    gap_base_s5 = dict(dev4=round(table["REF_base"]["Rdev4"] - table["REF_S5"]["Rdev4"], 3),
                       y5=round(table["REF_base"]["R5y"] - table["REF_S5"]["R5y"], 3))
    rec = {}
    for v in ("TPm3", "RUNp3"):
        rec[v] = {}
        for w, key in (("dev4", "Rdev4"), ("y5", "R5y")):
            num = table[f"{v}_S5"][key] - table["REF_S5"][key]
            den = table["REF_base"][key] - table["REF_S5"][key]
            rec[v][w] = round(num / den, 3) if den else None
    (TMP / "bybitfill_table.json").write_text(json.dumps(
        {"table": table, "gaps": gaps, "gap_base_s5": gap_base_s5, "recovery_share": rec,
         "ref_gate": {"v421_years": exp["years"], "R": exp["R"], "DD": exp["DD"],
                      "full_path_dd": exp["full_path_dd"]}}, indent=1))
    print("gaps variant-REF:", gaps, flush=True)
    print("venue gap base-S5:", gap_base_s5, "recovery share:", rec, flush=True)
    print("saved tmp/bybitfill_table.json", flush=True)


if __name__ == "__main__":
    main()
