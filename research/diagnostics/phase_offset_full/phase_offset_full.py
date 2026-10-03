"""Dev-only diagnostic (not a registered version): how much of the DEPLOYED pipelines' dev return is 4h-phase luck?

The whole trade-mode pipeline (book + dips) of v367 (M5), v362 (M4), v340 (M2) and v321 (R2) is replayed on 4h grids shifted by
s = 0 / 1 / 2 / 3 hours, set up exactly as backend/history_tm.simulate (research_books_d2, v221.KW + KW_OVERRIDE, v216 G2 grid policy,
M-series pullback entry 0.75 sigma_4h / n_valid 3 / book_mult 0.75 / M5 tighten), with three changes:
  - engine inputs from phase_offset_dips.prep_grid on the shifted grid (identical to engine_user.prepare at s = 0), plus the funding flag:
    holding bar (T, T + 4h] pays the adverse long funding when a settlement 00/08/16 UTC falls inside it (each settlement in exactly one bar);
  - books on the shifted grid: the latest standard-grid book row r <= t_s (forward fill; r is decided at r + 4h <= t_s + 4h, no look-ahead);
  - the learned dip agents (keyed by standard holding bars) are switched OFF on every phase (size 1, TP m_sleeve_tp = 1.0); the s = 0 run
    WITH the agents (deployed form) is the reference row and must reproduce history_tm's dev4.
Periods: dev = the four dev years 2021-09-24 .. 2025-09-23 (nothing after 2025-09-23 is simulated), pre = 2020-06-01 .. 2021-09-23 where the
research books do not exist -> DIP-ONLY (books 0, pipeline dip rules, no agents). Also a dev DIP-ONLY row for the same comparison.
Usage: phase_offset_full.py <shift> <dev|pre>  -> runs/<period>_s<shift>.json ; aggregate.py builds the table.
Nothing here is selected or tuned.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent / "runs"
PIPES = ("v367", "v362", "v340", "v321")
DEV0, DEV1 = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")
PRE0, PRE1 = pd.Timestamp("2020-06-01", tz="UTC"), pd.Timestamp("2021-09-24", tz="UTC")
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prep_idx(M, idx, shift_h, syms):
    """phase_offset_dips.prep_grid on an EXPLICIT decision index (the standard engine index shifted by shift_h), float32 cube.

    Needed for an exact s = 0 reproduction of engine_user.prepare: the standard index starts at the first anchor (no warm-up, so sig4
    and the vol target are NaN / 1 for the first 20 days exactly as deployed), it lacks 2024-09-23 04:00..20:00 (a quirk of the v154
    book index, kept on every phase), and v172.cube_ohlc stores the minute cube as float32."""
    sh = pd.Timedelta(hours=shift_h)
    n, na = len(idx), len(syms)
    cube = {k: np.full((n, 240, na), np.nan, dtype=np.float32) for k in ("open", "high", "low", "close")}
    opens = pd.DataFrame(index=idx, columns=syms, dtype=float)
    hold = pd.Index(idx + pd.Timedelta(hours=4))
    for j, s in enumerate(syms):
        m = M[s]
        m = m[(m.index >= idx[0]) & (m.index < idx[-1] + pd.Timedelta(hours=8))]
        start = (m.index - sh).floor("4h") + sh
        row = hold.get_indexer(start)
        ok = row >= 0
        off = ((m.index - start).total_seconds() // 60).astype(int)
        for k in cube:
            cube[k][row[ok], off[ok], j] = m[k].to_numpy(float)[ok]
        first = m[m.index == start]["open"]
        opens[s] = pd.Series(first.to_numpy(), index=first.index).reindex(idx)
    for k in cube:
        X = cube[k]
        for mm in range(1, 240):
            miss = np.isnan(X[:, mm, :])
            X[:, mm, :][miss] = X[:, mm - 1, :][miss]
    o = opens
    sig4 = o.pct_change().rolling(360, min_periods=120).std().to_numpy()
    return opens, dict(idx=idx, cols=list(syms), O=cube["open"], H=cube["high"], L=cube["low"], C=cube["close"], sig4=sig4,
                       o1=o.shift(-1).to_numpy(), o2=o.shift(-2).to_numpy(), settle=settle_flags(idx))


def settle_flags(idx):
    """True when a funding settlement (00/08/16 UTC) lies in the holding bar (idx + 4h, idx + 8h]."""
    end = idx + pd.Timedelta(hours=8)
    return np.asarray(end.floor("8h") > idx + pd.Timedelta(hours=4))


def pipe_setup(pipe, hist, v221, v216, idx, cols, agents):
    """history_tm.simulate's kw and trade dict (agents optional; lookups keyed by this grid's holding bars)."""
    kw = dict(v221.KW, **hist.KW_OVERRIDE.get(pipe, {}))
    if agents:
        tab = pd.read_parquet(hist.G2_TABLE if pipe == "v301" else hist.R2_TABLE)
        keys = [(pd.Timestamp(t), s, int(r)) for t, s, r in zip(tab["T"], tab["sym"], tab["rung"])]
        lsz, ltp = dict(zip(keys, tab["size"].astype(float))), dict(zip(keys, tab["tp"].astype(float)))
        rmap = hist.M3_R2_RUNG if pipe in ("v340", "v342", "v362", "v367") else {}
        kw["sleeve_fill_size"] = lambda i, a, r, f: lsz.get((idx[i] + pd.Timedelta(hours=4), cols[a], rmap.get(r, r)), 1.0)
        kw["sleeve_tp"] = lambda i, a, r, f: ltp.get((idx[i] + pd.Timedelta(hours=4), cols[a], rmap.get(r, r)), 1.0)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    if pipe in ("v315", "v340", "v342", "v362", "v367"):
        grid_pol = trade["policy"]
        trade = dict(trade, n_valid=3, policy=lambda i, a, st: {"open": 0.75} if st["pos"] == 0 else grid_pol(i, a, st))
        if pipe == "v367":
            pol5 = trade["policy"]
            trade["policy"] = lambda i, a, st: "tighten" if st["pos"] != 0 and st["sgn"] == 0 and st["upnl"] < 0 else pol5(i, a, st)
        if pipe in ("v340", "v342", "v362", "v367"):
            trade["book_mult"] = 0.75
    return kw, trade


def metrics(idx, eq, eq_min, eq_max, anchors, live0, live1, sh=pd.Timedelta(0)):
    """engine_user.summarize restricted to the given anchors (1m DD with minute-path peaks, as the engine)."""
    years = []
    for a in anchors:
        a0 = pd.Timestamp(a, tz="UTC") + sh  # the year on this phase's grid (same number of bars on every phase)
        mk = np.asarray((idx >= a0) & (idx < min(a0 + pd.Timedelta(days=365), live1)))
        first = int(np.argmax(mk))
        base = eq[first - 1] if first > 0 else 1.0
        e, em, ex = eq[mk] / base, eq_min[mk] / base, eq_max[mk] / base
        pk = np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, ex)]))[1:]
        years.append(dict(anchor=a, net_pct=round(100 * float(e[-1] - 1), 2), dd_1m_pct=round(100 * float(np.max(1 - np.minimum(e, em) / pk)), 2)))
    full = np.asarray((idx >= live0) & (idx < live1))
    first = int(np.argmax(full))
    base = eq[first - 1] if first > 0 else 1.0
    e, em, ex = eq[full] / base, eq_min[full] / base, eq_max[full] / base
    peak = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
    peak1 = np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, ex)]))[1:]
    months = (live1 - live0).days / (365 / 12)
    return dict(yearly=years, total_pct=round(100 * float(e[-1] - 1), 2), monthly_geo=round(100 * float(e[-1] ** (1 / months) - 1), 3),
                dd_4h=round(100 * float(np.max(1 - e / peak)), 2), dd_1m=round(100 * float(np.max(1 - np.minimum(e, em) / peak1)), 2))


def book_win(v221, events, live0, live1):
    ts = v221.v216.v213.trade_stats(events).get("dev", {})
    rr = [float(e["ret"]) for e in events if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and live0 <= pd.Timestamp(e["t"]) < live1 + pd.Timedelta(hours=8)]
    nb, wb = ts.get("trades") or 0, ts.get("win_rate") or 0.0
    n = nb + len(rr)
    return dict(book_trades=nb, book_win=wb if nb else None, rungs=len(rr), rung_win=round(float(np.mean(np.array(rr) > 0)), 4) if rr else None,
                win_all=round((wb * nb + sum(r > 0 for r in rr)) / n, 4) if n else None)


def main(shift, period, stale=0):
    """stale > 0 (control): the full pipeline without agents on this grid with the books lagged by `stale` more rows (4h each)."""
    t_start = time.time()
    pod = _load("pod_full", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = _load("history_tm_full", ROOT / "backend/history_tm.py")
    v221 = _load("v221_full", RD / "v221/v221_grid_hysteresis.py")
    fw = _load("forward_v205_full", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216
    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
                                                                                 eq_max=(eq if eq_max is None else eq_max).copy(), stats=stats) or {}
    p0, p1 = (DEV0, DEV1) if period == "dev" else (PRE0, PRE1)
    sh = pd.Timedelta(hours=shift)
    live0, live1 = p0 + sh, p1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _ = eu.er.v154_books()
    if period == "dev":  # the standard engine index up to two rows past the dev end (o1 / o2 of the last dev bar), shifted
        std_idx = books154.index[books154.index <= DEV1 + pd.Timedelta(hours=4)]
    else:
        std_idx = pd.date_range(PRE0, PRE1 + pd.Timedelta(hours=4), freq="4h")
    M = pod.minutes()
    opens, prep = prep_idx(M, std_idx + sh, shift, list(books154.columns))
    del M
    idx = prep["idx"]
    cols = list(prep["cols"])
    assert cols == list(books154.columns)
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)  # latest standard row r <= t_s (identity at s = 0)
    if shift == 0:
        assert (books.index == idx).all()
    zero = pd.DataFrame(0.0, index=idx, columns=cols)
    anchors = ANCH if period == "dev" else ()
    runs = []
    for pipe in PIPES:
        jobs = [("full_noagents", books, False), ("diponly_noagents", zero, False)] if period == "dev" else [("diponly_noagents", zero, False)]
        if stale:
            jobs = [(f"full_noagents_stale{4 * stale}h", books.shift(stale).fillna(0.0), False)]
        if period == "dev" and shift == 0 and not stale:
            jobs.insert(0, ("full_agents", books, True))
        for tag, bk, agents in jobs:
            t0 = time.time()
            kw, trade = pipe_setup(pipe, hist, v221, v216, idx, cols, agents)
            events = []
            eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=events, **kw)
            m = metrics(cap["idx"], cap["eq"], cap["eq_min"], cap["eq_max"], anchors, live0, live1, sh)
            if period == "pre":  # halves as the earlier pre-2021 diagnostic, and the first bar actually traded
                eqs = pd.Series(cap["eq"], index=cap["idx"])
                live = eqs[(eqs.index >= live0) & (eqs.index < live1)]
                moved = live[live.diff().fillna(0) != 0]
                m["first_traded_bar"] = str(moved.index[0]) if len(moved) else None
                cut = pd.Timestamp("2021-01-01", tz="UTC") + sh
                b = float(live[live.index < cut].iloc[-1])
                m["h1_2020_pct"] = round(100 * (b - 1), 2)
                m["h2_2021_pct"] = round(100 * (float(live.iloc[-1]) / b - 1), 2)
            if period == "dev":
                g4 = np.prod([1 + y["net_pct"] / 100 for y in m["yearly"]]) ** (1 / 4)
                m["monthly_dev4"] = round(100 * (g4 ** (1 / 12) - 1), 3)
            m.update(book_win(v221, events, live0, live1))
            m["stats"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()}
            eq_end = pd.Series(cap["eq"], index=cap["idx"] + pd.Timedelta(hours=8))  # equity at the end of each holding bar
            eq_end = eq_end[(cap["idx"] >= live0 - pd.Timedelta(hours=4)) & (cap["idx"] < live1)]
            runs.append(dict(pipe=pipe, tag=tag, shift=shift, period=period, **m,
                             eq_end={str(k): float(v) for k, v in eq_end.items()}))
            print(pipe, tag, "s", shift, period, m.get("monthly_dev4", m["monthly_geo"]), [y["net_pct"] for y in m["yearly"]],
                  "DD1m", m["dd_1m"], "win", m["book_win"], f"{time.time() - t0:.0f}s", flush=True)
    OUT.mkdir(exist_ok=True)
    meta = dict(shift_h=shift, period=period, live=[str(live0), str(live1)], settle_bars=int(prep["settle"].sum()), bars=len(idx),
                note="funding: adverse long 0.0001 on the bar that contains a settlement; agents off except tag full_agents", secs=round(time.time() - t_start))
    (OUT / f"{period}_s{shift}{f'_stale{stale}' if stale else ''}.json").write_text(json.dumps(dict(meta=meta, runs=runs), default=str))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
