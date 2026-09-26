"""Majors multi-horizon TSMOM portfolio with portfolio-level volatility targeting (4h bars).

Per asset: signal = mean(sign(log close - log close h days ago)) over horizons, long-only or
long/short, gated by the asset's own daily SMA50/SMA200 ribbon. Portfolio: per-asset risk
parity (1/vol), summed, then scaled so the portfolio's trailing 30-day realized vol hits a
target (cap on gross leverage). Positions only change when the rounded target moves by at
least `band` (turnover control). Parameters are chosen on data before each anchor (Sharpe),
then the next real year is traded; the last anchor is the hidden year.

  python scripts/mj_tsmom_portfolio.py BTCUSDT,ETHUSDT,SOLUSDT
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.research_vf import ANCHORS, EMBARGO_DAYS
from agentic_alpha_lab.patterns.common import load_bars

XS = Path("data/raw/xs_universe_20260924")
OUT = Path("artifacts/research/mj/tsmom_portfolio")
PER_DAY = 6


def load(syms):
    close, open_, fund, daily_rib = {}, {}, {}, {}
    for s in syms:
        b = load_bars("4h", include_opened_year=True) if s == "BTCUSDT" else pd.read_parquet(XS / f"{s}_4h.parquet")
        idx = pd.to_datetime(b["open_time"], utc=True)
        close[s] = pd.Series(b["close"].to_numpy(float), index=idx)
        open_[s] = pd.Series(b["open"].to_numpy(float), index=idx)
        d = (load_bars("1d", include_opened_year=True) if s == "BTCUSDT" else pd.read_parquet(XS / f"{s}_1d.parquet"))
        dc = pd.Series(d["close"].to_numpy(float), index=pd.to_datetime(d["close_time"], utc=True))
        s50, s200 = dc.rolling(50).mean(), dc.rolling(200).mean()
        rib = pd.Series(np.where((dc > s50) & (s50 > s200), 1.0, np.where((dc < s50) & (s50 < s200), -1.0, 0.0)), index=dc.index)
        ct = pd.to_datetime(b["close_time"], utc=True)
        daily_rib[s] = pd.Series(rib.reindex(ct, method="ffill").to_numpy(), index=idx)  # last closed daily bar
        f = pd.read_parquet(XS / f"{s}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("4h")
        fund[s] = f.groupby(ft)["fundingRate"].sum()
    C = pd.DataFrame(close).sort_index()
    return dict(close=C, open=pd.DataFrame(open_).reindex(C.index), rib=pd.DataFrame(daily_rib).reindex(C.index),
                fund=pd.DataFrame(fund).reindex(C.index).fillna(0.0))


def weights(P, q):
    C = P["close"]
    lc = np.log(C)
    sig = sum(np.sign(lc - lc.shift(h * PER_DAY)) for h in q["horizons"]) / len(q["horizons"])
    if not q["shorts"]:
        sig = sig.clip(lower=0)
    rib = P["rib"]
    sig = sig.where(~((sig > 0) & (rib == -1)), 0.0).where(~((sig < 0) & (rib == 1)), 0.0)
    if q.get("btc_gate") and "BTCUSDT" in rib:
        btc = rib["BTCUSDT"]
        long_scale = np.where(btc == 1, 1.0, q["btc_gate"])  # reduce longs when BTC's daily ribbon is not bullish
        sig = sig.where(sig <= 0, sig.mul(long_scale, axis=0))
    r = lc.diff()
    vol = r.rolling(PER_DAY * 30).std() * np.sqrt(PER_DAY * 365)
    raw = (sig / vol).fillna(0.0)
    # portfolio vol of the raw book, trailing 30 days (uses only past returns of past weights)
    port_r = (raw.shift(1) * r).sum(axis=1)
    pvol = port_r.rolling(PER_DAY * 30, min_periods=PER_DAY * 10).std() * np.sqrt(PER_DAY * 365)
    scale = (q["target_vol"] / pvol).clip(upper=10.0)
    w = raw.mul(scale, axis=0)
    gross = w.abs().sum(axis=1)
    w = w.div((gross / q["max_gross"]).clip(lower=1.0), axis=0).fillna(0.0)
    # turnover band: only move a weight when it changes by more than `band`
    out = np.zeros_like(w.to_numpy())
    cur = np.zeros(w.shape[1])
    for t, row in enumerate(w.to_numpy()):
        move = np.abs(row - cur) > q["band"]
        cur = np.where(move, row, cur)
        out[t] = cur
    return pd.DataFrame(out, index=w.index, columns=w.columns)


def simulate(P, w, start, end, fee=0.0002, slip=0.0, dd_cut=None, cooldown_days=30):
    """Bar-by-bar portfolio; optional drawdown circuit breaker scales the book by 0.5 beyond
    dd_cut and to 0 beyond 2*dd_cut, resetting the peak after `cooldown_days` in a reduced state."""
    o = P["open"]
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    idx = w.index[(w.index >= start) & (w.index <= end)]
    W0 = w.loc[idx].to_numpy()
    R = r_next.loc[idx].to_numpy()
    F = P["fund"].shift(-1).reindex(idx).fillna(0.0).to_numpy()
    n = len(idx)
    eq = np.ones(n)
    net = np.zeros(n)
    turn = np.zeros(n)
    prev_w = np.zeros(W0.shape[1])
    level, peak, mult, reduced_since = 1.0, 1.0, 1.0, None
    for t in range(n):
        if dd_cut is not None:
            dd = 1 - level / peak
            mult = 1.0 if dd < dd_cut else (0.5 if dd < 2 * dd_cut else 0.0)
            if mult < 1.0:
                reduced_since = t if reduced_since is None else reduced_since
                if t - reduced_since >= cooldown_days * PER_DAY:
                    peak, reduced_since, mult = level, None, 1.0
            else:
                reduced_since = None
        wt = W0[t] * mult
        turn[t] = np.abs(wt - prev_w).sum()
        net[t] = (wt * R[t]).sum() - turn[t] * (fee + slip) - (wt * F[t]).sum()
        level *= 1 + net[t]
        peak = max(peak, level)
        eq[t] = level
        prev_w = wt
    return pd.Series(eq, index=idx), pd.Series(net, index=idx), pd.Series(turn, index=idx)


def stats(eq, net, turn):
    days = len(eq) / PER_DAY
    g = float(eq.iloc[-1])
    dd = float(np.max(1 - eq / eq.cummax()))
    return dict(net_pct=round(100 * (g - 1), 1), monthly=round(100 * (g ** (30.4375 / days) - 1), 2),
                sharpe=round(float(net.mean() / net.std() * np.sqrt(PER_DAY * 365)), 2) if net.std() > 0 else 0.0,
                dd_pct=round(100 * dd, 1), turnover_per_day=round(float(turn.mean() * PER_DAY), 2))


GRID = [dict(horizons=hz, shorts=sh, target_vol=tv, max_gross=mg, band=bd, dd_cut=dc, btc_gate=bg)
        for hz in ((7, 30), (7, 30, 90), (14, 60)) for sh in (False, True) for tv in (0.2, 0.3, 0.4) for mg in (0.5, 1.0, 1.5, 2.0, 3.0) for bd in (0.05,)
        for dc in (None, 0.06, 0.1) for bg in (0.0, 0.5, 1.0)]
MAX_TRAIN_DD = 20.0


def wkey(q):
    return json.dumps({k: v for k, v in q.items() if k != "dd_cut"})



def main():
    syms = sys.argv[1].split(",")
    P = load(syms)
    OUT.mkdir(parents=True, exist_ok=True)
    cache = {}
    for q in GRID:
        if wkey(q) not in cache:
            cache[wkey(q)] = weights(P, q)
    idx = P["close"].index
    res = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        s0, s1 = idx[0] + pd.Timedelta(days=260), a - pd.Timedelta(days=EMBARGO_DAYS)
        # objective: Calmar-like (annual return / max DD) on training, which penalises crash exposure
        def score(q):
            st = stats(*simulate(P, cache[wkey(q)], s0, s1, dd_cut=q["dd_cut"]))
            yrs = (s1 - s0).days / 365
            ann = (1 + st["net_pct"] / 100) ** (1 / yrs) - 1
            # hard constraint (user, 2026-09-25): training max DD <= 20%; maximize annual return inside it
            return ann if st["dd_pct"] <= MAX_TRAIN_DD else -10 - st["dd_pct"]
        best = max(GRID, key=score)
        tr = stats(*simulate(P, cache[wkey(best)], s0, s1, dd_cut=best["dd_cut"]))
        w = cache[wkey(best)]
        f0, f1 = a, a + pd.Timedelta(days=364)
        n = stats(*simulate(P, w, f0, f1, dd_cut=best["dd_cut"]))
        s = stats(*simulate(P, w, f0, f1, fee=0.0006, slip=0.0005, dd_cut=best["dd_cut"]))
        res.append(dict(anchor=anchor, selected=best, train=tr, normal=n, stress=s))
        print(anchor, "sel", best, "| train sharpe", tr["sharpe"], "dd", tr["dd_pct"], "| fwd", n, "| stress net", s["net_pct"], "dd", s["dd_pct"], flush=True)
    nets = [r["normal"]["net_pct"] for r in res]
    geo = np.prod([1 + x / 100 for x in nets]) ** (1 / len(nets)) - 1
    print(f"geometric mean {100 * geo:.1f}%/yr = {100 * ((1 + geo) ** (1 / 12) - 1):.2f}%/month; worst-year DD {max(r['normal']['dd_pct'] for r in res)}%; "
          f"stress geo {100 * (np.prod([1 + r['stress']['net_pct'] / 100 for r in res]) ** (1 / len(res)) - 1):.1f}%/yr")
    (OUT / f"{'_'.join(s[:3] for s in syms)}.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
