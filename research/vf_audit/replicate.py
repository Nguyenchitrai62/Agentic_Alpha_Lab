"""Blind replication of vf W9 hidden-year combo spec (Part A).

Reads ONLY: data/raw/ma_ribbon_20260924/ (via patterns.common loaders),
never the leader files listed in OPENCODE_VF_W9_AUDIT.md.

Spec recap:
- Book T, Book D, Target = 0.65*(0.5*T+0.5*D), decided at 4h close t, traded at open t+1.
- Window open_time in [2025-09-24, 2026-09-23 20:00 UTC]; start flat; liquidate at final close.
- Normal fee 0.0002 on traded notional; stress 0.0006 fee + 0.0005 adverse slippage.
- Long funding 0.0001 per fundingTime in [open_t, open_t+1) on long notional; shorts 0.

Assumptions (documented for audit, all causal):
A1. Daily SMA50/200 are rolling means of daily close with min_periods=full window.
A2. Daily bar availability time = its close_time; 4h bar joins last daily with
    daily.close_time <= h4.close_time (merge_asof backward). Same-millisecond
    close (e.g. 20:00 4h and daily) counts as closed.
A3. EMA20/200 on 4h close via pandas ewm(span, adjust=False, min_periods=span).mean().
    L = (close > EMA20) & (EMA20 > EMA200); NaN -> False.
A4. T is edge-triggered: enters 1 on rising edge of L (L[t] & ~L[t-1], L[-1]=False
    for first row) only if d[t] != -1; holds while L true; else 0. A blocked edge
    (d==-1) does NOT arm a later entry while L stays true; next entry needs a new edge.
A5. Donchian uses strictly previous bars (exclusive of current): long_entry =
    close[t] > max(high[t-55:t]) requiring t>=55; long_exit = close[t] <= min(low[t-10:t])
    requiring t>=10; short_entry = close[t] < min(low[t-55:t]) & (d[t]==-1) requiring
    t>=55; short_exit = close[t] >= max(high[t-10:t]) requiring t>=10.
A6. D state machine with long priority, same-bar flip allowed after an exit:
    prev=+1: if long_exit: D = -1 if short_entry else 0; else D=+1 (stay even if short_entry).
    prev=-1: if short_exit: D = +1 if long_entry else 0; else D=-1 (stay even if long_entry).
    prev=0: D = +1 if long_entry elif short_entry then -1 else 0.
    "Short never overlaps long" enforced by long priority above.
A7. Target[t] = 0.65*(0.5*T[t]+0.5*D[t]) in {+0.65,+0.325,0,-0.325}.
A8. Portfolio: equity indexed 100 at window open[0]. Position quantity Q (BTC, signed)
    fixed between target changes. At trade open p (open[j], j>=1): desired=target[j-1];
    if desired != cur: Q_new = desired*E_before/p; traded_notional=|Q_new-Q_old|*p;
    fee = rate*traded_notional; stress adds 0.0005*traded_notional slippage (equity deduction).
    E_after = E_before - fee - slip. PnL over [open[j], next]: Q*(P_next-P_open[j]).
    Funding per interval [open[j], open[j+1]): nF = count(fundingTime in [open[j],open[j+1]));
    if Q>0: fund = nF*0.0001*(Q*open[j]) (open-price notional proxy); shorts 0.
    Final bar holds to close[N-1] (not open[N]); liquidation at close[N-1] pays fee/slip
    on |Q|*close. Decision target[N-1] is NOT executed (would trade after liquidation).
A9. Drawdown close = peak-to-trough on equity sampled at 4h closes (after funding, before gap
    to next open? equity_close defined in code). Intrabar worst per bar: long->low, short->high,
    flat->close; worst equity = E_after_open_trade + Q*(worst-open) - funding_bar (conservative:
    funding charged at worst point). Intrabar DD computed over interleaved [worst,close] sequence.
A10. Target-change list records decision bars (open_time) where target differs from previous
    decision (with flat 0 before first). Trade time = next bar open (None for final bar).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common

OUT = Path(__file__).resolve().parent / "replication.json"
START = pd.Timestamp("2025-09-24", tz="UTC")
END_OPEN = pd.Timestamp("2026-09-23 20:00", tz="UTC")


def compute_d_for_4h(b4: pd.DataFrame, b1d: pd.DataFrame) -> pd.Series:
    dly = b1d.sort_values("close_time").reset_index(drop=True).copy()
    dly["sma50"] = dly["close"].rolling(50, min_periods=50).mean()
    dly["sma200"] = dly["close"].rolling(200, min_periods=200).mean()
    dly["d_dly"] = 0
    long_m = (dly["close"] > dly["sma50"]) & (dly["sma50"] > dly["sma200"])
    short_m = (dly["close"] < dly["sma50"]) & (dly["sma50"] < dly["sma200"])
    dly.loc[long_m, "d_dly"] = 1
    dly.loc[short_m, "d_dly"] = -1
    left = b4.sort_values("close_time").reset_index(drop=True)
    right = dly[["close_time", "d_dly"]].sort_values("close_time")
    j = pd.merge_asof(left[["close_time"]], right, on="close_time", direction="backward")
    d = j["d_dly"].fillna(0).astype(int)
    return pd.Series(d.to_numpy(), index=b4.index)


def compute_L(b4: pd.DataFrame) -> pd.Series:
    c = b4["close"]
    ema20 = c.ewm(span=20, adjust=False, min_periods=20).mean()
    ema200 = c.ewm(span=200, adjust=False, min_periods=200).mean()
    L = (c > ema20) & (ema20 > ema200)
    return L.fillna(False)


def compute_T(L: pd.Series, d: pd.Series) -> pd.Series:
    n = len(L)
    T = np.zeros(n, dtype=np.int8)
    in_long = False
    prev_L = False
    Lv = L.to_numpy().astype(bool)
    dv = d.to_numpy().astype(int)
    for i in range(n):
        li = bool(Lv[i])
        di = int(dv[i])
        if not in_long:
            if li and (not prev_L):
                if di != -1:
                    in_long = True
                    T[i] = 1
                else:
                    T[i] = 0
            else:
                T[i] = 0
        else:
            if li:
                T[i] = 1
            else:
                in_long = False
                T[i] = 0
        prev_L = li
    return pd.Series(T, index=L.index)


def compute_D(b4: pd.DataFrame, d: pd.Series) -> pd.Series:
    n = len(b4)
    close = b4["close"].to_numpy()
    high = b4["high"].to_numpy()
    low = b4["low"].to_numpy()
    dv = d.to_numpy().astype(int)
    D = np.zeros(n, dtype=np.int8)
    prev = 0
    for i in range(n):
        if i >= 55:
            long_entry = bool(close[i] > np.max(high[i - 55:i]))
            short_base = bool(close[i] < np.min(low[i - 55:i]))
        else:
            long_entry = False
            short_base = False
        short_entry = bool(short_base and (dv[i] == -1)) if i >= 55 else False
        if i >= 10:
            long_exit = bool(close[i] <= np.min(low[i - 10:i]))
            short_exit = bool(close[i] >= np.max(high[i - 10:i]))
        else:
            long_exit = False
            short_exit = False
        if prev == 1:
            if long_exit:
                cur = -1 if short_entry else 0
            else:
                cur = 1
        elif prev == -1:
            if short_exit:
                cur = 1 if long_entry else 0
            else:
                cur = -1
        else:
            if long_entry:
                cur = 1
            elif short_entry:
                cur = -1
            else:
                cur = 0
        D[i] = cur
        prev = cur
    return pd.Series(D, index=b4.index)


def max_dd(equity: np.ndarray) -> float:
    e = np.asarray(equity, float)
    peak = np.maximum.accumulate(e)
    dd = (e - peak) / peak
    return float(dd.min())


def simulate(w: pd.DataFrame, targets_w: np.ndarray, funding: pd.DataFrame,
             fee_rate: float, slip_rate: float):
    n = len(w)
    opens = w["open"].to_numpy(float)
    closes = w["close"].to_numpy(float)
    highs = w["high"].to_numpy(float)
    lows = w["low"].to_numpy(float)
    ot = pd.to_datetime(w["open_time"], utc=True).reset_index(drop=True)
    # next opens: for j<N-1 use opens[j+1]; last uses close[N-1] as exit
    fts = pd.to_datetime(funding["fundingTime"], utc=True).reset_index(drop=True)
    # count funding per interval [open[j], open[j+1]) (last: [open[N-1], close[N-1]+1ms])
    E = 100.0
    Q = 0.0
    cur = 0.0
    total_fees = 0.0
    total_slip = 0.0
    total_funding = 0.0
    n_exec_trades = 0
    eq_close = np.zeros(n)
    eq_worst = np.zeros(n)
    for j in range(n):
        pj = opens[j]
        if j == 0:
            E_after = E  # start flat, no trade at first open
        else:
            desired = float(targets_w[j - 1])
            if desired != cur:
                Q_new = desired * E / pj if pj != 0 else 0.0
                notional = abs(Q_new - Q) * pj
                fee = fee_rate * notional
                slip = slip_rate * notional
                E = E - fee - slip
                total_fees += fee
                total_slip += slip
                n_exec_trades += 1
                Q = Q_new
                cur = desired
            E_after = E
        # funding count for this bar's holding interval
        if j < n - 1:
            lo = ot[j]
            hi = ot[j + 1]
            p_next = opens[j + 1]
        else:
            lo = ot[j]
            # close time = open+4h-1ms; use close_time column for upper bound inclusive
            hi = pd.to_datetime(w.iloc[j]["close_time"], utc=True) + pd.Timedelta(milliseconds=1)
            p_next = closes[j]
        nF = int((((fts >= lo) & (fts < hi))).sum())
        fund = 0.0
        if Q > 0 and nF > 0:
            fund = nF * 0.0001 * (Q * pj)
            total_funding += fund
        # equity at close of bar j
        E_c = E_after + Q * (closes[j] - pj) - fund
        eq_close[j] = E_c
        if Q > 0:
            E_w = E_after + Q * (lows[j] - pj) - fund
        elif Q < 0:
            E_w = E_after + Q * (highs[j] - pj) - fund  # Q<0, high>open -> negative
        else:
            E_w = E_after
        eq_worst[j] = E_w
        # roll to next open (gap close->open_next) for j<N-1
        if j < n - 1:
            E = E_c + Q * (opens[j + 1] - closes[j])
        else:
            E = E_c
    # liquidate at final close at price closes[-1]; Q currently held
    liq_fee = 0.0
    liq_slip = 0.0
    if Q != 0:
        liq_notional = abs(Q) * closes[-1]
        liq_fee = fee_rate * liq_notional
        liq_slip = slip_rate * liq_notional
        E = E - liq_fee - liq_slip
        total_fees += liq_fee
        total_slip += liq_slip
        n_exec_trades += 1
        Q = 0.0
    # drawdowns
    dd_close = max_dd(eq_close)
    inter = np.empty(2 * n)
    inter[0::2] = eq_worst
    inter[1::2] = eq_close
    dd_intra = max_dd(inter)
    return {
        "final_equity": float(E),
        "eq_close": eq_close,
        "eq_worst": eq_worst,
        "total_fees": float(total_fees),
        "total_slip": float(total_slip),
        "total_funding": float(total_funding),
        "n_exec_trades": int(n_exec_trades),
        "dd_close": float(dd_close),
        "dd_intra": float(dd_intra),
    }


def main():
    b4 = common.load_bars("4h", include_opened_year=True).sort_values("open_time").reset_index(drop=True)
    b1d = common.load_bars("1d", include_opened_year=True).sort_values("open_time").reset_index(drop=True)
    funding = common.load_funding(include_opened_year=True).sort_values("fundingTime").reset_index(drop=True)
    d = compute_d_for_4h(b4, b1d)
    L = compute_L(b4)
    T = compute_T(L, d)
    D = compute_D(b4, d)
    target = 0.65 * (0.5 * T.to_numpy(float) + 0.5 * D.to_numpy(float))
    full = pd.DataFrame({"open_time": pd.to_datetime(b4["open_time"], utc=True),
                         "close_time": pd.to_datetime(b4["close_time"], utc=True),
                         "open": b4["open"].to_numpy(float), "high": b4["high"].to_numpy(float),
                         "low": b4["low"].to_numpy(float), "close": b4["close"].to_numpy(float),
                         "d": d.to_numpy(int), "L": L.to_numpy(bool).astype(int),
                         "T": T.to_numpy(int), "D": D.to_numpy(int), "target": target})
    m = (full["open_time"] >= START) & (full["open_time"] <= END_OPEN)
    w = full.loc[m].reset_index(drop=True)
    assert len(w) == 2190, len(w)
    targets_w = w["target"].to_numpy(float)
    # target changes (decision basis, flat 0 before first)
    changes = []
    prev = 0.0
    for idx, row in w.iterrows():
        if float(row["target"]) != prev:
            trade_ot = w.iloc[idx + 1]["open_time"].isoformat() if idx + 1 < len(w) else None
            changes.append({"decision_open_time": row["open_time"].isoformat(),
                            "decision_close_time": row["close_time"].isoformat(),
                            "trade_open_time": trade_ot,
                            "prev_target": prev, "new_target": float(row["target"]),
                            "T": int(row["T"]), "D": int(row["D"]), "d": int(row["d"])})
            prev = float(row["target"])
    # executed changes exclude final-bar decision (no trade after liquidation)
    n_exec_changes = sum(1 for c in changes if c["trade_open_time"] is not None)
    # note: if final bar is a change, its trade_open_time is None (open[N] outside window)
    normal = simulate(w, targets_w, funding, fee_rate=0.0002, slip_rate=0.0)
    stress = simulate(w, targets_w, funding, fee_rate=0.0006, slip_rate=0.0005)
    E0 = 100.0

    def pack(r):
        return {"final_equity": r["final_equity"],
                "net_pct": (r["final_equity"] / E0 - 1) * 100.0,
                "fees_abs": r["total_fees"], "fees_pct": r["total_fees"] / E0 * 100.0,
                "slippage_abs": r["total_slip"], "slippage_pct": r["total_slip"] / E0 * 100.0,
                "funding_abs": r["total_funding"], "funding_pct": r["total_funding"] / E0 * 100.0,
                "n_exec_trades_incl_liquidation": r["n_exec_trades"],
                "max_dd_close_pct": r["dd_close"] * 100.0,
                "max_dd_intrabar_pct": r["dd_intra"] * 100.0}

    out = {
        "spec": "OPENCODE_VF_W9_AUDIT blind replication; see replicate.py assumptions A1-A10",
        "window": {"start": START.isoformat(), "end_open": END_OPEN.isoformat(),
                   "n_bars": int(len(w)),
                   "first_close": w.iloc[0]["close_time"].isoformat(),
                   "final_close": w.iloc[-1]["close_time"].isoformat(),
                   "final_close_price": float(w.iloc[-1]["close"])},
        "data_rows": {"klines_4h_full": int(len(b4)), "klines_1d_full": int(len(b1d)),
                      "funding_full": int(len(funding))},
        "targets": {"unique_values": sorted(map(float, np.unique(targets_w))),
                    "counts": {str(k): int((targets_w == k).sum()) for k in np.unique(targets_w)},
                    "n_target_changes_decision_basis": int(len(changes)),
                    "n_target_changes_executed_excl_final": int(n_exec_changes)},
        "normal": pack(normal),
        "stress": pack(stress),
        "target_changes": changes,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps({"normal": out["normal"], "stress": out["stress"],
                      "n_changes": len(changes), "n_exec": n_exec_changes}, indent=2))


if __name__ == "__main__":
    main()
