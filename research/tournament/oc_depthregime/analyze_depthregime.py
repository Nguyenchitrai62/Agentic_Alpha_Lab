"""oc_depthregime: split R2B1D17BF deep/shallow dip P&L by bar-open regimes.

DIAGNOSTIC only (see PLAN.md, pre-registered before any outcome was computed).
Reads oc_kpi events_s{0..3}.parquet + hourly_ext.parquet (majors only).
No 1m data. One process, RAM < 1 GB.
Writes results.json in this folder.
Usage: .venv/Scripts/python.exe research/tournament/oc_depthregime/analyze_depthregime.py
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi"
EXT = HERE.parent / "ext"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_END = pd.Timestamp("2026-09-24", tz="UTC")
EMBARGO = pd.Timedelta(days=7)
H4_HOURS = {0, 4, 8, 12, 16, 20}


def year_of(t) -> int | None:
    t = pd.Timestamp(t)
    for k in range(5):
        end = ANCH[k + 1] if k < 4 else ANCH_END
        if ANCH[k] <= t < end:
            return k
    return None


def pair_rungs(ev: pd.DataFrame):
    """FIFO per symbol. Returns list of dicts + (unpaired, left_open)."""
    pend: dict[str, deque] = {}
    out = []
    unpaired = 0
    for r in ev.itertuples():
        if r.kind == "rung_fill":
            pend.setdefault(r.symbol, deque()).append(r)
        elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
            q0 = pend.get(r.symbol)
            if q0:
                f0 = q0.popleft()
                out.append(dict(
                    fill_t=pd.Timestamp(f0.t), exit_t=pd.Timestamp(r.t),
                    symbol=r.symbol, depth=float(f0.rung),
                    exit=r.kind, weight=float(r.weight),
                    ret=float(r.ret),
                    pnl=float(r.weight) * float(r.ret),
                    gross=float(r.weight)))
            else:
                unpaired += 1
    left = sum(len(q) for q in pend.values())
    return out, unpaired, left


def floor_h4(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    h = (ts.hour // 4) * 4
    return pd.Timestamp(ts.year, ts.month, ts.day, h, tz="UTC")


def build_4h(hourly: pd.DataFrame):
    """Returns dict coin -> DataFrame indexed by T0 with open4, sigma4, ma1200, btc30 parts."""
    out = {}
    for coin in MAJORS:
        g = hourly[hourly["sym"] == coin].sort_values("t")
        g = g[(g["t"].dt.hour.isin(H4_HOURS)) & (g["t"].dt.minute == 0)]
        g = g[g["t"] < ANCH_END].drop_duplicates("t").set_index("t").sort_index()
        o = g["open"].astype(float)
        sigma = o.pct_change().rolling(360, min_periods=120).mean if False else o.pct_change().rolling(360, min_periods=120).std(ddof=1)
        out[coin] = pd.DataFrame({"open": o, "sigma": sigma})
    btc = out["BTCUSDT"]["open"]
    ma1200 = btc.rolling(1200, min_periods=600).mean()
    return out, btc, ma1200


def main():
    hourly = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "open", "sym"])
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    per4h, btc_open, ma1200 = build_4h(hourly)
    grid = btc_open.index  # standard 4h grid (BTC-complete; majors share the grid)
    grid_int = grid.values.astype("datetime64[ns]").astype("int64")

    # walk-forward sigma tercile cutoffs per (year, coin): percentiles of sigma with T < A-7d
    cutoffs: dict[str, dict[str, tuple[float, float]]] = {}
    for coin in MAJORS:
        s = per4h[coin]["sigma"].dropna()
        cutoffs[coin] = {}
        for k in range(5):
            hist = s[s.index < (ANCH[k] - EMBARGO)]
            p33, p66 = float(hist.quantile(0.33)), float(hist.quantile(0.66))
            cutoffs[coin][str(k)] = (p33, p66)

    # ---- pair rungs over 4 shifts ----
    all_rungs = []
    checks = dict(unpaired_exits=0, open_rungs_left=0)
    fills_for_n = []  # (fill_t, symbol) for n_evt
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        ev = ev.sort_values("t").reset_index(drop=True)
        rungs, unpaired, left = pair_rungs(ev)
        checks["unpaired_exits"] += int(unpaired)
        checks["open_rungs_left"] += int(left)
        for d in rungs:
            d["shift"] = s
            d["year"] = year_of(d["fill_t"])
            all_rungs.append(d)
            fills_for_n.append((d["fill_t"], d["symbol"]))
    # n_evt: distinct other majors with a rung_fill in [t-60min, t]
    fall = sorted(fills_for_n)  # sort by time
    from bisect import bisect_left
    times = [t for t, _ in fall]
    syms = [c for _, c in fall]
    # per-fill: walk with pointer (n small enough for bisect per fill; ~21k fills fine)
    import collections
    # group times per coin for fast range queries
    per_coin = {c: sorted(t for t, c in fall if c == c) for c in MAJORS}
    # simpler: for each rung, count other coins with any fill in window
    # n_evt: distinct other majors with a rung_fill in [t-60min, t], SAME shift
    # (same sub-account; pooled wall-clock counts would mix the 4 phase
    #  sub-accounts and erase all variation — fixed post-PLAN, see REPORT).
    shift_fills: dict[int, list] = {}
    for d in all_rungs:
        shift_fills.setdefault(d["shift"], []).append((d["fill_t"], d["symbol"]))
    per_coin_shift = {}
    for s, lst in shift_fills.items():
        for c in MAJORS:
            per_coin_shift[(s, c)] = sorted(t for t, cc in lst if cc == c)
    n_list = []
    for d in all_rungs:
        t = d["fill_t"]
        lo = t - pd.Timedelta(minutes=60)
        n = 0
        for c in MAJORS:
            if c == d["symbol"]:
                continue
            arr = per_coin_shift[(d["shift"], c)]
            j = bisect_left(arr, lo)
            if j < len(arr) and arr[j] <= t:
                n += 1
        n_list.append(n)
    for d, n in zip(all_rungs, n_list):
        d["n_evt"] = int(n)

    # ---- attach regimes ----
    btc_o = btc_open
    btc_idx = btc_o.index
    for d in all_rungs:
        t0 = floor_h4(d["fill_t"])
        d["T0"] = t0
        # bear (v410): open[T0] < MA1200[T0], NaN->bull
        try:
            o = float(btc_o.loc[t0])
            m = float(ma1200.loc[t0])
            d["bear"] = "bear" if (np.isfinite(o) and np.isfinite(m) and o < m) else "bull"
        except KeyError:
            d["bear"] = "bull"
        # btc30: open[T0]/open[T0-180]-1
        try:
            j = btc_idx.get_loc(t0)
            if isinstance(j, slice):
                d["btc30"] = "unknown"
            elif j >= 180:
                o0 = float(btc_o.iloc[j])
                o1 = float(btc_o.iloc[j - 180])
                r = o0 / o1 - 1 if o1 else float("nan")
                d["btc30"] = "up" if (np.isfinite(r) and r > 0) else ("down" if np.isfinite(r) else "unknown")
            else:
                d["btc30"] = "unknown"
        except KeyError:
            d["btc30"] = "unknown"
        # sigma tercile (walk-forward per coin)
        coin, y = d["symbol"], d["year"]
        try:
            sg = float(per4h[coin]["sigma"].loc[t0])
        except KeyError:
            sg = float("nan")
        d["sigma_val"] = sg
        if y is None or not np.isfinite(sg):
            d["sigma_terc"] = "unknown"
        else:
            p33, p66 = cutoffs[coin][str(y)]
            d["sigma_terc"] = "low" if sg <= p33 else ("high" if sg > p66 else "mid")
        # hour bucket
        h = pd.Timestamp(d["fill_t"]).hour
        d["hour"] = "h00_05" if h < 6 else ("h06_11" if h < 12 else ("h12_17" if h < 18 else "h18_23"))
        d["n_bucket"] = "n0" if d["n_evt"] == 0 else ("n1" if d["n_evt"] == 1 else "n2p")
        d["group"] = "deep" if d["depth"] in (4.0, 5.0) else "shallow"

    # drop fills outside anchor years (expected 0)
    outside = sum(1 for d in all_rungs if d["year"] is None)
    checks["outside_anchor_years"] = int(outside)
    rows = [d for d in all_rungs if d["year"] is not None]
    checks["n_rungs"] = len(rows)
    checks["unknown_btc30"] = sum(1 for d in rows if d["btc30"] == "unknown")
    checks["unknown_sigma"] = sum(1 for d in rows if d["sigma_terc"] == "unknown")

    def summ(v):
        n = len(v)
        pnl = float(sum(r["pnl"] for r in v))
        gross = float(sum(r["gross"] for r in v))
        wins = sum(1 for r in v if r["ret"] > 0)
        return dict(n=n, pnl_sub_pct=round(pnl * 100, 3),
                    pnl_mix_pct=round(pnl / 4 * 100, 3),
                    win=round(wins / n, 4) if n else None,
                    pnl_per_gross=round(pnl / gross, 5) if gross else None)

    dims = {"bear": ["bear", "bull"], "btc30": ["up", "down"],
            "sigma_terc": ["low", "mid", "high"],
            "n_evt": ["n0", "n1", "n2p"],
            "hour": ["h00_05", "h06_11", "h12_17", "h18_23"],
            "exit": ["rung_tp", "rung_sl", "rung_timeout"]}
    key_of = {"bear": "bear", "btc30": "btc30", "sigma_terc": "sigma_terc",
              "n_evt": "n_bucket", "hour": "hour", "exit": "exit"}
    tables = {}
    for dim, vals in dims.items():
        k = key_of[dim]
        t = {}
        for y in range(5):
            yd = {}
            for g in ("deep", "shallow"):
                gd = {}
                for v in vals:
                    sel = [r for r in rows if r["year"] == y and r["group"] == g and r[k] == v]
                    gd[v] = summ(sel)
                yd[g] = gd
            t[str(y)] = yd
        # pooled
        pd_ = {}
        for g in ("deep", "shallow"):
            gd = {}
            for v in vals:
                sel = [r for r in rows if r["group"] == g and r[k] == v]
                gd[v] = summ(sel)
            pd_[g] = gd
        t["pooled"] = pd_
        tables[dim] = t

    # year totals per group + deep sign count per regime value
    totals = {}
    for y in list(range(5)) + ["pooled"]:
        sel = rows if y == "pooled" else [r for r in rows if r["year"] == y]
        totals[str(y)] = {g: summ([r for r in sel if r["group"] == g]) for g in ("deep", "shallow")}
    deep_sign = {}
    for dim, vals in dims.items():
        k = key_of[dim]
        dd = {}
        for v in vals:
            signs = []
            for y in range(5):
                s = totals  # noqa
                sel = [r for r in rows if r["year"] == y and r["group"] == "deep" and r[k] == v]
                p = sum(r["pnl"] for r in sel) / 4 * 100
                signs.append(round(p, 3))
            dd[v] = dict(yearly_deep_mix_pct=signs,
                         n_years_ge0=sum(1 for x in signs if x >= 0),
                         all5_negative=all(x < 0 for x in signs))
        deep_sign[dim] = dd

    out = dict(
        variant="R2B1D17BF", diagnostic=True, selection_rule="none (diagnostic, no PROMISING rule)",
        methods=("FIFO rung pairing (copy of oc_contrib); year=FILL time in anchor year; "
                 "pnl=exit weight*engine ret (net of rung fees), pnl_mix=pnl_sub/4; "
                 "T0=floor(fill_t to standard 4h grid); bear=v410 BTC open4<MA1200 incl T0 min600 NaN->bull; "
                 "btc30=open4BTC[T0]/open4BTC[T0-180]-1 up iff >0; "
                 "sigma4=std of 4h-open simple returns trailing360/min120 at T0, tercile cutoffs=p33/p66 of "
                 "that coin's sigma with T<anchor-7d (walk-forward per year/coin); "
                 "n_evt=distinct other majors with >=1 rung_fill in [fill_t-60min,fill_t] "
                 "(event-based proxy for B1 n; exact 1m C<=O*(1-2.5sig) n NOT recomputed, no 1m read per LIGHT); "
                 "hour=UTC hour bucket of fill_t; exit=realised exit kind (not a pre-trade regime)."),
        anchors=[a.strftime("%Y-%m-%d") for a in ANCH],
        cutoffs_sigma={c: {k: [round(float(x[0]), 6), round(float(x[1]), 6)] for k, x in v.items()} for c, v in cutoffs.items()},
        totals=totals, tables=tables, deep_sign=deep_sign, checks=checks)
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("n_rungs", len(rows), "deep/shallow pooled:",
          totals["pooled"]["deep"]["n"], totals["pooled"]["shallow"]["n"], flush=True)
    print("deep pooled mix%", totals["pooled"]["deep"]["pnl_mix_pct"],
          "shallow pooled mix%", totals["pooled"]["shallow"]["pnl_mix_pct"], flush=True)
    print("checks", checks, flush=True)
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
