"""oc_spotlongs2 scoring (CPU-only): gate + dev4 / Y4-diagnostic / 5y + full-path DD.

Reads tmp/runs_<stage>_<fric>.pkl (REF/SPOT_F10/SPOT_F06 full-window runs per
shift), scores with reset_metric.year_reset + v388.mix, checks the reproduction
gate (REF dev years 0..3 == v421 G2 to the digit; pick-last years 0..3 ==
pick-dev), aggregates the per-bar turnover + fee/funding split records into
per-year means across shifts, writes tmp/spotlongs2_table.json + results.json.
REPORT.md is written from that table only. REF full-window numbers are the
stored v421 row (labelled, never recomputed); REF_S5 side-by-side is read from
oc_c2bybit (never recomputed).
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
VARIANTS = ("REF", "SPOT_F10", "SPOT_F06")
SPLIT_KEYS = ("turnover", "spot_fees", "perp_fees", "funding_saved",
              "funding_paid", "borrow")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def score_runs(runs, key, g1, v388, rm, years):
    """Score one variant key from {shift: {key: rec}} on valid year indices.

    years: subset of 0..4 present in these runs (dev stage -> [0,1,2,3]).
    Dev stats (Rdev4/W/DDdev4/losing) use years 0..3; 5y/full only when all
    five years are present, else None.
    """
    years = list(years)
    rr = {s: {key: runs[s][key]["run"]} for s in range(4)}
    all_yrs = [rm.year_reset(rr, key, y) for y in years]
    Rs = [y["R"] for y in all_yrs]
    DDs = [y["DD"] for y in all_yrs]
    y2r = dict(zip(years, Rs))
    y2d = dict(zip(years, DDs))
    dev_yrs = [y for y in years if y < 4]
    dev = [y2r[y] for y in dev_yrs]
    e, mn = v388.mix(rr, key, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    fulldd = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    wins = []
    for y in range(5):
        if y in years:
            nb = sum(runs[s][key]["wins"][y]["nb"] for s in range(4))
            wb = sum(runs[s][key]["wins"][y]["wb"] for s in range(4))
            nr = sum(runs[s][key]["wins"][y]["nr"] for s in range(4))
            wr = sum(runs[s][key]["wins"][y]["wr"] for s in range(4))
        else:
            nb = wb = nr = wr = 0
        wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                         book_win=round(wb / nb, 4) if nb else None,
                         rung_win=round(wr / nr, 4) if nr else None,
                         all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
    out = dict(years_R=Rs, years_DD=DDs, years_idx=years,
               Rdev4=geo(dev), Wdev4=round(min(dev), 3),
               DDdev4=round(max(y2d[y] for y in dev_yrs), 2),
               losing_dev4=sum(r < 0 for r in dev),
               wins=wins)
    if set(years) == {0, 1, 2, 3, 4}:
        out.update(R5y=geo(Rs), W5y=round(min(Rs), 3),
                   DD5y=round(max(DDs), 2),
                   losing_5y=sum(r < 0 for r in Rs),
                   full_path_dd=fulldd,
                   DDmax_full=round(max(max(DDs), fulldd), 2))
    else:
        out.update(R5y=None, W5y=None, DD5y=None, losing_5y=None,
                   full_path_dd=None, DDmax_full=round(max(max(DDs), fulldd), 2))
    return out


def split_years(runs, key, years):
    """Mean-across-shifts yearly sums of the per-bar turnover/fee-split records.

    Per (shift s, year y): sum of per-bar terms over holding bars with open T
    in [A_y + sh + 4h, A_y + sh + 365d + 4h) (same windowing as the wins
    collection in the compute script). Reported = mean across the 4 shifts, in
    fractions of equity per year (turnover is x equity/year).
    """
    anchors = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
    out = {}
    for y in years:
        per_shift = []
        for s in range(4):
            sh = pd.Timedelta(hours=s)
            a0 = pd.Timestamp(anchors[y], tz="UTC") + sh + pd.Timedelta(hours=4)
            a1 = a0 + pd.Timedelta(days=365)
            acc = {k: 0.0 for k in SPLIT_KEYS}
            for b in runs[s][key]["bars_lite"]:
                t = pd.Timestamp(b["t"])
                if a0 <= t < a1:
                    for k in SPLIT_KEYS:
                        acc[k] += float(b.get(k, 0.0))
            per_shift.append(acc)
        mean = {k: round(float(np.mean([p[k] for p in per_shift])), 6) for k in SPLIT_KEYS}
        out[str(y)] = mean
    return out


def main():
    v388 = _load("v388_spot2", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_spot2", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]

    p = TMP / "runs_dev_base.pkl"
    assert p.exists(), f"missing {p} — run compute_spotlongs2_engine.py --stage dev first"
    runs = pickle.loads(p.read_bytes())
    assert set(runs) == {0, 1, 2, 3}, sorted(runs)
    for s in range(4):
        assert set(runs[s]) >= {"REF"}, (s, sorted(runs[s]))
    dev_years = [0, 1, 2, 3]

    table = {}
    for v in VARIANTS:
        if v not in runs[0]:
            continue
        table[v] = score_runs(runs, v, g1, v388, rm, dev_years)
        table[v]["split_dev_years"] = split_years(runs, v, dev_years)

    # ---- reproduction gate: REF dev years 0..3 == v421 G2 to the digit ----
    for y in dev_years:
        er, ed = exp["years"][y]
        assert table["REF"]["years_R"][y] == er, (y, table["REF"]["years_R"][y], er)
        assert table["REF"]["years_DD"][y] == ed, (y, table["REF"]["years_DD"][y], ed)
    print("REF reproduces v421 G2 dev years 0..3 EXACTLY:",
          table["REF"]["years_R"], flush=True)

    # ---- dev4 robust pick (REF vs SPOT_F10 only; SPOT_F06 never picked) ----
    cand = {v: table[v] for v in ("REF", "SPOT_F10") if v in table}
    assert set(cand) == {"REF", "SPOT_F10"}, sorted(cand)
    elig = {v: t for v, t in cand.items()
            if t["DDmax_full"] <= 20 and t["losing_dev4"] == 0}
    pool = elig or cand
    above = {v: t for v, t in pool.items() if t["Rdev4"] >= 5}
    pool2 = above or pool
    best = max(sorted(pool2), key=lambda v: (pool2[v]["Wdev4"], pool2[v]["Rdev4"]))

    # ---- last-year window (pick only, scored ONCE) ----
    plast = TMP / "runs_last_base.pkl"
    if plast.exists():
        last = pickle.loads(plast.read_bytes())
        assert set(last) == {0, 1, 2, 3}, sorted(last)
        assert set(last[0]) == {best}, (best, sorted(last[0]))
        full = score_runs(last, best, g1, v388, rm, [0, 1, 2, 3, 4])
        for y in dev_years:  # last-stage run must match dev-stage on years 0..3
            assert full["years_R"][y] == table[best]["years_R"][y], (y, full, table[best])
            assert full["years_DD"][y] == table[best]["years_DD"][y], (y, full, table[best])
        print(f"{best} last-stage matches dev on years 0..3; Y4:",
              full["years_R"][4], full["years_DD"][4], flush=True)
        full["split_years"] = split_years(last, best, [0, 1, 2, 3, 4])
        table[f"{best}_full"] = full

    # ---- S5 Bybit dev window (pick only) + REF_S5 side-by-side ----
    ps5 = TMP / "runs_dev_S5.pkl"
    if ps5.exists():
        s5 = pickle.loads(ps5.read_bytes())
        assert set(s5[0]) == {best}, (best, sorted(s5[0]))
        table[f"{best}_S5"] = score_runs(s5, best, g1, v388, rm, dev_years)
        table[f"{best}_S5"]["split_dev_years"] = split_years(s5, best, dev_years)
    c2b = json.loads((C2B / "tmp/c2bybit_table.json").read_text())["table"]
    table["REF_S5_side"] = {k: c2b["REF_S5"][k] for k in
                            ("years_R", "years_DD", "Rdev4", "Wdev4", "DDdev4",
                             "R5y", "W5y", "full_path_dd", "DDmax_full")}

    # ---- stored REF full-window row (labelled, never recomputed) ----
    table["REF_stored"] = dict(
        years_R=[r for r, _ in exp["years"]],
        years_DD=[d for _, d in exp["years"]],
        R5y=exp["R"], W5y=exp["W"], DD5y=exp["DD"],
        losing_5y=exp.get("losing", 0), full_path_dd=exp["full_path_dd"],
        Rdev4=geo([r for r, _ in exp["years"]][:4]),
        Wdev4=min(r for r, _ in exp["years"][:4]),
        DDdev4=max(d for _, d in exp["years"][:4]),
        losing_dev4=sum(r < 0 for r, _ in exp["years"][:4]))

    (TMP / "spotlongs2_table.json").write_text(json.dumps(
        {"table": table,
         "pick": best,
         "ref_gate": {"years": exp["years"], "R": exp["R"], "DD": exp["DD"],
                      "full_path_dd": exp["full_path_dd"]}}, indent=1))
    print("dev table:", {v: (table[v]["Rdev4"], table[v]["Wdev4"],
                             table[v]["DDmax_full"], table[v]["losing_dev4"])
                         for v in cand}, flush=True)
    print("SPOT_F06 (sensitivity):", (table["SPOT_F06"]["Rdev4"], table["SPOT_F06"]["Wdev4"],
                                       table["SPOT_F06"]["DDmax_full"]), flush=True)
    print("dev4 robust pick:", best, flush=True)

    out = {
        "meta": {
            "ref": "v421 R2B1D17BFG2 (REF gate reproduces dev 0..3 to digit; REF full row stored)",
            "variants": ["REF gate", "SPOT_F10 (all book longs spot, spot 0.001/0.001, borrow APR 10%)",
                         "SPOT_F06 (same routing, spot 0.0006/0.0006 sensitivity, borrow APR 10%)",
                         "S5 Bybit-price row for the pick (short 2021 window labelled)"],
            "costs": "perp legs maker 0.0002 / taker 0.00055; spot-routed LONG book legs maker/taker 0.001 (F10) or 0.0006 (F06); book longs spot 0 funding, borrow APR 10% on max(0, spot-long - equity)",
            "metric": "reset_metric.year_reset per anchor year + v388.mix full-path DD; robust pick on dev4 (REF vs SPOT_F10) only",
            "turnover_note": ("per-bar book turnover + spot/perp fee split + funding paid/saved + borrow "
                              "(fractions of bar-start equity) summed per anchor year, mean across 4 shifts; "
                              "dip-sleeve fees stay implicit in rung returns (engine convention)"),
        },
        "table": table,
        "pick": best,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("saved results.json + tmp/spotlongs2_table.json", flush=True)


if __name__ == "__main__":
    main()
