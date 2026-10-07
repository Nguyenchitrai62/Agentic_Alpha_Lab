"""oc_contrib: diagnostic attribution of R2B1D17BF 5y return + DD episodes.

Reads oc_kpi events/barsum/results + oc_ddanat4p mix_episodes windows +
R2 tables (TP choice). LIGHT: one process, no 1m data.
Writes results.json in this folder.
Usage: .venv/Scripts/python.exe research/tournament/oc_contrib/attribute.py
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi"
DD = HERE.parent / "oc_ddanat4p"
RD = Path("research/parallel/rounds/parallel-20260906-r2")
MAKER, TAKER = 0.0002, 0.00055
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_END = pd.Timestamp("2026-09-24", tz="UTC")
DEPTH2IDX = {2.5: 0, 3.0: 1, 3.5: 2, 4.0: 3, 5.0: 4}


def year_of(t) -> int | None:
    t = pd.Timestamp(t)
    for k in range(5):
        end = ANCH[k + 1] if k < 4 else ANCH_END
        if ANCH[k] <= t < end:
            return k
    return None


def pair_rungs(ev: pd.DataFrame):
    """FIFO per symbol. Returns (pairs, unpaired_exits, left_open, max_fill_exit_wdiff)."""
    pend: dict[str, deque] = {}
    out = []
    unpaired = 0
    maxdiff = 0.0
    for r in ev.itertuples():
        if r.kind == "rung_fill":
            pend.setdefault(r.symbol, deque()).append(r)
        elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
            q0 = pend.get(r.symbol)
            if q0:
                f0 = q0.popleft()
                w_exit, w_fill = float(r.weight), float(f0.weight)
                maxdiff = max(maxdiff, abs(w_exit - w_fill))
                out.append(dict(
                    fill_t=pd.Timestamp(f0.t), exit_t=pd.Timestamp(r.t),
                    symbol=r.symbol, depth=float(f0.rung),
                    exit=r.kind, w_fill=w_fill, w_exit=w_exit,
                    ret=float(r.ret),
                    pnl=w_exit * float(r.ret), gross=w_exit))
            else:
                unpaired += 1
    left = sum(len(q) for q in pend.values())
    return out, unpaired, left, maxdiff


def book_episodes(ev: pd.DataFrame):
    """Copy of oc_kpi book_episodes + equity pnl/gross/side/timestamps."""
    pos, out = {}, []
    for e in ev.itertuples():
        k, sym = e.kind, e.symbol
        if k == "book_fill":
            q = abs(float(e.weight)) / float(e.price)
            pos[sym] = dict(entry_t=pd.Timestamp(e.t), side=1 if e.side == "buy" else -1,
                            qty=q, cost=q * float(e.price), proceeds=0.0,
                            fees=q * float(e.price) * MAKER, gross_add=0.0)
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(float(e.weight)) / float(e.price)
            o["qty"] += q
            o["cost"] += q * float(e.price)
            o["gross_add"] += q * float(e.price)
            o["fees"] += q * float(e.price) * MAKER
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(float(e.weight)) / float(e.price), o["qty"])
            o["qty"] -= q
            o["proceeds"] += q * float(e.price)
            o["fees"] += q * float(e.price) * MAKER
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * float(e.price)
            o["fees"] += o["qty"] * float(e.price) * (TAKER if k == "book_stop" else MAKER)
            pnl_eq = o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]
            net_ret = pnl_eq / o["cost"] if o["cost"] else 0.0
            out.append(dict(entry_t=o["entry_t"], exit_t=pd.Timestamp(e.t), symbol=sym,
                            side=o["side"], exit=k, pnl=pnl_eq,
                            gross=o["cost"] + o["gross_add"], net_ret=float(net_ret)))
            pos.pop(sym, None)
    return out, len(pos)


def load_tp_lookup(shift: int):
    """Returns (T_grid_sorted, dict[(T_val,sym,rung_idx)]->tp, n_rows). T_val = int64 ns."""
    tab = pd.read_parquet(
        RD / "v376" / "tables_hidden" / f"r2_table_s{shift}.parquet",
        columns=["T", "sym", "rung", "tp"])
    tab["T"] = pd.to_datetime(tab["T"], utc=True)
    grid = np.sort(tab["T"].astype("int64").unique())
    lut = {(int(pd.Timestamp(t).value), str(s), int(r)): float(tp)
           for t, s, r, tp in zip(tab["T"].astype("int64"), tab["sym"], tab["rung"], tab["tp"])}
    return grid, lut, len(tab)


def main():
    mix = json.loads((DD / "mix_episodes.json").read_text())
    # union of distinct (peak,trough] windows from full + reset episodes
    seen, episodes = set(), []
    for key in ("full_episodes", "reset_episodes"):
        for e in mix[key]:
            pk, tr = str(e["peak"]), str(e["trough"])
            if (pk, tr) not in seen:
                seen.add((pk, tr))
                episodes.append(dict(peak=pk, trough=tr,
                                     dd_4h_pct=float(e.get("dd_4h_pct", float("nan"))),
                                     dd_1m_pct=float(e.get("dd_1m_pct", float("nan")))))
    episodes.sort(key=lambda d: d["peak"])
    assert len(episodes) == 5, f"expected 5 union episodes, got {len(episodes)}"

    all_rungs, all_books = [], []
    checks = dict(unpaired_exits=0, open_rungs_left=0, open_books_left=0,
                  tp_unknown=0, max_fill_exit_wdiff=0.0)
    per_shift_n = []
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        ev = ev.sort_values("t").reset_index(drop=True)
        rungs, unpaired, rleft, maxdiff = pair_rungs(ev)
        books, bleft = book_episodes(ev)
        checks["unpaired_exits"] += int(unpaired)
        checks["open_rungs_left"] += int(rleft)
        checks["open_books_left"] += int(bleft)
        checks["max_fill_exit_wdiff"] = max(checks["max_fill_exit_wdiff"], float(maxdiff))
        grid, lut, _ = load_tp_lookup(s)
        for d in rungs:
            ftv = int(d["fill_t"].value)
            j = int(np.searchsorted(grid, ftv, side="right")) - 1
            if j < 0:
                checks["tp_unknown"] += 1
                d["tp"] = "unknown"
            else:
                key = (int(grid[j]), d["symbol"], DEPTH2IDX.get(d["depth"], -1))
                tp = lut.get(key)
                if tp is None:
                    checks["tp_unknown"] += 1
                    d["tp"] = "unknown"
                else:
                    d["tp"] = str(float(tp)) if float(tp) not in (0.5, 1.0, 1.5) else str(float(tp))
                    # normalise: '0.5'/'1.0'/'1.5'
                    d["tp"] = {"0.5": "0.5", "1.0": "1.0", "1.5": "1.5"}.get(d["tp"], d["tp"])
            d["shift"] = s
            d["year_entry"] = year_of(d["fill_t"])
            d["year_exit"] = year_of(d["exit_t"])
        for b in books:
            b["shift"] = s
            b["year_entry"] = year_of(b["entry_t"])
            b["year_exit"] = year_of(b["exit_t"])
        all_rungs += rungs
        all_books += books
        per_shift_n.append(dict(shift=s, n_rungs=len(rungs), n_books=len(books)))

    # ---- aggregation helper ----
    def agg(rows, keyfn, years=(0, 1, 2, 3, 4, "pooled")):
        out = {}
        pool = {}
        for y in range(5):
            sel = [r for r in rows if r["year_entry"] == y]
            by = {}
            for r in sel:
                by.setdefault(keyfn(r), []).append(r)
            out[str(y)] = {k: summ(v) for k, v in sorted(by.items())}
        by = {}
        for r in rows:
            by.setdefault(keyfn(r), []).append(r)
        out["pooled"] = {k: summ(v) for k, v in sorted(by.items())}
        return out

    def summ(v):
        n = len(v)
        pnl_sub = float(sum(r["pnl"] for r in v))
        gross = float(sum(r["gross"] for r in v))
        wins = sum(1 for r in v if (r["ret"] > 0 if "ret" in r else r["net_ret"] > 0))
        return dict(n=n, pnl_sub_pct=round(pnl_sub * 100, 3),
                    pnl_mix_pct=round(pnl_sub / 4 * 100, 3),
                    win=round(wins / n, 4) if n else None,
                    pnl_per_gross=round(pnl_sub / gross, 5) if gross else None,
                    gross_sub=round(gross, 3))

    sleeve = agg(all_books + [dict(**d, _s="dip") for d in all_rungs],
                 lambda r: ("dip" if "_s" in r else ("book_long" if r["side"] == 1 else "book_short")))
    # fix: rung dicts lack side/net_ret; summ win uses ret for rungs, net_ret for books
    depth = agg(all_rungs, lambda r: str(r["depth"]))
    coin = agg(all_books + all_rungs, lambda r: r["symbol"])
    # coin split further by sleeve? keep combined + note; leader can cross with sleeve table
    exitkind = agg(all_rungs, lambda r: r["exit"])
    tpchoice = agg(all_rungs, lambda r: r["tp"])

    # per-year totals (all trades, entry year) in mix %
    per_year_tot = []
    for y in range(5):
        b = [r for r in all_books if r["year_entry"] == y]
        r = [r for r in all_rungs if r["year_entry"] == y]
        pnl = sum(r_["pnl"] for r_ in b) + sum(r_["pnl"] for r_ in r)
        per_year_tot.append(dict(year=y, anchor=ANCH[y].strftime("%Y-%m-%d"),
                                 pnl_sub_pct=round(pnl * 100, 3),
                                 pnl_mix_pct=round(pnl / 4 * 100, 3),
                                 n_book=len(b), n_rungs=len(r)))
    pooled_pnl = sum(r["pnl"] for r in all_books) + sum(r["pnl"] for r in all_rungs)

    # ---- DD windows: exit-time realized ----
    dd_out = []
    for e in episodes:
        pk, tr = pd.Timestamp(e["peak"]), pd.Timestamp(e["trough"])
        inwin = lambda t: (t > pk) and (t <= tr)
        rb = [r for r in all_books if inwin(r["exit_t"])]
        rr = [r for r in all_rungs if inwin(r["exit_t"])]
        tot = sum(r["pnl"] for r in rb) + sum(r["pnl"] for r in rr)
        def wrows(rows, kf):
            by = {}
            for r in rows:
                by.setdefault(kf(r), []).append(r)
            d = {}
            for k, v in sorted(by.items()):
                p = sum(x["pnl"] for x in v)
                d[k] = dict(n=len(v), pnl_mix_pct=round(p / 4 * 100, 3),
                            share_of_window=round(p / tot, 4) if tot else None)
            return d
        dd_out.append(dict(
            peak=e["peak"], trough=e["trough"],
            dd_4h_pct=e["dd_4h_pct"], dd_1m_pct=e["dd_1m_pct"],
            window_realized_sub_pct=round(tot * 100, 3),
            window_realized_mix_pct=round(tot / 4 * 100, 3),
            n_book=len(rb), n_rungs=len(rr),
            by_sleeve=wrows(rb + [dict(**d, _s=1) for d in rr],
                            lambda r: ("dip" if "_s" in r else ("book_long" if r["side"] == 1 else "book_short"))),
            by_depth=wrows(rr, lambda r: str(r["depth"])),
            by_coin=wrows(rb + rr, lambda r: r["symbol"]),
            by_exit=wrows(rr, lambda r: r["exit"]),
            by_tp=wrows(rr, lambda r: r["tp"])))

    out = dict(
        variant="R2B1D17BF", diagnostic=True, selection_rule="none (diagnostic, no PROMISING rule)",
        methods=("FIFO rung pairing + v213 book episodes; year=ENTRY anchor year; "
                 "pnl=fraction of sub-account equity (rung weight*ret net of rung fees; "
                 "book side*(proceeds-cost)-fees, funding excluded); pnl_mix=pnl_sub/4 "
                 "(1/4 capital per phase, additive approx — compounding gap vs 5y net stated); "
                 "win=ret/net_ret>0; pnl_per_gross=sum(pnl)/sum(gross) with rung gross=exit weight, "
                 "book gross=cost+adds; DD windows=union(5) of mix_episodes full+reset (peak,trough] "
                 "on mixed clock, exit-time realized only (no open marks, no funding); "
                 "dip exit close-stop/backstop merged as rung_sl (engine logs one kind); "
                 "TP choice via R2 table (T<=fill_t, sym, depth->idx)."),
        episodes_windows=[dict(peak=e["peak"], trough=e["trough"],
                               dd_4h_pct=e["dd_4h_pct"], dd_1m_pct=e["dd_1m_pct"]) for e in episodes],
        per_year_entry_totals=per_year_tot,
        pooled=dict(pnl_sub_pct=round(pooled_pnl * 100, 3),
                    pnl_mix_pct=round(pooled_pnl / 4 * 100, 3),
                    n_book=len(all_books), n_rungs=len(all_rungs)),
        by_sleeve=sleeve, by_depth=depth, by_coin=coin, by_exit=exitkind, by_tp=tpchoice,
        dd_episodes=dd_out, per_shift=per_shift_n, checks=checks)
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("pooled mix %", round(pooled_pnl / 4 * 100, 2), "n", len(all_books) + len(all_rungs), flush=True)
    print("checks", checks, flush=True)
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
