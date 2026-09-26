"""MA support/resistance limit-order lab (user hypothesis 2026-09-24).

At every closed 15m bar, find the nearest user MA-Ribbon level (SMA 50/100/200 of
15m/1h/4h, each known from its last closed bar) below price for longs (above for
shorts), rest a limit order there, and manage it on real 1m bars with
`backtest.limit_levels`. A placebo places the same order at the same distance
from price but ignores where the MA is (level = close -/+ the distance to a
randomly chosen other bar's nearest level), so any "S/R" edge must beat it.

  python scripts/masr_limit_lab.py --window dev|hidden
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.bracket import atr
from agentic_alpha_lab.backtest.limit_levels import LimitCosts, Order, run_orders, summarize_trades
from agentic_alpha_lab.patterns.common import load_bars

D = Path("data/raw/btc_intraday_20260924")
OUT = Path("artifacts/research/masr/limit_lab")
WINDOWS = {"dev": ("2020-01-01", "2025-09-13"), "hidden": ("2025-09-24", "2026-09-23")}
TFS = ("15m", "1h", "4h")
PERIODS = (50, 100, 200)


def load_1m(first: str, last: str) -> pd.DataFrame:
    years = range(pd.Timestamp(first).year, pd.Timestamp(last).year + 1)
    parts = []
    for y in years:
        f = D / f"klines_1m_{y}.parquet"
        if f.exists():
            parts.append(pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]))
    alt = Path("data/raw/btc_1m_hidden_20260924/klines_1m.parquet")
    if alt.exists():
        parts.append(pd.read_parquet(alt, columns=["open_time", "open", "high", "low", "close"]))
    m = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    lo, hi = pd.Timestamp(first, tz="UTC"), pd.Timestamp(last, tz="UTC") + pd.Timedelta("2D")
    return m[(m.open_time >= lo) & (m.open_time < hi)].reset_index(drop=True)


def levels_frame() -> pd.DataFrame:
    b15 = pd.read_parquet(D / "klines_15m.parquet")
    b15["open_time"] = pd.to_datetime(b15["open_time"], utc=True)
    b15["close_time"] = pd.to_datetime(b15["close_time"], utc=True)
    out = pd.DataFrame({"t": b15["close_time"], "close": b15["close"], "atr": atr(b15)})
    for tf in TFS:
        b = b15 if tf == "15m" else load_bars(tf, include_opened_year=True)
        lv = pd.DataFrame({"t": b["close_time"].to_numpy()})
        for p in PERIODS:
            lv[f"{tf}_sma{p}"] = b["close"].rolling(p, min_periods=p).mean().to_numpy()
        lv["t"] = pd.to_datetime(lv["t"], utc=True)
        out = pd.merge_asof(out.sort_values("t"), lv.sort_values("t"), on="t", direction="backward")
    b4 = load_bars("4h", include_opened_year=True)
    trend = pd.DataFrame({"t": pd.to_datetime(b4["close_time"], utc=True),
                          "trend4h": np.sign(b4["close"].rolling(50).mean() - b4["close"].rolling(200).mean()).to_numpy()})
    return pd.merge_asof(out, trend, on="t", direction="backward")


def make_orders(lv: pd.DataFrame, p: dict, placebo: bool, rng: np.random.Generator) -> list[Order]:
    cols = [c for c in lv.columns if "_sma" in c]
    L = lv[cols].to_numpy()
    close, a = lv["close"].to_numpy(), lv["atr"].to_numpy()
    orders = []
    for side in (1, -1):
        if side == -1 and not p["shorts"]:
            continue
        rel = (close[:, None] - L) * side / a[:, None]  # >0 : level on the entry side of price
        rel = np.where((rel >= p["min_atr"]) & (rel <= p["max_atr"]), rel, np.nan)
        near = np.nanmin(rel, axis=1)
        idx = np.flatnonzero(np.isfinite(near) & np.isfinite(a))
        if p["trend"]:
            tr = lv["trend4h"].to_numpy()
            idx = idx[tr[idx] == side]
        if placebo:  # same distance distribution, level unrelated to any MA at this bar
            near_sh = near[idx][rng.permutation(len(idx))]
            dist = near_sh
        else:
            dist = near[idx]
        for i, d in zip(idx, dist):
            level = close[i] - side * d * a[i]
            stop = level - side * p["stop_atr"] * a[i]
            target = level + side * p["rr"] * p["stop_atr"] * a[i]
            orders.append(Order(lv["t"].iloc[i], side, float(level), float(stop), float(target), p["expiry"], p["hold"]))
    return orders


def evaluate(m1: pd.DataFrame, lv: pd.DataFrame, p: dict, window: tuple[str, str], seed: int = 0) -> dict:
    lo, hi = pd.Timestamp(window[0], tz="UTC"), pd.Timestamp(window[1], tz="UTC") + pd.Timedelta("1D")
    sub = lv[(lv.t >= lo) & (lv.t < hi)].reset_index(drop=True)
    days = (hi - lo).total_seconds() / 86400
    res = {}
    for name, placebo in (("ma", False), ("placebo", True)):
        rows = []
        for costs_name, costs in (("realistic", LimitCosts()), ("stress", LimitCosts(maker=0.0004, taker=0.0006, stop_slippage=0.0005))):
            r = run_orders(m1, make_orders(sub, p, placebo, np.random.default_rng(seed)), costs)
            res[f"{name}_{costs_name}"] = {k: round(v, 4) if isinstance(v, float) else v for k, v in summarize_trades(r, days).items()}
    return res


GRID = [dict(min_atr=mi, max_atr=ma, stop_atr=s, rr=rr, expiry=4 * 15, hold=h, trend=t, shorts=sh)
        for mi, ma in ((0.2, 1.5), (0.5, 3.0)) for s in (0.5, 1.0) for rr in (1.0, 2.0) for h in (240, 960) for t in (True, False) for sh in (False, True)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", choices=list(WINDOWS), default="dev")
    ap.add_argument("--limit", type=int, default=0, help="evaluate only the first N grid configs")
    a = ap.parse_args()
    w = WINDOWS[a.window]
    m1 = load_1m(*w)
    lv = levels_frame()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    grid = GRID[: a.limit] if a.limit else GRID
    for i, p in enumerate(grid):
        r = evaluate(m1, lv, p, w)
        rows.append(dict(**p, **{f"{k}_{m}": v for k, d in r.items() for m, v in d.items() if m in ("net_pct", "monthly_geo_pct", "trades", "win_rate", "mean_ret_bps", "dd_trade_close_pct")}))
        x = rows[-1]
        print(i, json.dumps(p), "| MA real", x.get("ma_realistic_net_pct"), "bps", x.get("ma_realistic_mean_ret_bps"), "n", x.get("ma_realistic_trades"),
              "| placebo", x.get("placebo_realistic_net_pct"), "bps", x.get("placebo_realistic_mean_ret_bps"), flush=True)
    pd.DataFrame(rows).to_csv(OUT / f"grid_{a.window}.csv", index=False)


if __name__ == "__main__":
    main()
