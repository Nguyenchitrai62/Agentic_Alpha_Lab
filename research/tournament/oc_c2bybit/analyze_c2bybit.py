"""oc_c2bybit scoring (CPU-only): dev4 / Y4-diagnostic / 5y + full-path DD.

Reads tmp/runs_<fric>.pkl (REF/C2 full-window runs per friction), scores with
reset_metric.year_reset + v388.mix, checks the reproduction gate (base REF ==
v421 G2 to the digit; base C2 == oc_chronos numbers to the digit), writes
tmp/c2bybit_table.json. REPORT.md + results.json are written from that table.
K2 side-by-side numbers are read from oc_k2bybit (never recomputed).
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
CH = ROOT / "research/tournament/oc_chronos"
K2B = ROOT / "research/tournament/oc_k2bybit"
FRICS = ("base", "S1", "S2", "S3", "S4", "S5")
VARIANTS = ("REF", "C2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def main():
    v388 = _load("v388_c2bybit", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_c2bybit", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    ch_res = json.loads((CH / "results.json").read_text())

    runs = {}
    for fric in FRICS:
        p = TMP / f"runs_{fric}.pkl"
        assert p.exists(), f"missing cache {p} — run compute_c2bybit_engine.py first"
        runs[fric] = pickle.loads(p.read_bytes())
        assert set(runs[fric]) == {0, 1, 2, 3}, (fric, sorted(runs[fric]))
        for s in range(4):
            assert set(runs[fric][s]) == set(VARIANTS), (fric, s, sorted(runs[fric][s]))

    table = {}
    for fric in FRICS:
        for v in VARIANTS:
            key = f"{v}_{fric}"
            rr = {s: {key: runs[fric][s][v]["run"]} for s in range(4)}
            yrs = [rm.year_reset(rr, key, y) for y in range(5)]
            Rs = [y["R"] for y in yrs]
            DDs = [y["DD"] for y in yrs]
            dev = Rs[:4]
            e, mn = v388.mix(rr, key, g1)
            seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
            es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
            fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
            wins = []
            for y in range(5):
                nb = sum(runs[fric][s][v]["wins"][y]["nb"] for s in range(4))
                wb = sum(runs[fric][s][v]["wins"][y]["wb"] for s in range(4))
                nr = sum(runs[fric][s][v]["wins"][y]["nr"] for s in range(4))
                wr = sum(runs[fric][s][v]["wins"][y]["wr"] for s in range(4))
                wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                                 book_win=round(wb / nb, 4) if nb else None,
                                 rung_win=round(wr / nr, 4) if nr else None,
                                 all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
            table[key] = dict(years_R=Rs, years_DD=DDs,
                              Rdev4=geo(dev), Wdev4=round(min(dev), 3),
                              DDdev4=round(max(DDs[:4]), 2),
                              losing_dev4=sum(r < 0 for r in dev),
                              R5y=geo(Rs), W5y=round(min(Rs), 3),
                              DD5y=round(max(DDs), 2),
                              losing_5y=sum(r < 0 for r in Rs),
                              full_path_dd=fulldd,
                              DDmax_full=round(max(max(DDs), fulldd), 2),
                              wins=wins)

    # ---- reproduction gate: base REF == v421 G2 to the digit ----
    for y in range(5):
        er, ed = exp["years"][y]
        assert table["REF_base"]["years_R"][y] == er, (y, table["REF_base"]["years_R"][y], er)
        assert table["REF_base"]["years_DD"][y] == ed, (y, table["REF_base"]["years_DD"][y], ed)
    assert table["REF_base"]["R5y"] == exp["R"], (table["REF_base"]["R5y"], exp["R"])
    assert table["REF_base"]["DD5y"] == exp["DD"], table["REF_base"]["DD5y"]
    assert table["REF_base"]["full_path_dd"] == exp["full_path_dd"], table["REF_base"]
    print("REF_base reproduces v421 G2 EXACTLY:", table["REF_base"]["years_R"],
          "full", table["REF_base"]["full_path_dd"], flush=True)

    # ---- reproduction gate: base C2 == oc_chronos to the digit ----
    ch_dev_R = ch_res["dev"]["C2"]["r"]
    ch_dev_DD = ch_res["dev"]["C2"]["dd"]
    ch_last_R = ch_res["last_year_scored_once"]["C2"]["Rlast"]
    ch_last_DD = ch_res["last_year_scored_once"]["C2"]["DDlast"]
    ch_full = ch_res["last_year_scored_once"]["C2"]["full_path_dd"]
    for y in range(4):
        assert table["C2_base"]["years_R"][y] == ch_dev_R[y], (y, table["C2_base"]["years_R"][y], ch_dev_R[y])
        assert table["C2_base"]["years_DD"][y] == ch_dev_DD[y], (y, table["C2_base"]["years_DD"][y], ch_dev_DD[y])
    assert table["C2_base"]["years_R"][4] == ch_last_R, (table["C2_base"]["years_R"][4], ch_last_R)
    assert table["C2_base"]["years_DD"][4] == ch_last_DD, (table["C2_base"]["years_DD"][4], ch_last_DD)
    assert table["C2_base"]["full_path_dd"] == ch_full, table["C2_base"]
    print("C2_base reproduces oc_chronos C2 EXACTLY:", table["C2_base"]["years_R"],
          "full", table["C2_base"]["full_path_dd"], flush=True)

    gaps = {}
    for fric in FRICS:
        gaps[fric] = dict(dev4=round(table[f"C2_{fric}"]["Rdev4"] - table[f"REF_{fric}"]["Rdev4"], 3),
                          y4_diag=round(table[f"C2_{fric}"]["years_R"][4] - table[f"REF_{fric}"]["years_R"][4], 3),
                          y5=round(table[f"C2_{fric}"]["R5y"] - table[f"REF_{fric}"]["R5y"], 3))
    (TMP / "c2bybit_table.json").write_text(json.dumps(
        {"table": table, "gaps": gaps,
         "ref_gate": {"years": exp["years"], "R": exp["R"], "DD": exp["DD"],
                      "full_path_dd": exp["full_path_dd"]}}, indent=1))
    print("gaps C2-REF:", gaps, flush=True)
    print("saved tmp/c2bybit_table.json", flush=True)


if __name__ == "__main__":
    main()
