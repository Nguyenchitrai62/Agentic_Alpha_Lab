"""oc_decayexit analyze: reset-metric scoring + robust dev4 pick + results.json.

Stage discipline: dev (tmp/runs_dev.pkl) holds REF+V1+V2+C_V1+C_V2 on
[DEV0,DEV1) only (Y4 zeros, never scored). Last (tmp/runs_last.pkl) must hold
ONLY REF + the dev4 pick on [DEV0,Y1) — scored ONCE. This script asserts that
discipline. Controls are diagnostic (in-year, not eligible, never picked).

Metrics per variant: per-year 4-phase reset %/mo + DD (reset_metric.year_reset),
dev4 geo mean / W / maxDD / losing, 5y geo mean (dev stage: 4y only; last stage:
5y with Y4 labelled scored-once), full-path DD via v388.mix, book win rates +
fills from wins, fee/funding totals from engine stats.

Robust pick (dev4 ONLY, among REF+V1+V2): eligible DDdev4<=20 and losing_dev4==0;
prefer Rdev4>=5, then highest Wdev4, ties->higher Rdev4.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TMP = HERE / "tmp"

sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
import phase_offset_full as pof  # noqa: E402

ANCH5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
ELIGIBLE = ("REF", "V1", "V2")
ALL_DEV = ("REF", "V1", "V2", "C_V1", "C_V2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_bt_an", RD / "v388/v388_bot_stop_distance.py")
rm = _load("reset_bt_an", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
G1 = v388.Y1 + pd.Timedelta(hours=12)


def geo(rs) -> float:
    g = 1.0
    for r in rs:
        g *= 1.0 + float(r) / 100.0
    return 100.0 * (g ** (1.0 / len(rs)) - 1.0)


def score_variant(allres, variant: str, years: list[int]) -> dict:
    runs = {s: {variant: allres[s][variant]["run"]} for s in allres}
    yr = [rm.year_reset(runs, variant, y) for y in years]
    Rs = [y["R"] for y in yr]
    DDs = [y["DD"] for y in yr]
    e, mn = v388.mix(runs, variant, G1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    fullDD = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    nb = sum(allres[s][variant]["wins"][y]["nb"] for s in allres for y in years)
    wb = sum(allres[s][variant]["wins"][y]["wb"] for s in allres for y in years)
    nr = sum(allres[s][variant]["wins"][y]["nr"] for s in allres for y in years)
    wr = sum(allres[s][variant]["wins"][y]["wr"] for s in allres for y in years)
    nf = sum(allres[s][variant]["wins"][y]["nfill"] for s in allres for y in years)
    fees = sum(float(allres[s][variant].get("stats", {}).get("fees", 0.0)) for s in allres)
    funding = sum(float(allres[s][variant].get("stats", {}).get("funding", 0.0)) for s in allres)
    per_year_win = []
    per_year_fills = []
    for y in years:
        nby = sum(allres[s][variant]["wins"][y]["nb"] for s in allres)
        wby = sum(allres[s][variant]["wins"][y]["wb"] for s in allres)
        per_year_win.append(round(wby / nby, 4) if nby else None)
        per_year_fills.append(sum(allres[s][variant]["wins"][y]["nfill"] for s in allres))
    return dict(years_R=[y["R"] for y in yr], years_DD=[y["DD"] for y in yr],
                years_book_win=per_year_win, years_fills=per_year_fills,
                R5=round(geo(Rs), 3), W=round(min(Rs), 3), maxDD=round(max(DDs), 2),
                fullDD=fullDD, losing=sum(r < 0 for r in Rs),
                book_trades=int(nb), book_win=round(wb / nb, 4) if nb else None,
                rung_trades=int(nr), rung_win=round(wr / nr, 4) if nr else None,
                win_all=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None,
                fills=int(nf), fees=round(fees, 4), funding=round(funding, 4))


def robust_pick(table: dict) -> str:
    cands = {k: v for k, v in table.items() if k in ELIGIBLE
             and v["DDdev4"] <= 20 and v["losing_dev4"] == 0}
    if not cands:
        return "none-eligible"
    hot = {k: v for k, v in cands.items() if v["Rdev4"] >= 5}
    pool = hot or cands
    return max(pool, key=lambda k: (pool[k]["Wdev4"], pool[k]["Rdev4"]))


def main():
    dev_p = TMP / "runs_dev.pkl"
    last_p = TMP / "runs_last.pkl"
    assert dev_p.exists(), "runs_dev.pkl missing — run the dev stage first"
    dev = pickle.loads(dev_p.read_bytes())
    assert set(dev) == {0, 1, 2, 3}, sorted(dev)
    for s in dev:
        assert set(dev[s]) == set(ALL_DEV), (s, sorted(dev[s]))
    exp_years = [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81), (10.677, 8.27)]
    table_dev = {}
    for v in ALL_DEV:
        sc = score_variant(dev, v, [0, 1, 2, 3])
        table_dev[v] = dict(
            years_R=sc["years_R"], years_DD=sc["years_DD"],
            years_book_win=sc["years_book_win"], years_fills=sc["years_fills"],
            Rdev4=sc["R5"], Wdev4=sc["W"], DDdev4=sc["maxDD"], losing_dev4=sc["losing"],
            fullDD_dev=sc["fullDD"], book_win=sc["book_win"], win_all=sc["win_all"],
            fills=sc["fills"], fees=sc["fees"], funding=sc["funding"],
            rung_win=sc["rung_win"])
    ref = table_dev["REF"]
    assert ref["years_R"] == [r for r, _ in exp_years], ref["years_R"]
    assert ref["years_DD"] == [d for _, d in exp_years], ref["years_DD"]
    print("REF dev identity OK vs v421 (dev years to the digit)", flush=True)
    pick = robust_pick(table_dev)
    print("DEV4 table:", json.dumps(table_dev, indent=1), flush=True)
    print("PICK (dev4 only, REF+V1+V2):", pick, flush=True)
    # Frozen claim rule: beats-exposure iff R(V) > R(C) AND DDmax(V) <= DDmax(C).
    for v, c in (("V1", "C_V1"), ("V2", "C_V2")):
        beats = (table_dev[v]["Rdev4"] > table_dev[c]["Rdev4"]
                 and table_dev[v]["DDdev4"] <= table_dev[c]["DDdev4"])
        print(f"{v} beats-exposure vs {c}: {beats} "
              f"(R {table_dev[v]['Rdev4']} vs {table_dev[c]['Rdev4']}; "
              f"DD {table_dev[v]['DDdev4']} vs {table_dev[c]['DDdev4']})", flush=True)

    with open(TMP / "std_books.pkl", "rb") as fh:
        S = pickle.load(fh)
    out = {"meta": {
        "idea": "IDEAS8 #6 signal-decay exit (remember entry |w0|; exit limit when |w|<frac*|w0|); V1 frac 0.3, V2 frac 0.5",
        "harness": ("4-phase engine vs G2 v421 R2B1D17BFG2 (pipe v321, kd=1.7 corr-inv, "
                    "bear books, budget 0.26*1.7, G=2.0, win_start=5, gate costs "
                    "maker 0.0002/taker 0.00055/longs 0.0001 per 8h; decay full limit close, "
                    "sign-flip tighten+close kept, SL/TP unchanged, stop-first)"),
        "metric": ("reset_metric.year_reset per anchor + v388.mix full-path DD; "
                   "selection on dev years 2021-2024 only; last year POST-HOC scored-once"),
        "rows": {"REF": "G2 unchanged (reproduces v421 to the digit)",
                 "V1": "decay frac 0.3 (frozen)",
                 "V2": "decay frac 0.5 (frozen)",
                 "C_V1": "exposure-matched constant for V1 (diagnostic, in-year, not eligible)",
                 "C_V2": "exposure-matched constant for V2 (diagnostic, in-year, not eligible)"},
        "pick": pick,
        "costs": {"maker": 0.0002, "taker": 0.00055, "fund_long_8h": 0.0001},
        "cy": S.get("cy", {})},
        "dev": table_dev, "pick": pick}

    if last_p.exists():
        last = pickle.loads(last_p.read_bytes())
        assert set(last) == {0, 1, 2, 3}, sorted(last)
        have = set(next(iter(last.values())))
        want = {"REF", pick} if pick not in ("none-eligible", "REF") else {"REF"}
        assert have == want, (have, want)
        table_last = {}
        for v in sorted(want):
            sc = score_variant(last, v, [0, 1, 2, 3, 4])
            table_last[v] = dict(
                years_R=sc["years_R"], years_DD=sc["years_DD"],
                years_book_win=sc["years_book_win"], years_fills=sc["years_fills"],
                R5=sc["R5"], W=sc["W"], maxDD=sc["maxDD"], losing=sc["losing"],
                fullDD=sc["fullDD"], book_win=sc["book_win"], win_all=sc["win_all"],
                fills=sc["fills"], fees=sc["fees"], funding=sc["funding"],
                rung_win=sc["rung_win"],
                Rdev4=round(geo(sc["years_R"][:4]), 3), Wdev4=min(sc["years_R"][:4]),
                DDdev4=max(sc["years_DD"][:4]), Rlast=sc["years_R"][4])
        assert table_last["REF"]["years_R"][4] == 4.648, table_last["REF"]["years_R"]
        assert table_last["REF"]["years_DD"][4] == 12.9, table_last["REF"]["years_DD"]
        out["last_scored_once"] = table_last
        print("LAST (scored-once) table:", json.dumps(table_last, indent=1), flush=True)
    else:
        print("last stage not run yet (expected before the pick is scored once)", flush=True)
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
