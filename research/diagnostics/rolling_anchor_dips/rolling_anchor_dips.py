"""Dev-only diagnostic (not a registered version): does a CLOCK-FREE dip anchor remove the 4h-grid phase luck of the dip ladder?

Motivation (v374-v376, v387): the anchored dip ladder (bids k sigma_4h below the 4h bar OPEN) earns very different returns on 4h grids
shifted by 1-3 h (e.g. R2 2023: +8.6 / +0.9 / +1.2 / -2.0 %/month across phases): the 4h open is an arbitrary reference, so the drop being
measured has a random look-back of 16..238 minutes. A rolling anchor measures every drop over the same look-back and needs no clock.

Fixed before running (event study, dip-only, no book, no agents, equal notional per fill, no compounding):
- Data: Binance USD-M 1m klines BTC/ETH/SOL/BNB/XRP (same files as phase_offset_dips), minutes < 2025-09-24 only (dev). Rows reported:
  pre-research period 2020-10-01..2021-09-23 ("pre") and the four dev years 2021-09-24 .. 2025-09-23.
- sigma = engine_user sig4: std of 4h open-to-open returns over 360 bars (min 120) on the standard grid, value of the bar containing the
  minute (uses opens up to that bar's open -> known at the bar open).
- Rules (rungs k = 3.0 and 4.0 sigma, each rung an independent position per coin):
  A_s  ANCHORED (current): bar grid shifted by s = 0,1,2,3 h; level L = open(bar) * (1 - k sigma); bid live minutes 16..238 of the bar;
       fill at the first minute with low < L (strict trade-through, maker, price L); at most one fill per rung per bar; exits from the
       minute after the fill: stop touch low <= L(1 - 8 sigma) (taker, price min(stop, minute open)), TP high > L(1 + sigma) (maker, price
       TP), same-minute tie -> stop; otherwise taker exit at the next bar open.
  R_open  ROLLING open: L(t) = open(t - 240) * (1 - k sigma) (price 240 minutes ago, known before minute t).
  R_max   ROLLING max: L(t) = max(close[t-240 .. t-1]) * (1 - k sigma) (drawdown from the 4h running high, known before minute t).
       Rolling rules: fill at minute t if low(t) < L(t) (maker, price L(t)); exits as above, time exit at the open of minute fill + 241
       (taker); a rung re-arms only 240 minutes after its previous fill AND after its position closed (<= one fill per rung per 4h).
- Costs: entry maker 0.0002, TP maker 0.0002, stop / time exit taker 0.00055. Funding ignored (all rules hold < 4h).
- Output per rule and period: fills, mean net return per fill (bps), win rate, sum of returns (units of notional), daily-P&L Sharpe
  (equal notional), max DD of the cumulative-sum curve, and for A_s the phase spread. Nothing is selected here; a registered version
  follows only if a rolling rule beats the 4-phase anchored mean in every dev year on sum AND on DD-adjusted terms.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEV1 = pd.Timestamp("2025-09-24", tz="UTC")
PERIODS = [("pre", "2020-10-01", "2021-09-24"), ("2021", "2021-09-24", "2022-09-24"), ("2022", "2022-09-24", "2023-09-24"),
           ("2023", "2023-09-24", "2024-09-24"), ("2024", "2024-09-24", "2025-09-24")]
KS = (3.0, 4.0)
MK, TK = 0.0002, 0.00055
SL_K, TP_K, W = 8.0, 1.0, 240


def load(s):
    d = ROOT / ("data/raw/btc_intraday_20260924" if s == "BTCUSDT" else "data/raw/majors_intraday_20260924")
    pat = "klines_1m_20*.parquet" if s == "BTCUSDT" else f"{s}_1m_20*.parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    m = m[(m.index >= pd.Timestamp("2020-01-01", tz="UTC")) & (m.index < DEV1)]
    full = pd.date_range(m.index[0], m.index[-1], freq="1min")
    return m.reindex(full)


def sigma_per_minute(m):
    o4 = m["open"].resample("4h").first()
    sig4 = o4.pct_change().rolling(360, min_periods=120).std()
    return sig4.reindex(m.index.floor("4h")).to_numpy()


def exits(O, H, L, f, lv, sg, t_end):
    """First exit after fill minute f for a long at level lv; t_end = index of the minute whose OPEN is the time exit."""
    stop, tp = lv * (1 - SL_K * sg), lv * (1 + TP_K * sg)
    a, b = f + 1, min(t_end, len(O))
    if b > a:
        hs = L[a:b] <= stop
        ht = H[a:b] > tp
        i_s = np.argmax(hs) if hs.any() else 10**9
        i_t = np.argmax(ht) if ht.any() else 10**9
        if i_s < 10**9 and i_s <= i_t:
            px = min(stop, O[a + i_s]) if np.isfinite(O[a + i_s]) else stop
            return a + i_s, px / lv - 1 - MK - TK, "stop"
        if i_t < 10**9:
            return a + i_t, tp / lv - 1 - 2 * MK, "tp"
    if t_end >= len(O) or not np.isfinite(O[t_end]):
        return None
    return t_end, O[t_end] / lv - 1 - MK - TK, "time"


def anchored(m, sg, shift_h, k):
    O, H, Lo = (m[c].to_numpy() for c in ("open", "high", "low"))
    idx = m.index
    sh = pd.Timedelta(hours=shift_h)
    start = (idx - sh).floor("4h") + sh
    off = ((idx - start).total_seconds() // 60).astype(int).to_numpy()
    bar_first = np.flatnonzero(off == 0)
    ev = []
    for b0 in bar_first:
        if b0 + 240 > len(O) or not np.isfinite(O[b0]) or not np.isfinite(sg[b0 + 16]):
            continue
        s = sg[b0 + 16]
        lv = O[b0] * (1 - k * s)
        win = Lo[b0 + 16:b0 + 239] < lv
        if not win.any():
            continue
        f = b0 + 16 + int(np.argmax(win))
        r = exits(O, H, Lo, f, lv, s, b0 + 240)
        if r is not None:
            ev.append((idx[f], r[1], r[2]))
    return ev


def rolling(m, sg, k, mode):
    O, H, Lo, C = (m[c].to_numpy() for c in ("open", "high", "low", "close"))
    idx = m.index
    if mode == "open":
        anc = np.full(len(O), np.nan)
        anc[W:] = O[:-W]
    else:
        anc = pd.Series(C).rolling(W, min_periods=W // 2).max().shift(1).to_numpy()
    lvl = anc * (1 - k * sg)
    trig = np.flatnonzero(Lo < lvl)  # NaN comparisons are False
    ev, ready = [], 0
    for f in trig:
        if f < ready:
            continue
        lv, s = lvl[f], sg[f]
        r = exits(O, H, Lo, f, lv, s, f + W + 1)
        if r is None:
            continue
        ev.append((idx[f], r[1], r[2]))
        ready = max(f + W, r[0] + 1)
    return ev


def summarize(evs):
    df = pd.DataFrame(evs, columns=["t", "ret", "how"])
    out = {}
    for name, a, b in PERIODS:
        d = df[(df.t >= pd.Timestamp(a, tz="UTC")) & (df.t < pd.Timestamp(b, tz="UTC"))]
        if not len(d):
            out[name] = dict(n=0)
            continue
        days = pd.date_range(a, b, freq="D", tz="UTC", inclusive="left")
        daily = d.groupby(d.t.dt.floor("D")).ret.sum().reindex(days, fill_value=0.0)
        cum = daily.cumsum()
        out[name] = dict(n=int(len(d)), mean_bps=round(1e4 * d.ret.mean(), 1), win=round(float((d.ret > 0).mean()), 3),
                         sum=round(float(d.ret.sum()), 3), sharpe=round(float(daily.mean() / daily.std() * np.sqrt(365)), 2),
                         dd=round(float((cum.cummax() - cum).max()), 3), stops=int((d.how == "stop").sum()))
    return out


def main():
    res = {}
    for s in SYMS:
        m = load(s)
        sg = sigma_per_minute(m)
        for k in KS:
            for sh in range(4):
                res.setdefault(f"A{sh}_k{k}", []).extend(anchored(m, sg, sh, k))
            for mode in ("open", "max"):
                res.setdefault(f"R_{mode}_k{k}", []).extend(rolling(m, sg, k, mode))
        print("done", s, flush=True)
    table = {key: summarize(ev) for key, ev in res.items()}
    for k in KS:  # 4-phase mean of the anchored rule (each phase with 1/4 notional)
        allev = []
        for sh in range(4):
            allev += [(t, r / 4, h) for t, r, h in res[f"A{sh}_k{k}"]]
        table[f"A4P_k{k}"] = summarize(allev)
    json.dump(table, open(OUT / "rolling_anchor_dips.json", "w"), indent=1)
    rows = []
    for key, per in table.items():
        for p, v in per.items():
            rows.append(dict(rule=key, period=p, **v))
    tab = pd.DataFrame(rows)
    print(tab.pivot(index="rule", columns="period", values="sum").round(2).to_string())
    print(tab.pivot(index="rule", columns="period", values="dd").round(2).to_string())
    print(tab.pivot(index="rule", columns="period", values="n").to_string())
    print(tab.pivot(index="rule", columns="period", values="mean_bps").to_string())
    print(tab.pivot(index="rule", columns="period", values="sharpe").to_string())


if __name__ == "__main__":
    main()
