"""Blind replication of mj W17 majors TSMOM spec (Part A).

Spec source: OPENCODE_MJ_W17_AUDIT.md. Written WITHOUT reading leader code:
scripts/mj_tsmom_portfolio.py, scripts/mj_lab.py, research/mj_portfolio_risk.py,
artifacts/research/mj/.

Method (all causal, decided at 4h close t uses only data with availability <= t):
- universe: BTC, ETH, SOL, BNB, XRP.
- signal_i(t) = mean(sign(logC_t - logC_{t-42}), sign(logC_t - logC_{t-180}))
  (42 = 7d*6, 180 = 30d*6 4h bars, positional shift per asset), clipped at 0.
  Bear filter: 0 if last CLOSED daily bar (daily close_time <= 4h close_time)
  has close < SMA50 < SMA200 (inclusive rolling means on daily closes).
- vol_i(t) = std(last 180 4h log returns ending at t, ddof=1) * sqrt(6*365).
  raw = signal/vol else 0 when undefined/nonpositive.
- union grid = sorted union of 5 assets' 4h open_time. Missing asset: raw=0, r=0.
- port_r(t) = sum_i raw_{t-1} * r_t, r = 4h log return at t.
- pvol(t) = std(last 180 port_r ending at t, min 60, ddof=1) * sqrt(6*365).
  scale = min(0.3/pvol, 10), 0 if undefined/nonpositive. w_pre = raw*scale.
  cap: if sum|w|>3 scale down to 3. band: keep prev w unless |new-prev|>0.05.
- execution: decision at close t held over bar h=t+1; asset leg return =
  open_{h+1}/open_h - 1 (0 if either open missing/nonpositive).
  cost = 0.0002*sum|w_t - w_{t-1}| (banded, capped weights).
  funding cost = sum_i w_{i,t} * sum(rates with fundingTime in [open_h, open_{h+1})).
  period ret = sum w*ret - cost - funding; equity compounds from 1.0.
- window holding bars h with open_time in [2023-09-24 00:00, 2024-09-22 20:00] UTC
  (2190 bars = 365 days). t = previous union slot (h-4h); start flat (w=0 before).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ANN = np.sqrt(6 * 365)
W0 = pd.Timestamp("2023-09-24 00:00:00+00:00")
W1 = pd.Timestamp("2024-09-22 20:00:00+00:00")

BTC_4H = Path("data/raw/ma_ribbon_20260924/klines_4h.parquet")
BTC_1D = Path("data/raw/ma_ribbon_20260924/klines_1d.parquet")
BTC_F = Path("data/raw/ma_ribbon_20260924/funding.parquet")
XS = Path("data/raw/xs_universe_20260924")


def load_asset(sym):
    if sym == "BTCUSDT":
        b4 = pd.read_parquet(BTC_4H)
        b1 = pd.read_parquet(BTC_1D)
        f = pd.read_parquet(BTC_F)
    else:
        b4 = pd.read_parquet(XS / f"{sym}_4h.parquet")
        b1 = pd.read_parquet(XS / f"{sym}_1d.parquet")
        f = pd.read_parquet(XS / f"{sym}_funding.parquet")
    b4 = b4.sort_values("open_time").reset_index(drop=True)
    b1 = b1.sort_values("open_time").reset_index(drop=True)
    for c in ("open_time", "close_time"):
        b4[c] = pd.to_datetime(b4[c], utc=True)
        b1[c] = pd.to_datetime(b1[c], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    f = f.sort_values("fundingTime").reset_index(drop=True)
    return b4, b1, f


def per_asset_raw(b4, b1):
    df = b4[["open_time", "close_time", "open", "close"]].copy().sort_values("open_time")
    df = df.reset_index(drop=True)
    logc = np.log(df["close"].to_numpy(dtype=float))
    s7 = np.sign(logc - np.roll(logc, 42))
    s30 = np.sign(logc - np.roll(logc, 180))
    s7[:42] = np.nan
    s30[:180] = np.nan
    sig = (np.nan_to_num(s7, nan=np.nan) + np.nan_to_num(s30, nan=np.nan)) / 2.0
    # rows where either leg is nan -> nan
    sig[np.isnan(s7) | np.isnan(s30)] = np.nan
    sig = np.clip(sig, 0, None)  # long-only clip below at 0
    sig[np.isnan(sig)] = 0.0

    # bear filter via last CLOSED daily bar (daily close_time <= 4h close_time)
    d = b1[["open_time", "close_time", "close"]].copy().sort_values("close_time")
    dc = d["close"].to_numpy(dtype=float)
    sma50 = pd.Series(dc).rolling(50).mean().to_numpy()
    sma200 = pd.Series(dc).rolling(200).mean().to_numpy()
    d["sma50"] = sma50
    d["sma200"] = sma200
    m = pd.merge_asof(
        df[["close_time"]].sort_values("close_time"),
        d[["close_time", "close", "sma50", "sma200"]].sort_values("close_time"),
        on="close_time",
        direction="backward",
    )
    bear = (
        (m["close"] < m["sma50"])
        & (m["sma50"] < m["sma200"])
        & m[["close", "sma50", "sma200"]].notna().all(axis=1)
    ).to_numpy()
    sig[bear] = 0.0

    ret = np.zeros(len(df))
    ret[1:] = logc[1:] - logc[:-1]
    vol = pd.Series(ret).rolling(180).std(ddof=1).to_numpy() * ANN
    raw = np.where((vol > 0) & np.isfinite(vol), sig / np.where(vol > 0, vol, np.nan), 0.0)
    raw[~np.isfinite(raw)] = 0.0
    df["signal"] = sig
    df["logret"] = ret
    df["vol"] = vol
    df["raw"] = raw
    return df


def main():
    per = {}
    funds = {}
    for s in SYMS:
        b4, b1, f = load_asset(s)
        per[s] = per_asset_raw(b4, b1)
        funds[s] = f

    # union grid (full history)
    grid = sorted(set().union(*[set(v["open_time"]) for v in per.values()]))
    grid = pd.DatetimeIndex(grid).tz_convert("UTC").sort_values()
    idx = {t: k for k, t in enumerate(grid)}
    n = len(grid)
    raw_m = np.zeros((n, len(SYMS)))
    ret_m = np.zeros((n, len(SYMS)))
    open_m = np.full((n, len(SYMS)), np.nan)
    for j, s in enumerate(SYMS):
        df = per[s].set_index("open_time")
        have = df.index.intersection(grid)
        pos = np.array([idx[t] for t in have])
        raw_m[pos, j] = df.loc[have, "raw"].to_numpy()
        ret_m[pos, j] = df.loc[have, "logret"].to_numpy()
        open_m[pos, j] = df.loc[have, "open"].to_numpy(dtype=float)

    # portfolio vol targeting
    port_r = np.zeros(n)
    for k in range(1, n):
        port_r[k] = float(np.dot(raw_m[k - 1], ret_m[k]))
    pvol = pd.Series(port_r).rolling(180, min_periods=60).std(ddof=1).to_numpy() * ANN
    scale = np.where((pvol > 0) & np.isfinite(pvol), 0.3 / np.where(pvol > 0, pvol, np.nan), 0.0)
    scale[~np.isfinite(scale)] = 0.0
    scale = np.minimum(scale, 10.0)
    w_pre = raw_m * scale[:, None]
    gross = np.abs(w_pre).sum(axis=1)
    over = gross > 3.0
    w_pre[over] *= (3.0 / gross[over])[:, None]
    # turnover band per asset
    w = np.zeros_like(w_pre)
    prev = np.zeros(len(SYMS))
    for k in range(n):
        cur = w_pre[k].copy()
        keep = np.abs(cur - prev) <= 0.05
        cur[keep] = prev[keep]
        w[k] = cur
        prev = cur

    # window holding bars
    win_mask = (grid >= W0) & (grid <= W1)
    win_pos = np.where(win_mask)[0]
    assert len(win_pos) == 2190, f"window bars {len(win_pos)} != 2190"
    # funding arrays per asset for fast sum
    frate = {}
    ftime = {}
    for j, s in enumerate(SYMS):
        f = funds[s]
        ftime[s] = pd.DatetimeIndex(pd.to_datetime(f["fundingTime"], utc=True))
        frate[s] = f["fundingRate"].to_numpy(dtype=float)

    eq = 1.0
    curve = []
    total_turnover = 0.0
    total_cost = 0.0
    total_funding = 0.0
    total_gross = 0.0
    for k in win_pos:
        kt = k - 1  # decision slot t = previous union bar (h - 4h)
        assert grid[kt] == grid[k] - pd.Timedelta(hours=4), (grid[kt], grid[k])
        wt = w[kt]
        wt_prev = w[kt - 1] if kt - 1 >= 0 else np.zeros(len(SYMS))
        dw = np.abs(wt - wt_prev).sum()
        cost = 0.0002 * float(dw)
        h, h1 = grid[k], grid[k] + pd.Timedelta(hours=4)
        legs = []
        fund = 0.0
        for j, s in enumerate(SYMS):
            o0, o1 = open_m[k, j], open_m[k + 1, j] if k + 1 < n else np.nan
            if np.isfinite(o0) and np.isfinite(o1) and o0 > 0:
                r = float(o1 / o0 - 1.0)
            else:
                r = 0.0
            legs.append(r)
            ft, fr = ftime[s], frate[s]
            # left-closed funding bucket [open_h, open_h+4h)
            m = (ft >= h) & (ft < h1)
            fund += float(wt[j] * fr[m].sum()) if m.any() else 0.0
        gross_r = float(np.dot(wt, np.array(legs)))
        pr = gross_r - cost - fund
        eq *= 1.0 + pr
        curve.append(float(eq))
        total_turnover += float(dw)
        total_cost += cost
        total_funding += fund
        total_gross += gross_r

    curve = np.array(curve)
    peak = np.maximum.accumulate(curve)
    dd = curve / peak - 1.0
    max_dd = float(dd.min())
    net_pct = float((curve[-1] - 1.0) * 100.0)
    n_days = len(win_pos) / 6.0
    out = {
        "spec": "OPENCODE_MJ_W17_AUDIT.md blind replication (Part A, no leader code read)",
        "universe": SYMS,
        "window": {"start": "2023-09-24T00:00:00Z", "end": "2024-09-22T20:00:00Z",
                   "holding_bars": int(len(win_pos)), "days": n_days},
        "signal": "mean(sign(d42),sign(d180)) clipped>=0; bear filter close<SMA50<SMA200 on last CLOSED daily (daily close_time<=4h close_time)",
        "vol": "std(last 180 4h logrets, ddof=1)*sqrt(6*365); pvol same on port_r min 60; scale=min(0.3/pvol,10); cap sum|w|=3",
        "band": "keep prev w unless |new-prev|>0.05 per asset",
        "execution": "w(t) earns open[h+1]/open[h]-1 with h=t+1; cost 0.0002*sum|dw|; funding w*rates in [open_h,open_h+4h); equity compounds from 1.0",
        "causality_notes": "shifts/rollings use only past closes; daily join merge_asof backward on close_time; vol/pvol windows ending at t; decision t applied to next bar",
        "net_pct": net_pct,
        "equity_final": float(curve[-1]),
        "max_drawdown": max_dd,
        "max_drawdown_pct": float(max_dd * 100.0),
        "turnover_per_day": float(total_turnover / n_days),
        "total_turnover_weight": float(total_turnover),
        "total_cost_drag": float(total_cost),
        "total_funding_drag": float(total_funding),
        "total_gross_return": float(total_gross),
        "n_bars": int(len(win_pos)),
    }
    Path("research/mj_audit").mkdir(parents=True, exist_ok=True)
    with open("research/mj_audit/replication.json", "w") as fh:
        json.dump(out, fh, indent=2)
    pd.DataFrame({"open_time": grid[win_pos], "equity": curve}).to_csv(
        "research/mj_audit/equity_4h.csv", index=False)
    print(json.dumps({k: out[k] for k in (
        "net_pct", "equity_final", "max_drawdown_pct", "turnover_per_day",
        "total_cost_drag", "total_funding_drag", "n_bars")}, indent=2))


if __name__ == "__main__":
    main()
