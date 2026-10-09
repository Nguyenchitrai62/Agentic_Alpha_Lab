"""oc_c2frontier scoring (CPU-only): dev4 / Y4-once / 5y + full-path DD.

Reads tmp/runs_<CFG>_<FRIC>.pkl (new engine rows), scores with
reset_metric.year_reset + v388.mix, checks the reproduction gates
(D13BF_base == v424 R2B1D13BF to the digit; v421 G2 reproduced from stored runs),
quotes G2 / G2+C2 read-only from oc_chronos, writes tmp/frontier_table.json.
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
CH = ROOT / "research/tournament/oc_chronos"

NEW_KEYS = ("D13BF_base", "D13BF_C2_base", "G2K20_C2_base", "D13BF_S5", "D13BF_C2_S5")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), 3)


def score_runs(v388, rm, runs, key):
    """runs: {shift: {key: {run, wins}}}; returns per-year R/DD + aggregates + wins."""
    rr = {s: {key: runs[s][key]["run"]} for s in range(4)}
    yrs = [rm.year_reset(rr, key, y) for y in range(5)]
    Rs = [y["R"] for y in yrs]
    DDs = [y["DD"] for y in yrs]
    dev = Rs[:4]
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(rr, key, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    wins = []
    for y in range(5):
        nb = sum(runs[s][key]["wins"][y]["nb"] for s in range(4))
        wb = sum(runs[s][key]["wins"][y]["wb"] for s in range(4))
        nr = sum(runs[s][key]["wins"][y]["nr"] for s in range(4))
        wr = sum(runs[s][key]["wins"][y]["wr"] for s in range(4))
        wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                         book_win=round(wb / nb, 4) if nb else None,
                         rung_win=round(wr / nr, 4) if nr else None,
                         all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
    return dict(years_R=Rs, years_DD=DDs,
                Rdev4=geo(dev), Wdev4=round(min(dev), 3),
                DDdev4=round(max(DDs[:4]), 2),
                losing_dev4=sum(r < 0 for r in dev),
                R5y=geo(Rs), W5y=round(min(Rs), 3),
                DD5y=round(max(DDs), 2),
                losing_5y=sum(r < 0 for r in Rs),
                full_path_dd=fulldd,
                DDmax_full=round(max(max(DDs), fulldd), 2),
                wins=wins)


def main():
    v388 = _load("v388_cfront", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_cfront", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")

    # ---- gate 1: v421 G2 reproduced from stored runs (CPU, no engine) ----
    v421_runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    exp_g2 = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    rr_g2 = {s: {"G2": v421_runs[s]["R2B1D17BFG2"]} for s in range(4)}
    got_g2 = [rm.year_reset(rr_g2, "G2", y) for y in range(5)]
    for y in range(5):
        er, ed = exp_g2["years"][y]
        assert (got_g2[y]["R"], got_g2[y]["DD"]) == (er, ed), (y, got_g2[y], exp_g2["years"][y])
    print("G2 reproduces v421 R2B1D17BFG2 EXACTLY (stored runs):",
          [(g["R"], g["DD"]) for g in got_g2], flush=True)

    # ---- quoted rows (read-only, never rescored here) ----
    ch_res = json.loads((CH / "results.json").read_text())
    quoted = {
        "G2": dict(years_R=[2.588, 3.282, 6.045, 10.677, 4.648],
                   years_DD=[10.86, 16.91, 15.81, 8.27, 12.90],
                   Rdev4=5.601, Wdev4=2.588, DDdev4=16.91,
                   R5y=5.410, W5y=2.588, full_path_dd=16.82, src="oc_chronos REF == v421 G2"),
        "G2_C2": dict(years_R=[2.711, 3.460, 6.250, 10.721, 4.754],
                      years_DD=[11.52, 15.48, 15.07, 8.29, 12.86],
                      Rdev4=5.739, Wdev4=2.711, DDdev4=15.48,
                      R5y=5.542, W5y=2.711, full_path_dd=15.42, src="oc_chronos C2"),
    }
    assert ch_res["dev"]["C2"]["r"] == [2.711, 3.46, 6.25, 10.721]
    assert ch_res["last_year_scored_once"]["C2"]["Rlast"] == 4.754

    # ---- new engine rows ----
    runs = {}
    for key in NEW_KEYS:
        p = TMP / f"runs_{key}.pkl"
        assert p.exists(), f"missing cache {p} — run compute_frontier_engine.py first"
        runs[key] = pickle.loads(p.read_bytes())
        assert set(runs[key]) == {0, 1, 2, 3}, (key, sorted(runs[key]))

    table = {}
    for key in NEW_KEYS:
        cfg = key.rsplit("_", 1)[0] if key.endswith(("_base", "_S5")) else key
        # cache layout: {shift: {cfg: payload}}; key maps to cfg inside
        inner = {s: {key: runs[key][s][cfg]} for s in range(4)}
        table[key] = score_runs(v388, rm, {s: inner[s] for s in range(4)}, key)

    # ---- gate 2: D13BF_base == v424 R2B1D13BF to the digit ----
    exp_d13 = json.loads((RD / "v424/v424_result.json").read_text())["rows"]["R2B1D13BF"]
    for y in range(5):
        er, ed = exp_d13["years"][y]
        assert table["D13BF_base"]["years_R"][y] == er, (y, table["D13BF_base"]["years_R"][y], er)
        assert table["D13BF_base"]["years_DD"][y] == ed, (y, table["D13BF_base"]["years_DD"][y], ed)
    assert table["D13BF_base"]["R5y"] == exp_d13["R"], (table["D13BF_base"]["R5y"], exp_d13["R"])
    assert table["D13BF_base"]["full_path_dd"] == exp_d13["full_path_dd"], table["D13BF_base"]
    print("D13BF_base reproduces v424 R2B1D13BF EXACTLY:",
          table["D13BF_base"]["years_R"], "full", table["D13BF_base"]["full_path_dd"], flush=True)

    gaps = {
        "D13BF_C2_minus_D13BF_base": round(table["D13BF_C2_base"]["R5y"] - table["D13BF_base"]["R5y"], 3),
        "G2K20_C2_minus_G2_base": None,  # filled below vs quoted v422 below
    }
    exp_k20 = json.loads((RD / "v422/v422_result.json").read_text())["rows"]["G2K20"]
    gaps["G2K20_C2_minus_v422_G2K20_5y"] = round(table["G2K20_C2_base"]["R5y"] - exp_k20["R"], 3)

    (TMP / "frontier_table.json").write_text(json.dumps(
        {"new_rows": table, "quoted": quoted,
         "known_points": {"G2_v421": {"R5y": 5.41, "full": 16.82},
                           "D13BF_v424": {"R5y": 4.971, "full": 14.86},
                           "G2K20_v422": {"R5y": 5.874, "full": 17.69},
                           "v409_D15B08": {"R5y": 4.626, "full": 14.94},
                           "v423_X45": {"R5y": 5.118, "full": 15.81}},
         "gaps": gaps}, indent=1))
    print("gaps:", gaps, flush=True)
    print("saved tmp/frontier_table.json", flush=True)


if __name__ == "__main__":
    main()
