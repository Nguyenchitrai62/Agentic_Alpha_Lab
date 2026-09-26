"""Cross-sectional / multi-coin families with the hidden-year protocol.

Selection: parameters chosen by Sharpe on all data before the anchor (10-day embargo),
then the hidden year [anchor, anchor + 365d) is traded. Robustness: same for five real
anchors with expanding windows. Costs: fee 0.0002 per unit turnover (limit execution)
and stress 0.0006 + 0.0005; funding actual (both sides) and AGENTS-normal.

  python scripts/xs_lab.py
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.xs_portfolio import load_panel, run_weights, summarize
from agentic_alpha_lab.research_vf import ANCHORS, EMBARGO_DAYS

OUT = Path("artifacts/research/xs")


def universe(panel, top: int, min_days: int = 200) -> pd.DataFrame:
    c = panel["close"]
    age = c.notna().cumsum()
    liq = panel["quote_volume"].rolling(30, min_periods=20).mean()
    rank = liq.where(age >= min_days).rank(axis=1, ascending=False)
    return (rank <= top) & c.notna()


def inv_vol(panel, lb: int = 30) -> pd.DataFrame:
    r = np.log(panel["close"]).diff()
    return 1.0 / (r.rolling(lb, min_periods=20).std() * np.sqrt(365))


def normalize(raw: pd.DataFrame, gross: float = 1.0) -> pd.DataFrame:
    s = raw.abs().sum(axis=1).replace(0, np.nan)
    return raw.div(s, axis=0).fillna(0.0) * gross


def rebalance(w: pd.DataFrame, every: int) -> pd.DataFrame:
    if every <= 1:
        return w
    keep = np.arange(len(w)) % every == 0
    return w.where(pd.Series(keep, index=w.index), np.nan).ffill().fillna(0.0)


def xs_momentum(panel, p):
    u = universe(panel, p["top"])
    ret = panel["close"] / panel["close"].shift(p["lb"]) - 1
    if p.get("skip"):
        ret = panel["close"].shift(p["skip"]) / panel["close"].shift(p["lb"]) - 1
    score = ret.where(u)
    rk = score.rank(axis=1, pct=True)
    sign = p.get("sign", 1)
    raw = sign * ((rk >= 1 - p["q"]).astype(float) - (rk <= p["q"]).astype(float))
    if not p["shorts"]:
        raw = raw.clip(lower=0)
    if p["ivol"]:
        raw = raw * inv_vol(panel)
    return rebalance(normalize(raw.where(u, 0.0).fillna(0.0)), p["every"])


def ts_trend(panel, p):
    u = universe(panel, p["top"])
    c = panel["close"]
    f, s = c.rolling(p["fast"]).mean(), c.rolling(p["slow"]).mean()
    raw = ((c > f) & (f > s)).astype(float)
    if p["shorts"]:
        raw = raw - ((c < f) & (f < s)).astype(float)
    raw = raw.where(u, 0.0) * inv_vol(panel)
    # gross 1 spread over the whole universe; flat names leave cash
    n = u.sum(axis=1).replace(0, np.nan)
    iv = (inv_vol(panel).where(u)).sum(axis=1)
    w = raw.div(iv, axis=0).fillna(0.0) * p["gross"]
    return rebalance(w, p["every"])


FAMILIES = {
    "xs_momentum": (xs_momentum, [dict(lb=lb, skip=sk, q=q, top=t, shorts=sh, ivol=iv, every=e)
                                  for lb in (7, 14, 30, 60) for sk in (0, 1) for q in (0.2, 0.33) for t in (20, 40)
                                  for sh in (True, False) for iv in (True,) for e in (1, 7)]),
    "xs_reversal": (xs_momentum, [dict(lb=lb, skip=0, q=q, top=t, shorts=True, ivol=True, every=1, sign=-1)
                                  for lb in (1, 2, 3, 5) for q in (0.2, 0.33) for t in (20, 40)]),
    "ts_trend_multi": (ts_trend, [dict(fast=f, slow=s, top=t, shorts=sh, gross=g, every=e)
                                  for f, s in ((10, 50), (20, 100), (50, 200)) for t in (10, 20, 40) for sh in (False, True)
                                  for g in (1.0,) for e in (1, 3)]),
}


def windows(idx, anchor, select_years=None):
    a = pd.Timestamp(anchor, tz="UTC")
    sel_end = a - pd.Timedelta(days=EMBARGO_DAYS)
    sel_start = idx[0] + pd.Timedelta(days=260) if select_years is None else max(a - pd.Timedelta(days=365 * select_years), idx[0] + pd.Timedelta(days=260))
    return (sel_start, sel_end), (a, a + pd.Timedelta(days=364))


def run_family(panel, fn, grid, anchors):
    out = []
    cache = {}
    for anchor in anchors:
        (s0, s1), (f0, f1) = windows(panel["close"].index, anchor)
        best, score = None, -np.inf
        for p in grid:
            key = json.dumps(p, sort_keys=True)
            if key not in cache:
                cache[key] = fn(panel, p)
            st = summarize(run_weights(panel, cache[key], s0, s1))
            if st["sharpe"] > score:
                best, score, sel_dd = p, st["sharpe"], st["dd_pct"]
        w = cache[json.dumps(best, sort_keys=True)]
        k = min(2.0, np.floor(min(2.0, 20.0 / max(sel_dd, 1e-6)) * 20) / 20)  # DD-targeted gross, capped at 2x
        rows = {}
        for name, kw in (("realistic", dict(fee=0.0002)), ("stress", dict(fee=0.0006, slippage=0.0005)), ("agents_funding", dict(fee=0.0002, funding="normal"))):
            rows[name] = {m: round(v, 4) for m, v in summarize(run_weights(panel, w * k, f0, f1, **kw)).items()}
        out.append(dict(anchor=anchor, selected=best, train_sharpe=round(score, 3), train_dd=round(sel_dd, 2), scale=k, forward=rows))
    return out


def main():
    panel = load_panel("1d")
    print("symbols", panel["close"].shape[1], "days", len(panel["close"]))
    OUT.mkdir(parents=True, exist_ok=True)
    btc = panel["open"]["BTCUSDT"]
    for fam, (fn, grid) in FAMILIES.items():
        res = run_family(panel, fn, grid, ANCHORS)
        (OUT / f"{fam}.json").write_text(json.dumps(res, indent=1, default=str))
        print(f"\n=== {fam} ({len(grid)} configs)")
        for r in res:
            a = pd.Timestamp(r["anchor"], tz="UTC")
            bh = btc.loc[a: a + pd.Timedelta(days=365)]
            f = r["forward"]
            print(f"{r['anchor']} k={r['scale']} sel={r['selected']} | real {f['realistic']['net_pct']:.1f}% stress {f['stress']['net_pct']:.1f}% "
                  f"DD {f['realistic']['dd_pct']:.1f}% sharpe {f['realistic']['sharpe']:.2f} monthly {f['realistic']['monthly_geo_pct']:.2f}% | BTC B&H {100 * (bh.iloc[-1] / bh.iloc[0] - 1):.1f}%")


if __name__ == "__main__":
    main()
