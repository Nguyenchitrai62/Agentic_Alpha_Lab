"""Dev-only event study: does the dip-reversal effect of the 4h sleeve exist at the 12h / daily scale? (not registered)

Data: 1m Binance USD-M klines of the five majors, 2021-08-01 .. 2025-09-24 EXCLUSIVE (the most recent year is never loaded).
For each period P (12h, 1d, aligned at 00:00 UTC) starting at T:
  sigma_P = std of the last 30 close-to-close log returns at scale P (known at T), O = open of minute 0.
  rung k in (2.0, 2.5, 3.0, 3.5, 4.0): resting limit bid L = O x exp(-k sigma_P), placed at minute 5 (minute-5 rule), filled only on a
  1m trade-through (low < L) in minutes 5 .. P-16, maker 0.0002.
  exit A: market at the next period open (taker 0.00055).
  exit B: take-profit limit at L x exp(+1 sigma_P) (maker, hit when a later minute's high > TP; stop-first irrelevant, no stop), else A.
  MAE = worst low after the fill until the exit, in sigma_P units (what a stop would face).
Baseline: buy at the minute-5 open of every period, exit at the next open (same fees).
Reported per dev year (anchors 2021-09-24 .. 2024-09-24): fills, mean net %, t-stat, win rate, p05 of net, median MAE.

  python research/diagnostics/daily_dip/daily_dip_dev.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
D = Path("data/raw/majors_intraday_20260924")
BTC = Path("data/raw/btc_intraday_20260924")
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
START, END = pd.Timestamp("2021-06-01", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
KS = (2.0, 2.5, 3.0, 3.5, 4.0)
MAKER, TAKER = 0.0002, 0.00055


def load_1m(s):
    parts = []
    for y in range(2021, 2026):
        f = (BTC / f"klines_1m_{y}.parquet") if s == "BTCUSDT" else (D / f"{s}_1m_{y}.parquet")
        if f.exists():
            parts.append(pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]))
    m = pd.concat(parts).drop_duplicates("open_time")
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m[(m.open_time >= START) & (m.open_time < END)].set_index("open_time").sort_index()
    grid = pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min")
    m = m.reindex(grid)
    m["close"] = m["close"].ffill()
    for c in ("open", "high", "low"):
        m[c] = m[c].fillna(m["close"])
    return m


def study(m, minutes):
    n = len(m) // minutes
    o = m["open"].to_numpy()[: n * minutes].reshape(n, minutes)
    h = m["high"].to_numpy()[: n * minutes].reshape(n, minutes)
    lo = m["low"].to_numpy()[: n * minutes].reshape(n, minutes)
    c = m["close"].to_numpy()[: n * minutes].reshape(n, minutes)
    t0 = m.index[: n * minutes : minutes]
    O = o[:, 0]
    nxt = np.append(O[1:], np.nan)                     # exit price = next period open
    r = np.log(c[:, -1] / np.roll(c[:, -1], 1))
    r[0] = np.nan
    sig = pd.Series(r).rolling(30, min_periods=20).std().shift(1).to_numpy()  # returns of periods before T only
    a, b = 5, minutes - 16
    rows = []
    base = np.log(nxt / o[:, a]) - (TAKER + TAKER)
    for k in KS:
        L = O * np.exp(-k * sig)
        hit = lo[:, a:b] < L[:, None]
        filled = hit.any(axis=1) & np.isfinite(sig) & np.isfinite(nxt)
        first = np.where(filled, hit.argmax(axis=1) + a, -1)
        for i in np.where(filled)[0]:
            f = first[i]
            ra = np.log(nxt[i] / L[i]) - MAKER - TAKER
            tp = L[i] * np.exp(sig[i])
            later_h = h[i, f + 1:]
            rb = (np.log(tp / L[i]) - 2 * MAKER) if (later_h > tp).any() else ra
            if (later_h > tp).any():
                j = f + 1 + int((later_h > tp).argmax())
                mae = np.log(min(lo[i, f + 1:j + 1].min(initial=L[i]), L[i]) / L[i]) / sig[i]
            else:
                mae = np.log(min(lo[i, f + 1:].min(initial=L[i]), L[i]) / L[i]) / sig[i]
            rows.append(dict(t=t0[i], k=k, net_a=ra, net_b=rb, mae=mae))
    ev = pd.DataFrame(rows)
    bl = pd.DataFrame({"t": t0, "net": base})
    return ev, bl


def summ(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return dict(n=int(len(x)))
    return dict(n=int(len(x)), mean_pct=round(100 * x.mean(), 3), t=round(float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))), 2),
                win=round(float((x > 0).mean()), 3), p05_pct=round(100 * float(np.quantile(x, 0.05)), 2))


def main():
    out = {}
    for scale, minutes in (("12h", 720), ("1d", 1440)):
        evs, bls = [], []
        for s in SYMS:
            m = load_1m(s)
            ev, bl = study(m, minutes)
            evs.append(ev.assign(sym=s))
            bls.append(bl.assign(sym=s))
        ev, bl = pd.concat(evs), pd.concat(bls)
        res = {}
        for yi, a0 in enumerate(ANCHORS):
            a1 = a0 + pd.Timedelta(days=365)
            yr = str(a0.year)
            e = ev[(ev.t >= a0) & (ev.t < a1)]
            res[yr] = {"baseline": summ(bl[(bl.t >= a0) & (bl.t < a1)].net)}
            for k in KS:
                g = e[e.k == k]
                res[yr][f"k{k}"] = {"exitA": summ(g.net_a), "exitB_tp1": summ(g.net_b),
                                    "mae_median_sigma": round(float(g.mae.median()), 2) if len(g) else None}
        out[scale] = res
        print("==", scale)
        for yr, r in res.items():
            print(yr, "baseline", r["baseline"])
            for k in KS:
                q = r[f"k{k}"]
                print("  k", k, "A", q["exitA"], "| B", q["exitB_tp1"], "| MAE med", q["mae_median_sigma"])
    (HERE / "daily_dip_dev.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
