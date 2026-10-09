"""oc_mvrvrobust event table (Task 1, no engine run).

PLAN-fixed: gate flag per 4h bar T (STANDARD-grid proxy: 4h steps from
2021-09-24 00:00 UTC): g=1 iff frozen-M1 mult < 1 (finite z > 2.0).
Windows = maximal contiguous g=1 runs; episodes = windows merged if gap <= 14d.
Per window: start/end/days, BTC buy-hold return (xs_universe BTC daily closes,
labelled), TOTAL-equity window P&L for G2 vs M1 from cached
oc_lit_position/engine_runs.pkl 4-phase paths (labelled total-equity proxy).

Usage:
  .venv/Scripts/python.exe research/tournament/oc_mvrvrobust/compute_events.py
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from signals_mvrv import gate_mults

LIT = ROOT / "research" / "tournament" / "oc_lit_position"
XS = ROOT / "data" / "raw" / "xs_universe_20260924" / "BTCUSDT_1d.parquet"
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
MERGE_GAP = pd.Timedelta(days=14)


def grid_4h():
    t0 = pd.Timestamp("2021-09-24 00:00", tz="UTC")
    t1 = pd.Timestamp("2026-09-24 00:00", tz="UTC")
    return pd.date_range(t0, t1, freq="4h", tz="UTC")


def btc_daily():
    df = pd.read_parquet(XS, columns=["open_time", "close"])
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    day = df["open_time"].dt.floor("D")
    df = df.assign(day=day).groupby("day", as_index=True).last(numeric_only=False)
    df.index = pd.to_datetime(df.index, utc=True)
    return df["close"].astype(float)


def window_ret(eqs, t_idx, start, end):
    """4-phase-mean total-equity return over [start, end] from cached runs.

    eqs: dict shift -> (t array, eq array). Uses nearest t <= bound.
    """
    rs = []
    for s, (t, eq) in eqs.items():
        t = pd.to_datetime(t, utc=True)
        i0 = int(np.searchsorted(t.values.astype(np.int64), start.value) - 1)
        i1 = int(np.searchsorted(t.values.astype(np.int64), end.value) - 1)
        i0 = max(i0, 0)
        i1 = max(i1, i0 + 1)
        i1 = min(i1, len(eq) - 1)
        rs.append(float(eq[i1] / eq[i0] - 1.0))
    return float(np.mean(rs))


def main():
    T = grid_4h()
    z, m = gate_mults(T)
    g = (m < 1.0).astype(int)
    print("gated bars total:", int(g.sum()), "of", len(T), flush=True)
    # per-year gated share (cross-check vs REPORT 0/3.3/45.4/6.4%)
    for k in range(5):
        sel = (T >= ANCH[k]) & (T < ANCH[k] + pd.Timedelta(days=365))
        print(f"year {2021+k}: gated {int(g[sel].sum())}/{int(sel.sum())} "
              f"= {100*g[sel].mean():.1f}%", flush=True)
    # maximal contiguous windows
    idx = np.where(g == 1)[0]
    windows = []
    if len(idx):
        s = p = idx[0]
        for i in idx[1:]:
            if i == p + 1:
                p = i
                continue
            windows.append((s, p))
            s = p = i
        windows.append((s, p))
    wins = []
    for s, p in windows:
        wins.append(dict(start=str(T[s]), end=str(T[p]),
                         nbars=int(p - s + 1),
                         days=float((T[p] - T[s]).total_seconds() / 86400)))
    print("windows (strictly contiguous):", len(wins), flush=True)
    # merge episodes gap <= 14d
    episodes = []
    cur = None
    for s, p in windows:
        if cur is None:
            cur = [s, p]
            continue
        gap = T[s] - T[cur[1]]
        if gap <= MERGE_GAP:
            cur[1] = p
        else:
            episodes.append(tuple(cur))
            cur = [s, p]
    if cur is not None:
        episodes.append(tuple(cur))
    print("episodes (merged <=14d):", len(episodes), flush=True)

    close = btc_daily()
    runs = pickle.loads((LIT / "engine_runs.pkl").read_bytes())
    eqs = {}
    for s in range(4):
        for row in ("G2", "M1"):
            pass
        t = pd.to_datetime(pd.Series(runs[s]["G2"]["t"]), utc=True)
        eqs_g = (t, np.asarray(runs[s]["G2"]["eq"], float))
        t2 = pd.to_datetime(pd.Series(runs[s]["M1"]["t"]), utc=True)
        eqs_m = (t2, np.asarray(runs[s]["M1"]["eq"], float))
        eqs.setdefault("G2", {})[s] = eqs_g
        eqs.setdefault("M1", {})[s] = eqs_m

    def btc_ret(start, end):
        d0 = pd.Timestamp(start).floor("D")
        d1 = pd.Timestamp(end).floor("D")
        try:
            c0 = float(close.loc[d0])
            c1 = float(close.loc[d1])
            return float(c1 / c0 - 1.0)
        except KeyError:
            return None

    ev_rows = []
    for ei, (s, p) in enumerate(episodes):
        st, en = T[s], T[p]
        # member windows
        members = [(a, b) for a, b in windows if a >= s and b <= p]
        rg = window_ret(eqs["G2"], None, st, en)
        rm = window_ret(eqs["M1"], None, st, en)
        # per-anchor-year bar attribution (keys = anchor year 2021+k)
        years = {}
        for k in range(5):
            a0, a1 = ANCH[k], ANCH[k] + pd.Timedelta(days=365)
            sel = (T[s:p + 1] >= a0) & (T[s:p + 1] < a1)
            years[f"anchor_{2021 + k}"] = int(np.asarray(sel).sum())
        ev_rows.append(dict(
            episode=ei,
            start=str(st), end=str(en),
            nbars=int(p - s + 1),
            days=float((en - st).total_seconds() / 86400),
            n_windows=len(members),
            btc_ret=btc_ret(st, en),
            g2_window_ret=round(rg, 6),
            m1_window_ret=round(rm, 6),
            diff=round(rm - rg, 6),
            per_anchor_year_bars=years,
        ))
        print(f"E{ei}: {st.date()}..{en.date()} nbars={p-s+1} "
              f"days={(en-st).days} btc={ev_rows[-1]['btc_ret']} "
              f"G2={rg:.4f} M1={rm:.4f} diff={rm-rg:.4f} {years}", flush=True)

    out = dict(windows=wins, episodes=ev_rows,
               merge_gap_days=14,
               note=("TOTAL-equity window proxy from cached oc_lit_position "
                     "engine_runs.pkl 4-phase paths; BTC buy-hold from "
                     "xs_universe BTC daily closes."),
               gated_share={str(2021 + k): round(float(g[(T >= ANCH[k]) & (T < ANCH[k] + pd.Timedelta(days=365))].mean()), 4) for k in range(5)})
    (HERE / "events.json").write_text(json.dumps(out, indent=1))
    print("wrote events.json", flush=True)


if __name__ == "__main__":
    main()
