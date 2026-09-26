"""Opening-range breakout on real 1m bars (BTC first; majors once 1m data exist).

Range = high/low of [range_start, range_end) UTC each day. From range_end until session_end the
first trade-through of the range high (long) or low (short) enters with a stop order (taker fee
plus slippage beyond the level). Stop at the opposite side or at the range midpoint; target at
R x risk; otherwise exit at session_end close. One trade per day. Stop-first within a minute.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("artifacts/research/mj/orb")
TAKER, SLIP, MAKER = 0.0005, 0.0002, 0.0002


def load_1m(sym: str) -> pd.DataFrame:
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_*.parquet"))
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in files])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").sort_values("open_time").set_index("open_time")


def simulate(m: pd.DataFrame, p: dict) -> pd.DataFrame:
    day = m.index.floor("D")
    mins = (m.index.hour * 60 + m.index.minute).to_numpy()
    o, h, l, c = (m[k].to_numpy() for k in ("open", "high", "low", "close"))
    trades = []
    days = day.unique()
    starts = np.searchsorted(m.index.values, days.values)
    ends = np.append(starts[1:], len(m))
    for d, a, b in zip(days, starts, ends):
        mm = mins[a:b]
        rng = (mm >= p["rs"] * 60) & (mm < p["re"] * 60)
        if rng.sum() < (p["re"] - p["rs"]) * 60 * 0.9:
            continue
        hi, lo = h[a:b][rng].max(), l[a:b][rng].min()
        width = hi - lo
        if width <= 0:
            continue
        sess = np.flatnonzero((mm >= p["re"] * 60) & (mm < p["se"] * 60)) + a
        entry = None
        for i in sess:
            if h[i] > hi and p["dir"] in ("both", "long"):
                entry, side, lvl = i, 1, hi
                break
            if l[i] < lo and p["dir"] in ("both", "short"):
                entry, side, lvl = i, -1, lo
                break
        if entry is None:
            continue
        px_in = max(lvl, o[entry]) * (1 + SLIP) if side > 0 else min(lvl, o[entry]) * (1 - SLIP)
        stop = (lo if side > 0 else hi) if p["stop"] == "opposite" else (hi + lo) / 2
        risk = abs(px_in - stop)
        target = px_in + side * p["rr"] * risk
        exit_px, kind = None, "session"
        for j in range(entry + 1, sess[-1] + 1):
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                exit_px, kind = (min(stop, o[j]) * (1 - SLIP) if side > 0 else max(stop, o[j]) * (1 + SLIP)), "stop"
                break
            if (side > 0 and h[j] > target) or (side < 0 and l[j] < target):
                exit_px, kind = target, "target"
                break
        if exit_px is None:
            exit_px = c[sess[-1]] * (1 - SLIP * side)
        fee = TAKER + (MAKER if kind == "target" else TAKER)
        ret = side * (exit_px / px_in - 1) - fee
        trades.append(dict(day=d, side=side, ret=ret, kind=kind, width_pct=width / lvl, risk_pct=risk / px_in))
    return pd.DataFrame(trades)


GRID = [dict(rs=rs, re=re, se=se, rr=rr, stop=st, dir=dr)
        for (rs, re) in ((0, 8), (0, 4), (13, 14)) for se in (20, 24) for rr in (1.0, 2.0, 99.0) for st in ("opposite", "mid") for dr in ("both", "long")
        if se > re]


def stats(tr: pd.DataFrame, lo: str, hi: str, risk_frac: float = 0.01) -> dict:
    t = tr[(tr.day >= pd.Timestamp(lo, tz="UTC")) & (tr.day < pd.Timestamp(hi, tz="UTC"))]
    if len(t) < 20:
        return dict(n=len(t))
    # size each trade to risk `risk_frac` of equity at its stop distance (capped at 2x notional)
    size = np.minimum(risk_frac / t.risk_pct.clip(lower=1e-4), 2.0)
    eq = np.cumprod(1 + (size * t.ret).to_numpy())
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    yrs = (pd.Timestamp(hi) - pd.Timestamp(lo)).days / 365
    return dict(n=len(t), mean_bps=round(1e4 * t.ret.mean(), 2), hit=round(float((t.ret > 0).mean()), 3),
                t_stat=round(float(t.ret.mean() / t.ret.std() * np.sqrt(len(t))), 2), net_pct=round(100 * (eq[-1] - 1), 1),
                cagr_pct=round(100 * (eq[-1] ** (1 / yrs) - 1), 1), dd_pct=round(100 * dd, 1), avg_size=round(float(size.mean()), 2))


def main():
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    m = load_1m(sym)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in GRID:
        tr = simulate(m, p)
        dev, first_half, second_half = stats(tr, "2020-01-01", "2025-09-14"), stats(tr, "2020-01-01", "2022-09-01"), stats(tr, "2022-09-01", "2025-09-14")
        hid = stats(tr, "2025-09-24", "2026-09-24")
        rows.append(dict(p=json.dumps(p), dev=dev, h1=first_half, h2=second_half, hidden=hid))
        print(json.dumps(p), "| dev", dev, "| halves", first_half.get("mean_bps"), second_half.get("mean_bps"), "| hidden", hid, flush=True)
    (OUT / f"orb_{sym}.json").write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()
