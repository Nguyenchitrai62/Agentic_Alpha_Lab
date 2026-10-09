"""oc_booktrim scoring (CPU-only): dev4 / pick / Y4-once / 5y + full-path DD + decomposition.

Reads tmp/runs_dev_<fric>.pkl (REF/BT08/BT06 dev-window runs) and
tmp/runs_last_<fric>.pkl (pick + REF full-window runs), scores with
reset_metric.year_reset + v388.mix, checks the reproduction gates
(REF_base dev == v421 G2 years 0..3 to the digit; REF_base full == 5y/full-DD;
REF_S5 == oc_c2bybit REF_S5 to the digit), writes tmp/booktrim_table.json.
REPORT.md + results.json are written from that table only.
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
VARIANTS = ("REF", "BT08", "BT06")
FRICS = ("base", "S5")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def main():
    v388 = _load("v388_booktrim", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_booktrim", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    c2b = json.loads((C2B / "tmp/c2bybit_table.json").read_text())["table"]

    dev, last = {}, {}
    for fric in FRICS:
        p = TMP / f"runs_dev_{fric}.pkl"
        assert p.exists(), f"missing cache {p} — run compute_booktrim_engine.py --stage dev first"
        dev[fric] = pickle.loads(p.read_bytes())
        assert set(dev[fric]) == {0, 1, 2, 3}, (fric, sorted(dev[fric]))
        for s in range(4):
            assert set(dev[fric][s]) == set(VARIANTS), (fric, s, sorted(dev[fric][s]))
    for fric in FRICS:
        p = TMP / f"runs_last_{fric}.pkl"
        assert p.exists(), f"missing cache {p} — run compute_booktrim_engine.py --stage last first"
        last[fric] = pickle.loads(p.read_bytes())
        assert set(last[fric]) == {0, 1, 2, 3}, (fric, sorted(last[fric]))

    last_variants = sorted(last["base"][0].keys())
    assert set(last_variants) == set(last["S5"][0].keys()), last_variants
    assert set(last_variants) <= set(VARIANTS) and "REF" in last_variants, last_variants
    nonref = [v for v in last_variants if v != "REF"]
    assert len(nonref) <= 1, last_variants
    staged_pick = nonref[0] if nonref else "REF"  # pick==REF collapses to REF-only last stage

    def score_runs(runs, variants, nyears):
        """Per (variant): years R/DD via year_reset, dev4 stats, wins, decomp."""
        out = {}
        for v in variants:
            rr = {s: {v: runs[s][v]["run"]} for s in range(4)}
            yrs = [rm.year_reset(rr, v, y) for y in range(nyears)]
            Rs = [y["R"] for y in yrs]
            DDs = [y["DD"] for y in yrs]
            devRs = Rs[:4]
            e, mn = v388.mix(rr, v, g1)
            seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
            es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
            fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
            wins = []
            for y in range(len(Rs)):
                nb = sum(runs[s][v]["wins"][y]["nb"] for s in range(4))
                wb = sum(runs[s][v]["wins"][y]["wb"] for s in range(4))
                nr = sum(runs[s][v]["wins"][y]["nr"] for s in range(4))
                wr = sum(runs[s][v]["wins"][y]["wr"] for s in range(4))
                wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                                 book_win=round(wb / nb, 4) if nb else None,
                                 rung_win=round(wr / nr, 4) if nr else None,
                                 all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
            dc = dict(book=[0.0] * 5, dip=[0.0] * 5, fills=[0] * 5,
                      wsum=[0.0] * 5, near=[0] * 5, over=[0] * 5,
                      maxconc=[0.0] * 4, rungs=[0] * 4)
            for s in range(4):
                d = runs[s][v]["decomp"]
                for y in range(5):
                    dc["book"][y] += d["book"][y] / 4
                    dc["dip"][y] += d["dip"][y] / 4
                    dc["fills"][y] += d["fills"][y]
                    dc["wsum"][y] += d["wsum"][y]
                    dc["near"][y] += d["near"][y]
                    dc["over"][y] += d["over"][y]
                dc["maxconc"][s] = d["max_concurrent"]
                dc["rungs"][s] = d["rungs"]
            dc["wmean"] = [round(dc["wsum"][y] / dc["fills"][y], 6) if dc["fills"][y] else None
                           for y in range(5)]
            tot_b = sum(dc["book"][:4])
            tot_d = sum(dc["dip"][:4])
            dc["book_share_dev4"] = (round(tot_b / (tot_b + tot_d), 4)
                                     if (tot_b + tot_d) > 0 else None)
            out[v] = dict(years_R=Rs, years_DD=DDs,
                          Rdev4=geo(devRs), Wdev4=round(min(devRs), 3),
                          DDdev4=round(max(DDs[:4]), 2),
                          losing_dev4=sum(r < 0 for r in devRs),
                          R5y=geo(Rs) if len(Rs) == 5 else None,
                          W5y=round(min(Rs), 3) if len(Rs) == 5 else None,
                          DD5y=round(max(DDs), 2) if len(Rs) == 5 else None,
                          losing_5y=sum(r < 0 for r in Rs) if len(Rs) == 5 else None,
                          full_path_dd=fulldd,
                          DDmax_full=round(max(max(DDs), fulldd), 2),
                          wins=wins, decomp=dc)
        return out

    devT = {f: score_runs(dev[f], VARIANTS, 4) for f in FRICS}
    lastT = {f: score_runs(last[f], last_variants, 5) for f in FRICS}

    # ---- reproduction gate 1: REF_base dev == v421 G2 years 0..3 to the digit ----
    for y in range(4):
        er, ed = exp["years"][y]
        assert devT["base"]["REF"]["years_R"][y] == er, (y, devT["base"]["REF"]["years_R"][y], er)
        assert devT["base"]["REF"]["years_DD"][y] == ed, (y, devT["base"]["REF"]["years_DD"][y], ed)
    print("REF_base dev reproduces v421 G2 years 0..3 EXACTLY", flush=True)
    # ---- gate 2: REF_base full-window 5y + full-path DD ----
    assert lastT["base"]["REF"]["R5y"] == exp["R"], (lastT["base"]["REF"]["R5y"], exp["R"])
    for y in range(5):
        er, ed = exp["years"][y]
        assert lastT["base"]["REF"]["years_R"][y] == er, (y, lastT["base"]["REF"]["years_R"][y], er)
        assert lastT["base"]["REF"]["years_DD"][y] == ed, (y, lastT["base"]["REF"]["years_DD"][y], ed)
    assert lastT["base"]["REF"]["full_path_dd"] == exp["full_path_dd"], lastT["base"]["REF"]
    print("REF_base full reproduces v421 G2 5y + full-path DD EXACTLY", flush=True)
    # ---- gate 3: REF_S5 == oc_c2bybit REF_S5 to the digit ----
    for y in range(5):
        assert lastT["S5"]["REF"]["years_R"][y] == c2b["REF_S5"]["years_R"][y], (y, "R")
        assert lastT["S5"]["REF"]["years_DD"][y] == c2b["REF_S5"]["years_DD"][y], (y, "DD")
    assert lastT["S5"]["REF"]["R5y"] == c2b["REF_S5"]["R5y"]
    assert lastT["S5"]["REF"]["full_path_dd"] == c2b["REF_S5"]["full_path_dd"]
    print("REF_S5 reproduces oc_c2bybit REF_S5 EXACTLY", flush=True)
    # ---- gate 4: dev REF_S5 year 0..3 == last REF_S5 year 0..3 (stage consistency) ----
    for y in range(4):
        assert devT["S5"]["REF"]["years_R"][y] == lastT["S5"]["REF"]["years_R"][y], (y, "R")
        assert devT["S5"]["REF"]["years_DD"][y] == lastT["S5"]["REF"]["years_DD"][y], (y, "DD")
    for y in range(4):
        assert devT["base"]["REF"]["years_R"][y] == lastT["base"]["REF"]["years_R"][y], (y, "R")
    print("dev/last stage consistency for REF OK", flush=True)

    # ---- robust pick on dev4 Binance base ONLY ----
    def eligible(m):
        return m["DDdev4"] <= 20 and m["losing_dev4"] == 0

    cands = {v: devT["base"][v] for v in VARIANTS}
    elig = [v for v in VARIANTS if eligible(cands[v])]
    over5 = [v for v in elig if cands[v]["Rdev4"] >= 5]
    pool = over5 or elig
    if pool:
        pick_calc = max(pool, key=lambda v: (cands[v]["Wdev4"], cands[v]["Rdev4"]))
    else:
        pick_calc = max(VARIANTS, key=lambda v: (cands[v]["Rdev4"],))
    print("robust pick on dev4 base:", pick_calc, {v: (cands[v]["Rdev4"], cands[v]["Wdev4"], cands[v]["DDdev4"], cands[v]["losing_dev4"]) for v in VARIANTS}, flush=True)
    assert staged_pick == pick_calc, (staged_pick, pick_calc)
    pick = pick_calc

    (TMP / "booktrim_table.json").write_text(json.dumps(
        {"dev": devT, "last": lastT, "pick": pick,
         "ref_gate": {"years": exp["years"], "R": exp["R"], "DD": exp["DD"],
                      "full_path_dd": exp["full_path_dd"]}}, indent=1))
    print("saved tmp/booktrim_table.json, pick =", pick, flush=True)


if __name__ == "__main__":
    main()
