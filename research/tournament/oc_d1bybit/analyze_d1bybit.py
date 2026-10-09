"""oc_d1bybit scoring (CPU-only): dev4 / Y4-diagnostic / 5y + full-path DD + Spearman.

Reads tmp/runs_<fric>.pkl (REF/D1 full-window runs per friction), scores with
reset_metric.year_reset + v388.mix, checks the reproduction gate (base REF ==
v421 G2 to the digit; base D1 == oc_downshare numbers to the digit; REF_S* ==
oc_c2bybit REF_S* to the digit), computes per-year Spearman rho between frozen
D1 and C2 multipliers, writes tmp/d1bybit_table.json. REPORT.md + results.json
are written from that table. C2 side-by-side numbers are read from oc_c2bybit
(never recomputed).
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
TMP = HERE / "tmp"
DS = ROOT / "research/tournament/oc_downshare"
CH = ROOT / "research/tournament/oc_chronos"
C2B = ROOT / "research/tournament/oc_c2bybit"
FRICS = ("base", "S1", "S2", "S3", "S4", "S5")
VARIANTS = ("REF", "D1")
ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")

sys.path.insert(0, str(HERE))
from tilt_rule import assign_mult  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def _rank_avg(x):
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x), dtype=float)
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and x[order[j + 1]] == x[order[i]]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def spearman_rho(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ra, rb = _rank_avg(a), _rank_avg(b)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = float(np.sqrt((ra ** 2).sum() * (rb ** 2).sum()))
    if denom == 0:
        return float("nan")
    return float((ra * rb).sum() / denom)


def d1_c2_spearman():
    """Per-year Spearman rho between frozen D1 and C2 multipliers.

    Universe: intersection of frozen feature rows (majors, shifts 0..3, T in
    year y) with both risk_D1 and ch_q10 present. Mults via anchor-y fits only.
    """
    ds = pd.read_parquet(DS / "downshare_features_4shift.parquet",
                         columns=["sym", "shift", "T", "risk_D1"])
    ch = pd.read_parquet(CH / "chronos_features_4shift.parquet",
                         columns=["sym", "shift", "T", "ch_q10"])
    ds["T"] = pd.to_datetime(ds["T"], utc=True)
    ch["T"] = pd.to_datetime(ch["T"], utc=True)
    d1fits = json.loads((DS / "fits.json").read_text())["D1"]
    c2fits = json.loads((CH / "fits.json").read_text())
    out = []
    for y, a in enumerate(ANCH5):
        a0 = pd.Timestamp(a, tz="UTC")
        a1 = a0 + pd.Timedelta(days=365)
        d = ds[(ds["T"] >= a0) & (ds["T"] < a1)]
        c = ch[(ch["T"] >= a0) & (ch["T"] < a1)]
        m = d.merge(c, on=["sym", "shift", "T"], how="inner")
        m = m[np.isfinite(m["risk_D1"].to_numpy()) & np.isfinite(m["ch_q10"].to_numpy())]
        f1, f2 = d1fits[a], c2fits[a]
        m1 = np.array([assign_mult(r, f1["direction"], f1["q20"], f1["q80"], 1.25, 0.75)
                       for r in m["risk_D1"].to_numpy(dtype=float)])
        m2 = np.array([assign_mult(-q, f2["direction"], f2["q20"], f2["q80"], 1.25, 0.75)
                       for q in m["ch_q10"].to_numpy(dtype=float)])
        rho = spearman_rho(m1, m2)
        out.append(dict(year=a, n=int(len(m)), spearman=round(float(rho), 4)))
        print(f"spearman y={y} {a} n={len(m)} rho={rho:.4f}", flush=True)
        del d, c, m
    return out


def main():
    v388 = _load("v388_d1bybit", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_d1bybit", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    ds_dev = json.loads((DS / "tmp/dev_table.json").read_text())["table"]
    ds_last = json.loads((DS / "tmp/last_table.json").read_text())
    c2tab = json.loads((C2B / "tmp/c2bybit_table.json").read_text())

    runs = {}
    for fric in FRICS:
        p = TMP / f"runs_{fric}.pkl"
        assert p.exists(), f"missing cache {p} — run compute_d1bybit_engine.py first"
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
            sized = {}
            for y in range(5):
                ms_ = [runs[fric][s][v]["mult"][str(y)]["sized_mean"] for s in range(4)]
                ns = [runs[fric][s][v]["mult"][str(y)]["n_sized"] for s in range(4)]
                tot = sum(ns)
                sized[str(y)] = round(float(sum(m * n for m, n in zip(ms_, ns)) / tot), 6) if tot else None
            table[key] = dict(years_R=Rs, years_DD=DDs,
                              Rdev4=geo(dev), Wdev4=round(min(dev), 3),
                              DDdev4=round(max(DDs[:4]), 2),
                              losing_dev4=sum(r < 0 for r in dev),
                              R5y=geo(Rs), W5y=round(min(Rs), 3),
                              DD5y=round(max(DDs), 2),
                              losing_5y=sum(r < 0 for r in Rs),
                              full_path_dd=fulldd,
                              DDmax_full=round(max(max(DDs), fulldd), 2),
                              wins=wins, sized_mean=sized)

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

    # ---- reproduction gate: base D1 == oc_downshare to the digit ----
    exp_d1_dev_R = ds_dev["D1"]["years_R"]
    exp_d1_dev_DD = ds_dev["D1"]["years_DD"]
    exp_d1_last = ds_last["D1"]
    for y in range(4):
        assert table["D1_base"]["years_R"][y] == exp_d1_dev_R[y], (y, table["D1_base"]["years_R"][y], exp_d1_dev_R[y])
        assert table["D1_base"]["years_DD"][y] == exp_d1_dev_DD[y], (y, table["D1_base"]["years_DD"][y], exp_d1_dev_DD[y])
    assert table["D1_base"]["years_R"][4] == exp_d1_last["Rlast"], (table["D1_base"]["years_R"][4], exp_d1_last["Rlast"])
    assert table["D1_base"]["years_DD"][4] == exp_d1_last["DDlast"], (table["D1_base"]["years_DD"][4], exp_d1_last["DDlast"])
    assert table["D1_base"]["full_path_dd"] == exp_d1_last["full_path_dd"], table["D1_base"]
    print("D1_base reproduces oc_downshare D1 EXACTLY:", table["D1_base"]["years_R"],
          "full", table["D1_base"]["full_path_dd"], flush=True)

    # ---- friction REF consistency: our REF_S* == oc_c2bybit REF_S* to digit ----
    for fric in FRICS:
        for y in range(5):
            assert table[f"REF_{fric}"]["years_R"][y] == c2tab["table"][f"REF_{fric}"]["years_R"][y], \
                (fric, y, table[f"REF_{fric}"]["years_R"][y])
            assert table[f"REF_{fric}"]["years_DD"][y] == c2tab["table"][f"REF_{fric}"]["years_DD"][y], \
                (fric, y, table[f"REF_{fric}"]["years_DD"][y])
        assert table[f"REF_{fric}"]["full_path_dd"] == c2tab["table"][f"REF_{fric}"]["full_path_dd"], fric
    print("REF_S* match oc_c2bybit REF_S* EXACTLY (friction impl identical)", flush=True)

    gaps = {}
    for fric in FRICS:
        gaps[fric] = dict(dev4=round(table[f"D1_{fric}"]["Rdev4"] - table[f"REF_{fric}"]["Rdev4"], 3),
                          y4_diag=round(table[f"D1_{fric}"]["years_R"][4] - table[f"REF_{fric}"]["years_R"][4], 3),
                          y5=round(table[f"D1_{fric}"]["R5y"] - table[f"REF_{fric}"]["R5y"], 3))
    spear = d1_c2_spearman()
    c2gaps = c2tab["gaps"]
    (TMP / "d1bybit_table.json").write_text(json.dumps(
        {"table": table, "gaps": gaps, "spearman_D1_C2": spear,
         "c2_gaps_sidebyside": c2gaps,
         "ref_gate": {"years": exp["years"], "R": exp["R"], "DD": exp["DD"],
                      "full_path_dd": exp["full_path_dd"]}}, indent=1))
    print("gaps D1-REF:", gaps, flush=True)
    print("saved tmp/d1bybit_table.json", flush=True)


if __name__ == "__main__":
    main()
