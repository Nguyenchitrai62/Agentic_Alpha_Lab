"""Majors-only lab (BTC, ETH, SOL, BNB, XRP): dual momentum and squeeze breakout, hidden-year protocol.

Parameters chosen by Sharpe on all data before the anchor (10-day embargo); gross scaled so the
training DD is 20% (cap 1x baseline; 2x reported separately). Robustness: five real anchors.

  python scripts/mj_lab.py [family ...]
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.xs_portfolio import run_weights, summarize
from agentic_alpha_lab.research_vf import ANCHORS, EMBARGO_DAYS

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
XS = Path("data/raw/xs_universe_20260924")
OUT = Path("artifacts/research/mj")


def load_majors(tf: str = "1d") -> dict[str, pd.DataFrame]:
    fields = {k: {} for k in ("open", "high", "low", "close", "quote_volume", "funding")}
    for s in MAJORS:
        b = pd.read_parquet(XS / f"{s}_{tf}.parquet")
        idx = pd.to_datetime(b["open_time"], utc=True)
        for k in ("open", "high", "low", "close", "quote_volume"):
            fields[k][s] = pd.Series(b[k].to_numpy(float), index=idx)
        fu = pd.read_parquet(XS / f"{s}_funding.parquet")
        t = pd.to_datetime(fu["fundingTime"], utc=True).dt.floor("D" if tf == "1d" else tf)
        fields["funding"][s] = fu.groupby(t)["fundingRate"].sum().astype(float)
    p = {k: pd.DataFrame(v).sort_index() for k, v in fields.items()}
    p["funding"] = p["funding"].reindex(p["close"].index).fillna(0.0)
    return p


def dual_momentum(p, q):
    c = p["close"]
    mom = c / c.shift(q["lb"]) - 1
    trend = c > c.rolling(q["ma"]).mean()
    if q["ribbon"]:
        s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
        trend &= ~((c < s50) & (s50 < s200))
    score = mom.where(trend & c.notna())
    rk = score.rank(axis=1, ascending=False)
    pick = (rk <= q["k"]) & score.notna() & (score > q["min_mom"])
    raw = pick.astype(float)
    if q["ivol"]:
        raw = raw / (np.log(c).diff().rolling(30).std())
    w = raw.div(raw.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    if q["every"] > 1:
        keep = pd.Series(np.arange(len(w)) % q["every"] == 0, index=w.index)
        w = w.where(keep, np.nan).ffill().fillna(0.0)
    return w


def squeeze(p, q):
    """Volatility compression then breakout, per asset, equal risk across majors."""
    c, h, lo = p["close"], p["high"], p["low"]
    ma = c.rolling(20).mean()
    sd = c.rolling(20).std()
    bw = (4 * sd / ma)
    pct = bw.rolling(q["lookback"], min_periods=60).rank(pct=True)
    squeezed = (pct.shift(1) < q["pct"])
    up = squeezed & (c > h.rolling(q["don"]).max().shift(1))
    dn = squeezed & (c < lo.rolling(q["don"]).min().shift(1))
    ema = c.ewm(span=q["exit"], adjust=False).mean()
    pos = pd.DataFrame(0.0, index=c.index, columns=c.columns)
    for s in c.columns:
        x = np.zeros(len(c))
        state = 0
        cu, cd, cc, ce = up[s].to_numpy(), dn[s].to_numpy(), c[s].to_numpy(), ema[s].to_numpy()
        for t in range(len(c)):
            if state == 1 and not cc[t] > ce[t]:
                state = 0
            elif state == -1 and not cc[t] < ce[t]:
                state = 0
            if state == 0:
                if cu[t]:
                    state = 1
                elif cd[t] and q["shorts"]:
                    state = -1
            x[t] = state
        pos[s] = x
    raw = pos / (np.log(c).diff().rolling(30).std())
    n = c.notna().sum(axis=1).replace(0, np.nan)
    iv = (1 / np.log(c).diff().rolling(30).std()).sum(axis=1)
    return raw.div(iv, axis=0).fillna(0.0)


def majors_trend(p, q):
    """Each major in its own 4h-free daily trend (close > SMA fast > SMA slow), inverse-vol weighted."""
    c = p["close"]
    f, s = c.rolling(q["fast"]).mean(), c.rolling(q["slow"]).mean()
    on = ((c > f) & (f > s)).astype(float)
    raw = on / np.log(c).diff().rolling(30).std()
    iv = (1 / np.log(c).diff().rolling(30).std()).where(c.notna()).sum(axis=1)
    return raw.div(iv, axis=0).fillna(0.0) * q["gross"]


PAIRS = (("ETHUSDT", "BTCUSDT"), ("SOLUSDT", "BTCUSDT"), ("SOLUSDT", "ETHUSDT"), ("BNBUSDT", "BTCUSDT"), ("XRPUSDT", "BTCUSDT"))


def pair_signal(p, a, b, q):
    """Signed spread position (+1 long A / short beta*B) from a residual or ratio rule, held q['hold'] days."""
    ca, cb = p["close"][a], p["close"][b]
    ra, rb = np.log(ca).diff(), np.log(cb).diff()
    beta = ra.rolling(60).cov(rb) / rb.rolling(60).var()
    if q["rule"] == "resid_mr":
        res = ra - beta.shift(1) * rb
        z = res.rolling(60).sum() / (res.rolling(60).std(ddof=0) * np.sqrt(60))
        ev = np.where(z < -q["z"], 1, np.where(z > q["z"], -1, 0))
    else:  # ratio breakout (relative momentum)
        r = ca / cb
        ev = np.where(r > r.shift(1).rolling(q["n"]).max(), 1, np.where(r < r.shift(1).rolling(q["n"]).min(), -1, 0))
    ev = pd.Series(ev, index=ca.index).where(ca.notna() & cb.notna(), 0)
    pos = ev.replace(0, np.nan).ffill(limit=q["hold"] - 1).fillna(0.0)
    return pos, beta.clip(0.3, 2.0).fillna(1.0)


def pairs_spread(p, q):
    w = pd.DataFrame(0.0, index=p["close"].index, columns=p["close"].columns)
    pairs = PAIRS if q["pair"] == "all" else [PAIRS[q["pair"]]]
    for a, b in pairs:
        pos, beta = pair_signal(p, a, b, q)
        # equal risk per leg pair: long A, short beta*B, gross 1 per pair before averaging
        g = 1 + beta
        w[a] += pos / g
        w[b] -= pos * beta / g
    return w / len(pairs)


FAMILIES = {
    "pairs_spread": (pairs_spread, [dict(pair=pr, rule=ru, z=z, n=n, hold=h)
                                    for pr in (0, 1, 2, 3, 4, "all") for ru, z, n in (("resid_mr", 1.5, 0), ("resid_mr", 2.0, 0), ("ratio_brk", 0, 30), ("ratio_brk", 0, 55))
                                    for h in (3, 7, 14)]),
    "dual_momentum": (dual_momentum, [dict(lb=lb, ma=ma, ribbon=rb, k=k, ivol=iv, every=e, min_mom=0.0)
                                      for lb in (14, 30, 60, 90) for ma in (50, 100) for rb in (False, True) for k in (1, 2)
                                      for iv in (False, True) for e in (1, 7)]),
    "squeeze": (squeeze, [dict(lookback=lb, pct=pc, don=d, exit=ex, shorts=sh)
                          for lb in (120, 250) for pc in (0.1, 0.2) for d in (10, 20) for ex in (10, 20) for sh in (False, True)]),
    "majors_trend": (majors_trend, [dict(fast=f, slow=s, gross=g) for f, s in ((10, 50), (20, 100), (50, 200)) for g in (1.0,)]),
}


def windows(idx, anchor):
    a = pd.Timestamp(anchor, tz="UTC")
    return (idx[0] + pd.Timedelta(days=260), a - pd.Timedelta(days=EMBARGO_DAYS)), (a, a + pd.Timedelta(days=364))


def run_family(p, fn, grid):
    cache, out = {}, []
    for anchor in ANCHORS:
        (s0, s1), (f0, f1) = windows(p["close"].index, anchor)
        best, score, dd = None, -np.inf, None
        for q in grid:
            key = json.dumps(q, sort_keys=True)
            if key not in cache:
                cache[key] = fn(p, q)
            st = summarize(run_weights(p, cache[key], s0, s1))
            if st["sharpe"] > score:
                best, score, dd = q, st["sharpe"], st["dd_pct"]
        w = cache[json.dumps(best, sort_keys=True)]
        k1 = np.floor(min(1.0, 20.0 / max(dd, 1e-6)) * 20) / 20
        k2 = np.floor(min(2.0, 20.0 / max(dd, 1e-6)) * 20) / 20
        rows = {name: {m: round(v, 3) for m, v in summarize(run_weights(p, w * k, f0, f1, **kw)).items()}
                for name, k, kw in (("real", k1, dict(fee=0.0002)), ("stress", k1, dict(fee=0.0006, slippage=0.0005)),
                                    ("agents_funding", k1, dict(fee=0.0002, funding="normal")), ("real_cap2", k2, dict(fee=0.0002)))}
        out.append(dict(anchor=anchor, selected=best, train_sharpe=round(score, 3), train_dd=round(dd, 2), k=k1, k_cap2=k2, forward=rows))
    return out


def main():
    fams = sys.argv[1:] or list(FAMILIES)
    p = load_majors("1d")
    OUT.mkdir(parents=True, exist_ok=True)
    btc = p["open"]["BTCUSDT"]
    for fam in fams:
        fn, grid = FAMILIES[fam]
        res = run_family(p, fn, grid)
        (OUT / f"{fam}.json").write_text(json.dumps(res, indent=1, default=str))
        print(f"\n=== {fam} ({len(grid)} configs)")
        for r in res:
            f = r["forward"]
            a = pd.Timestamp(r["anchor"], tz="UTC")
            bh = btc.loc[a:a + pd.Timedelta(days=364)]
            print(f"{r['anchor']} k={r['k']} sel={r['selected']} | real {f['real']['net_pct']:.1f}% stress {f['stress']['net_pct']:.1f}% "
                  f"DD {f['real']['dd_pct']:.1f}% sharpe {f['real']['sharpe']:.2f} mo {f['real']['monthly_geo_pct']:.2f}% | cap2 k={r['k_cap2']} "
                  f"{f['real_cap2']['net_pct']:.1f}% DD {f['real_cap2']['dd_pct']:.1f}% | BTC {100 * (bh.iloc[-1] / bh.iloc[0] - 1):.1f}%")


if __name__ == "__main__":
    main()
