"""Funding carry (long spot + short USD-M perp, equal notional) on majors, hidden-year protocol.

Per 4h bar while in the trade: return on capital = (funding received by the short perp
+ spot return - perp return) / capital_per_notional. Entry/exit pay fee on both legs.
In the trade while the trailing mean funding (known at the bar close) exceeds `enter`,
out when it falls below `exit`. Parameters chosen on data before each anchor (Sharpe);
five real anchors, last = hidden year. Uses actual Binance funding (not the AGENTS
directional-short assumption), documented as such.

  python scripts/carry_lab.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.research_vf import ANCHORS, EMBARGO_DAYS

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
XS, SP = Path("data/raw/xs_universe_20260924"), Path("data/raw/spot_majors_20260925")
OUT = Path("artifacts/research/carry")
CAP = 1.2  # capital per unit notional (spot paid in full + perp margin buffer)


def load(sym):
    perp = pd.read_parquet(XS / f"{sym}_4h.parquet")
    spot = pd.read_parquet(SP / f"{sym}_spot_4h.parquet")
    idx = pd.to_datetime(perp["open_time"], utc=True)
    po = pd.Series(perp["open"].to_numpy(float), index=idx)
    so = pd.Series(spot["open"].to_numpy(float), index=pd.to_datetime(spot["open_time"], utc=True)).reindex(idx)
    f = pd.read_parquet(XS / f"{sym}_funding.parquet")
    ft = pd.to_datetime(f["fundingTime"], utc=True)
    rate = f.groupby(ft.dt.floor("4h"))["fundingRate"].sum().reindex(idx).fillna(0.0)
    known = f.set_index(ft)["fundingRate"]  # a funding print is known at its timestamp
    ct = pd.to_datetime(perp["close_time"], utc=True)
    return dict(po=po, so=so, rate=rate, known=known, ct=ct, idx=idx)


def position(d, q):
    m = d["known"].rolling(q["win"] * 3, min_periods=3).mean()
    m_at_close = m.reindex(d["ct"], method="ffill").to_numpy()
    out = np.zeros(len(m_at_close))
    on = False
    for t, v in enumerate(m_at_close):
        if not np.isfinite(v):
            continue
        if not on and v > q["enter"]:
            on = True
        elif on and v < q["exit"]:
            on = False
        out[t] = 1.0 if on else 0.0
    return pd.Series(out, index=d["idx"])


def returns(d, pos, fee):
    po, so = d["po"], d["so"]
    rp = po.shift(-2) / po.shift(-1) - 1  # perp return held over bar t+1 for a decision at t
    rs = so.shift(-2) / so.shift(-1) - 1
    fund = d["rate"].shift(-1)  # funding settled during bar t+1, received by the short
    gross = pos * (fund + rs - rp)
    cost = pos.diff().abs().fillna(pos.iloc[0]) * 2 * fee
    return ((gross - cost) / CAP).fillna(0.0)


GRID = [dict(win=w, enter=e, exit=x) for w in (3, 7, 14) for e in (0.00005, 0.0001, 0.0002) for x in (0.0, 0.00003) if x < e]


def stats(r):
    eq = (1 + r).cumprod()
    days = len(r) / 6
    g = float(eq.iloc[-1])
    return dict(net=round(100 * (g - 1), 2), dd=round(100 * float(np.max(1 - eq / eq.cummax())), 2),
                sharpe=round(float(r.mean() / r.std() * np.sqrt(6 * 365)), 2) if r.std() > 0 else 0.0,
                exposure=None)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fee = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0004
    data = {s: load(s) for s in SYMS}
    cache = {(s, json.dumps(q)): position(data[s], q) for s in SYMS for q in GRID}
    series = {}
    for s in SYMS:
        d = data[s]
        parts = []
        for anchor in ANCHORS:
            a = pd.Timestamp(anchor, tz="UTC")
            s0, s1 = d["idx"][0] + pd.Timedelta(days=30), a - pd.Timedelta(days=EMBARGO_DAYS)
            def score(q):
                r = returns(d, cache[(s, json.dumps(q))], fee)
                r = r[(r.index >= s0) & (r.index <= s1)]
                return r.mean() / r.std() if r.std() > 0 else -9
            best = max(GRID, key=score)
            r = returns(d, cache[(s, json.dumps(best))], fee)
            fwd = r[(r.index >= a) & (r.index < a + pd.Timedelta(days=365))]
            parts.append(fwd)
            st = stats(fwd)
            print(s, anchor, best, st, "exposure", round(float(cache[(s, json.dumps(best))][fwd.index].mean()), 2), flush=True)
        series[s] = pd.concat(parts)
    port = pd.DataFrame(series).fillna(0.0).mean(axis=1)
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        print("PORTFOLIO equal-weight", anchor, stats(port[(port.index >= a) & (port.index < a + pd.Timedelta(days=365))]))
    port.to_frame("carry").to_parquet(OUT / f"carry_oos_fee{fee}.parquet")


if __name__ == "__main__":
    main()
