"""oc_weeklybook analyze_last: last (Binance, scored-once) + S5 (Bybit friction) tables (LIGHT).

Reads tmp/dev_table.json for the frozen dev4 pick, tmp/runs_last.pkl (REF + pick
on [DEV0,Y1)) and tmp/runs_s5.pkl (REF + pick on Bybit [S5_START,DEV1)), appends
last_scored_once + s5_friction to results.json. Y4/S5 never pick.
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_bt_anl", RD / "v388/v388_bot_stop_distance.py")
rm = _load("reset_bt_anl", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
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


def main():
    dev_info = json.loads((TMP / "dev_table.json").read_text())
    pick = dev_info["pick"]
    want = {"REF", pick} if pick not in ("none-eligible", "REF") else {"REF"}
    print(f"frozen dev4 pick: {pick}; last/s5 want rows: {sorted(want)}", flush=True)

    out = json.loads((HERE / "results.json").read_text())

    last_p = TMP / "runs_last.pkl"
    assert last_p.exists(), "runs_last.pkl missing — run the last stage first"
    last = pickle.loads(last_p.read_bytes())
    assert set(last) == {0, 1, 2, 3}, sorted(last)
    have = set(next(iter(last.values())))
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

    s5_p = TMP / "runs_s5.pkl"
    assert s5_p.exists(), "runs_s5.pkl missing — run the s5 stage first"
    s5 = pickle.loads(s5_p.read_bytes())
    assert set(s5) == {0, 1, 2, 3}, sorted(s5)
    have5 = set(next(iter(s5.values())))
    assert have5 == want, (have5, want)
    table_s5 = {}
    for v in sorted(want):
        sc = score_variant(s5, v, [0, 1, 2, 3])
        table_s5[v] = dict(
            years_R=sc["years_R"], years_DD=sc["years_DD"],
            years_book_win=sc["years_book_win"], years_fills=sc["years_fills"],
            Rdev4=sc["R5"], Wdev4=sc["W"], DDdev4=sc["maxDD"], losing_dev4=sc["losing"],
            fullDD_dev=sc["fullDD"], book_win=sc["book_win"], win_all=sc["win_all"],
            fills=sc["fills"], fees=sc["fees"], funding=sc["funding"],
            rung_win=sc["rung_win"])
    out["s5_bybit_friction_scored_once_dev_window"] = {
        "note": ("Bybit 1m prices (oc_c2bybit S5 harness: bybit_minutes, live0=2021-11-15+shift, "
                 "std filtered >=2021-11-15 before shift; year 2021 = short window from 2021-11-15, "
                 "friction row only, never for selection)"),
        "table": table_s5}
    print("S5 (Bybit friction, dev window) table:", json.dumps(table_s5, indent=1), flush=True)

    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("updated results.json with last + s5", flush=True)


if __name__ == "__main__":
    main()
