"""oc_kpi_g2: win rates + positions/exposure from the s=0..3 replica events/bars.

Reads events_s{0..3}.parquet + barsum_s{0..3}.parquet (run_kpi_trades.py) and
results_equity.json (run_kpi.py). Merges everything into results.json, with the
R2B1D17BF oc_kpi numbers embedded side-by-side as reference_BF.
Usage: .venv/Scripts/python.exe research/tournament/oc_kpi_g2/compute_kpi.py
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
MAKER, TAKER = 0.0002, 0.00055
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_END = pd.Timestamp("2026-09-24", tz="UTC")


def year_of(t):
    t = pd.Timestamp(t)
    for k in range(5):
        end = ANCH[k + 1] if k < 4 else ANCH_END
        if ANCH[k] <= t < end:
            return k
    return None


def book_episodes(ev):
    """Exact copy of v213.trade_stats episode loop, plus entry/exit timestamps."""
    pos, out = {}, []
    for e in ev.itertuples():
        k, sym = e.kind, e.symbol
        if k == "book_fill":
            q = abs(e.weight) / e.price
            pos[sym] = dict(t=e.t, side=1 if e.side == "buy" else -1, qty=q,
                            cost=q * e.price, proceeds=0.0, fees=q * e.price * MAKER)
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
            out.append(dict(net=float(net), kind=k, entry_t=o["t"], exit_t=e.t, symbol=sym))
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
                out.append(dict(ret=float(r.ret), exit=r.kind, fill_t=f0.t, exit_t=r.t,
                                symbol=r.symbol, weight=float(f0.weight)))
            else:
                unpaired += 1
    left = sum(len(q) for q in pend.values())
    return out, unpaired, left


def main():
    eq = json.loads((HERE / "results_equity.json").read_text())
    per_year, shifts = [], []
    all_book, all_rung = [], []
    pos_rows, gross_vals, nbook_vals = [], [], []
    dip_minutes, dip_wminutes = 0.0, 0.0
    max_conc_dip, max_total, max_comb_gross = 0, 0, 0.0
    peak_gross_s, peak_gross_t, peak_total_t = 0, None, None
    open_left = 0
    total_live_min = 0.0
    for s in range(4):
        ev = pd.read_parquet(HERE / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        ev = ev.sort_values("t").reset_index(drop=True)
        bs = pd.read_parquet(HERE / f"barsum_s{s}.parquet")
        bs["t"] = pd.to_datetime(bs["t"], utc=True)
        book, left = book_episodes(ev)
        rungs, unpaired, rung_left = pair_rungs(ev)
        open_left += left
        all_book += [dict(**d, shift=s) for d in book]
        all_rung += [dict(**d, shift=s) for d in rungs]
        # dip concurrency sweep on [fill, exit)
        pts = []
        for d in rungs:
            f = pd.Timestamp(d["fill_t"]).value
            x = pd.Timestamp(d["exit_t"]).value
            pts.append((f, 1, float(d["weight"])))
            pts.append((x, -1, float(d["weight"])))
        pts.sort()
        conc, peak_c = 0, 0
        for t, d, w in pts:
            conc += d
            peak_c = max(peak_c, conc)
        # rung-minutes + weight-minutes
        rmin = sum((pd.Timestamp(d["exit_t"]).value - pd.Timestamp(d["fill_t"]).value) / 6e10 for d in rungs)
        wmin = sum(float(d["weight"]) * (pd.Timestamp(d["exit_t"]).value - pd.Timestamp(d["fill_t"]).value) / 6e10
                   for d in rungs)
        dip_minutes += rmin
        dip_wminutes += wmin
        max_conc_dip = max(max_conc_dip, peak_c)
        # book per-bar stats
        nbook_vals += bs["n_book"].tolist()
        gross_vals += bs["gross_book"].tolist()
        # combined max: at each rung fill minute, book n/gross of its bar + concurrent rungs/weights
        bidx = bs["t"].to_numpy()
        bn = bs["n_book"].to_numpy()
        bg = bs["gross_book"].to_numpy()
        fills_sorted = None  # (removed)
        conc2, w2 = 0, 0.0
        # sweep fills/exits together
        evs = []
        for d in rungs:
            evs.append((pd.Timestamp(d["fill_t"]).value, 1, float(d["weight"]), d["fill_t"]))
            evs.append((pd.Timestamp(d["exit_t"]).value, -1, float(d["weight"]), d["exit_t"]))
        evs.sort()
        bidx_int = bs["t"].apply(lambda x: pd.Timestamp(x).value).to_numpy()
        for t, d, w, to in evs:
            if d > 0:
                conc2 += 1
                w2 += w
                # book state of the bar containing t: last barsum t <= t+4h? barsum t = bar END (idx+8h);
                # bar start = t_bar - 4h. Use last bar with bar_end - 4h <= t, i.e. bar_end <= t + 4h.
                k = int(np.searchsorted(bidx_int,
                                        pd.Timestamp(to).value + int(4 * 3.6e12)) - 1)
                k = min(max(k, 0), len(bn) - 1)
                tot = int(bn[k]) + conc2
                gr2 = float(bg[k]) + w2
                if tot > max_total:
                    max_total = tot
                    peak_total_t = str(to)
                if gr2 > max_comb_gross:
                    max_comb_gross = gr2
                    peak_gross_s, peak_gross_t = s, str(to)
            else:
                conc2 -= 1
                w2 -= w
        live_min_s = float((pd.Timestamp("2026-09-23", tz="UTC") - pd.Timestamp("2021-09-24", tz="UTC")).total_seconds() / 60)
        total_live_min += live_min_s
        shifts.append(dict(shift=s, n_events=int(len(ev)), n_book=len(book), n_rungs=len(rungs),
                           book_win=round(float(np.mean([d["net"] > 0 for d in book])), 4) if book else None,
                           rung_win=round(float(np.mean([d["ret"] > 0 for d in rungs])), 4) if rungs else None,
                           n_book_avg=round(float(bs["n_book"].mean()), 3),
                           n_book_max=int(bs["n_book"].max()),
                           gross_book_avg=round(float(bs["gross_book"].mean()), 4),
                           gross_book_max=round(float(bs["gross_book"].max()), 4),
                           unpaired_exits=int(unpaired), open_book_left=int(left),
                           open_rung_left=int(rung_left),
                           rung_exits={k: int(sum(1 for d in rungs if d["exit"] == k))
                                       for k in ("rung_sl", "rung_tp", "rung_timeout")},
                           peak_conc_dip=int(peak_c)))
    # per anchor year (entry time), pooled over shifts
    years = []
    for y in range(5):
        b = [d for d in all_book if year_of(d["entry_t"]) == y]
        r = [d for d in all_rung if year_of(d["fill_t"]) == y]
        n = len(b) + len(r)
        years.append(dict(
            year=y, anchor=ANCH[y].strftime("%Y-%m-%d"),
            n_book=len(b), win_book=round(float(np.mean([d["net"] > 0 for d in b])), 4) if b else None,
            n_rungs=len(r), win_rungs=round(float(np.mean([d["ret"] > 0 for d in r])), 4) if r else None,
            rung_exits={k: int(sum(1 for d in r if d["exit"] == k))
                        for k in ("rung_sl", "rung_tp", "rung_timeout")},
            n_all=n,
            win_all=round(float((sum(d["net"] > 0 for d in b) + sum(d["ret"] > 0 for d in r)) / n), 4) if n else None))
    n_all = len(all_book) + len(all_rung)
    pooled = dict(
        n_book=len(all_book), win_book=round(float(np.mean([d["net"] > 0 for d in all_book])), 4),
        n_rungs=len(all_rung), win_rungs=round(float(np.mean([d["ret"] > 0 for d in all_rung])), 4),
        rung_exits={k: int(sum(1 for d in all_rung if d["exit"] == k))
                    for k in ("rung_sl", "rung_tp", "rung_timeout")},
        n_all=n_all,
        win_all=round(float((sum(d["net"] > 0 for d in all_book) +
                             sum(d["ret"] > 0 for d in all_rung)) / n_all), 4))
    nb = np.array(nbook_vals, float)
    gr = np.array(gross_vals, float)
    exposure = dict(
        n_book_avg=round(float(nb.mean()), 3), n_book_max=int(nb.max()),
        gross_book_avg=round(float(gr.mean()), 4), gross_book_max=round(float(gr.max()), 4),
        dip_avg_concurrent=round(float(dip_minutes / total_live_min), 4),
        dip_max_concurrent=int(max_conc_dip),
        dip_notional_avg=round(float(dip_wminutes / total_live_min), 5),
        total_avg_open=round(float(nb.mean() + dip_minutes / total_live_min), 3),
        total_max_open=int(max_total),
        combined_gross_max=round(float(max_comb_gross), 4),
        combined_gross_peak=dict(shift=int(peak_gross_s), t=peak_gross_t),
        total_open_peak_t=peak_total_t,
        n_bars=int(len(nb)))
    out = dict(variant="R2B1D17BFG2", equity=eq,
               win_rates=dict(per_year=years, pooled=pooled, per_shift=shifts,
                              open_book_positions_at_end=int(open_left),
                              note="book = v213 position episodes entry->flat/sign-change, net of maker/taker fees, funding excluded; rungs = FIFO fill->exit pairs, engine ret net of rung fees; year = ENTRY time in anchor year; pooled over 4 phase sub-accounts"),
               exposure=exposure,
               checks=dict(trade_months_compound_vs_net=eq["checks"]["prod_minus_net"],
                           shifts_match_1e9=[json.loads((HERE / f"check_s{s}.json").read_text())["match_1e9"]
                                             for s in range(4)]))
    bf = json.loads((HERE.parent / "oc_kpi" / "results.json").read_text())
    assert bf["variant"] == "R2B1D17BF"
    out["reference_BF"] = bf
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("pooled", pooled, flush=True)
    print("years", [(y["anchor"][:4], y["n_all"], y["win_all"]) for y in years], flush=True)
    print("exposure", exposure, flush=True)


if __name__ == "__main__":
    main()
