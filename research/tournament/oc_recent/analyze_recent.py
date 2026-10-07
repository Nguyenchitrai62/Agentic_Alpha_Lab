"""oc_recent: diagnostic decomposition of the most recent year vs earlier years.

Implements PLAN.md verbatim. LIGHT: one process, shifts sequential, no 1m data.
Reads only research/tournament/oc_kpi/{events_s*.parquet, results.json}.
Writes results.json in this folder.

Usage: .venv/Scripts/python.exe research/tournament/oc_recent/analyze_recent.py
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi"
MAKER, TAKER = 0.0002, 0.00055
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_END = pd.Timestamp("2026-09-24", tz="UTC")
CUT = pd.Timestamp("2026-09-24", tz="UTC")
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def year_of(t) -> int | None:
    t = pd.Timestamp(t)
    for k in range(5):
        end = ANCH[k + 1] if k < 4 else ANCH_END
        if ANCH[k] <= t < end:
            return k
    return None


def book_episodes(ev):
    """Exact copy of oc_kpi compute_kpi.book_episodes + side/symbol/weight/entry."""
    pos, out = {}, []
    for e in ev.itertuples():
        k, sym = e.kind, e.symbol
        if k == "book_fill":
            q = abs(e.weight) / e.price
            pos[sym] = dict(t=e.t, side=1 if e.side == "buy" else -1, qty=q,
                            cost=q * e.price, proceeds=0.0,
                            fees=q * e.price * MAKER, w=float(abs(e.weight)))
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e.weight) / e.price
            o["qty"] += q
            o["cost"] += q * e.price
            o["fees"] += q * e.price * MAKER
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e.weight) / e.price, o["qty"])
            o["qty"] -= q
            o["proceeds"] += q * e.price
            o["fees"] += q * e.price * MAKER
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e.price
            o["fees"] += o["qty"] * e.price * (TAKER if k == "book_stop" else MAKER)
            net = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]
            out.append(dict(net=float(net), kind=k, entry_t=o["t"], exit_t=e.t,
                            symbol=sym, side=int(o["side"]), weight=float(o["cost"])))
            pos.pop(sym, None)
    return out, len(pos)


def pair_rungs(ev):
    pend, out, unpaired = {}, [], 0
    for r in ev.itertuples():
        if r.kind == "rung_fill":
            pend.setdefault(r.symbol, deque()).append(r)
        elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
            q0 = pend.get(r.symbol)
            if q0:
                f0 = q0.popleft()
                out.append(dict(ret=float(r.ret), exit=r.kind, fill_t=f0.t,
                                exit_t=r.t, symbol=r.symbol,
                                weight=float(f0.weight)))
            else:
                unpaired += 1
    left = sum(len(q) for q in pend.values())
    return out, unpaired, left


def stat(xs):
    xs = list(xs)
    if not xs:
        return dict(n=0, win=None, mean=None)
    a = np.array(xs, float)
    return dict(n=int(len(a)), win=round(float((a > 0).mean()), 4),
                mean=round(float(a.mean()), 5))


def main():
    kpi = json.loads((KPI / "results.json").read_text())
    monthly = [(m, float(v)) for m, v in kpi["equity"]["monthly"]]
    year_R = [dict(anchor=y["anchor"], R=y["R"]) for y in kpi["equity"]["years"]]

    all_book, all_rung = [], []
    max_t, unpaired_tot, open_book, open_rung = None, 0, 0, 0
    for s in range(4):  # sequential, one shift at a time (LIGHT)
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        tmax = ev["t"].max()
        max_t = tmax if max_t is None or tmax > max_t else max_t
        ev = ev.sort_values("t").reset_index(drop=True)
        book, left_b = book_episodes(ev)
        rungs, unpaired, left_r = pair_rungs(ev)
        unpaired_tot += unpaired
        open_book += left_b
        open_rung += left_r
        for d in book:
            d["shift"] = s
            all_book.append(d)
        for d in rungs:
            d["shift"] = s
            all_rung.append(d)
        del ev

    # --- per anchor-year x sleeve x coin ---
    sleeves = ["book_long", "book_short", "dip"]
    by_ysc = []
    for y in range(5):
        for coin in COINS:
            bl = [d["net"] for d in all_book
                  if year_of(d["entry_t"]) == y and d["side"] == 1 and d["symbol"] == coin]
            bs = [d["net"] for d in all_book
                  if year_of(d["entry_t"]) == y and d["side"] == -1 and d["symbol"] == coin]
            dp = [d for d in all_rung
                  if year_of(d["fill_t"]) == y and d["symbol"] == coin]
            rets = [d["ret"] for d in dp]
            ex = {k: int(sum(1 for d in dp if d["exit"] == k))
                  for k in ("rung_sl", "rung_tp", "rung_timeout")}
            s_bl, s_bs = stat(bl), stat(bs)
            s_dp = stat(rets)
            w = [d["weight"] for d in dp]
            by_ysc.append(dict(
                year=y, anchor=ANCH[y].strftime("%Y-%m-%d"), coin=coin,
                book_long=dict(**s_bl, mean_w=None),
                book_short=dict(**s_bs, mean_w=None),
                dip=dict(**s_dp, exits=ex,
                         mean_weight=round(float(np.mean(w)), 5) if w else None,
                         gross_fill_notional=round(float(np.sum(w)), 3) if w else 0.0)))

    # --- per anchor-year x sleeve totals ---
    by_ys = []
    for y in range(5):
        bl = [d["net"] for d in all_book if year_of(d["entry_t"]) == y and d["side"] == 1]
        bs = [d["net"] for d in all_book if year_of(d["entry_t"]) == y and d["side"] == -1]
        dp = [d for d in all_rung if year_of(d["fill_t"]) == y]
        rets = [d["ret"] for d in dp]
        ex = {k: int(sum(1 for d in dp if d["exit"] == k))
              for k in ("rung_sl", "rung_tp", "rung_timeout")}
        w = [d["weight"] for d in dp]
        fills_pm = round(len(dp) / 12, 1)
        by_ys.append(dict(
            year=y, anchor=ANCH[y].strftime("%Y-%m-%d"),
            book_long=stat(bl), book_short=stat(bs),
            dip=dict(**stat(rets), exits=ex,
                     mean_weight=round(float(np.mean(w)), 5) if w else None,
                     gross_fill_notional=round(float(np.sum(w)), 3),
                     fills_per_month=fills_pm)))

    # --- dip per fill-calendar-month ---
    per_month = []
    rungs_by_m: dict[str, list] = {}
    for d in all_rung:
        m = pd.Timestamp(d["fill_t"]).strftime("%Y-%m")
        rungs_by_m.setdefault(m, []).append(d)
    for m in sorted(rungs_by_m):
        dp = rungs_by_m[m]
        rets = [d["ret"] for d in dp]
        w = [d["weight"] for d in dp]
        ex = {k: int(sum(1 for d in dp if d["exit"] == k))
              for k in ("rung_sl", "rung_tp", "rung_timeout")}
        per_month.append(dict(month=m, fills=len(dp), **stat(rets), exits=ex,
                              mean_weight=round(float(np.mean(w)), 5),
                              gross_fill_notional=round(float(np.sum(w)), 3)))

    # --- book per year x side (directional) ---
    book_side = []
    for y in range(5):
        for side, name in ((1, "long"), (-1, "short")):
            ns = [d["net"] for d in all_book
                  if year_of(d["entry_t"]) == y and d["side"] == side]
            book_side.append(dict(year=y, anchor=ANCH[y].strftime("%Y-%m-%d"),
                                  side=name, **stat(ns)))

    # --- monthly path slices: year3 = 2024-10..2025-09, year4 = 2025-10..2026-09 ---
    def logret(pct):
        return float(np.log1p(pct / 100))

    def slice_months(lo, hi):
        return [(m, v) for m, v in monthly if lo <= m <= hi]

    y3 = slice_months("2024-10", "2025-09")
    y4 = slice_months("2025-10", "2026-09")
    # 2021-09 and 2026-09 are partial calendar months; note, not adjust.
    def carry(rows):
        lr = [(m, v, logret(v)) for m, v in rows]
        tot = sum(c for _, _, c in lr)
        ranked = sorted(lr, key=lambda r: r[2], reverse=True)
        return dict(months=[[m, v] for m, v, _ in lr],
                    total_log=round(tot, 4),
                    top3=[[m, v] for m, v, _ in ranked[:3]],
                    bottom3=[[m, v] for m, v, _ in ranked[-3:]],
                    share_top3=round(sum(c for _, _, c in ranked[:3]) / tot, 3) if tot else None,
                    n_neg=int(sum(1 for _, v in rows if v < 0)))

    # cross-check: product of (1+R) over slice vs year narrative (approx; reset
    # years use per-year reset mix, calendar slice uses continuous mix, so this
    # is a path-shape check, not an equality check)
    out = dict(
        variant="R2B1D17BF-diagnostic",
        data=dict(source="research/tournament/oc_kpi",
                  cut="2026-09-24T00:00:00Z",
                  pooled_book=len(all_book), pooled_rungs=len(all_rung)),
        year_R=year_R,
        monthly_path=dict(monthly=[[m, v] for m, v in monthly],
                          year3_carry=carry(y3), year4_carry=carry(y4),
                          note="calendar-month continuous-mix path; 2021-09 partial from 09-24, 2026-09 partial to 09-23 12:00"),
        per_year_sleeve=by_ys,
        per_year_sleeve_coin=by_ysc,
        book_side=book_side,
        dip_per_fill_month=per_month,
        checks=dict(max_event_t=str(max_t),
                    max_event_t_below_cut=bool(max_t < CUT),
                    unpaired_rung_exits=int(unpaired_tot),
                    open_book_excluded=int(open_book),
                    open_rungs_left=int(open_rung),
                    year_parts_sum_book=int(sum(
                        y["book_long"]["n"] + y["book_short"]["n"] for y in by_ys)),
                    year_parts_sum_rungs=int(sum(
                        (y["dip"]["exits"]["rung_sl"] + y["dip"]["exits"]["rung_tp"]
                         + y["dip"]["exits"]["rung_timeout"]) for y in by_ys))),
        note=("Trade means are returns on position notional (book: v213 episode net "
              "ex-funding; rungs: engine ret net of rung fees); equity path is the "
              "frozen oc_kpi continuous mix. Sleeve equity attribution would need a "
              "sleeve on/off replay and is NOT claimed here."))

    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("book", len(all_book), "rungs", len(all_rung), flush=True)
    print("y4 dip", by_ys[4]["dip"], flush=True)
    print("y3 dip", by_ys[3]["dip"], flush=True)
    print("y4 book L/S", by_ys[4]["book_long"], by_ys[4]["book_short"], flush=True)
    print("y3 book L/S", by_ys[3]["book_long"], by_ys[3]["book_short"], flush=True)


if __name__ == "__main__":
    main()
