"""Daily multi-asset target-weight portfolio for the cross-sectional (xs) program.

Weights w[t, i] are decided at the close of day t from data up to that close and
held from open[t+1] to open[t+2]. Costs: fee on |w[t] - w[t-1]| (weights are
fractions of equity, gross exposure capped by the strategy), funding: actual
Binance rates applied to the signed weight (long pays positive funding) or the
AGENTS-normal assumption (long 0.0001 per 8h, short 0).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

UNIVERSE_DIR = Path("data/raw/xs_universe_20260924")


def load_panel(tf: str = "1d", min_days: int = 200) -> dict[str, pd.DataFrame]:
    """Aligned open/high/low/close/quote_volume/funding panels (index = UTC day open time)."""
    fields = {k: {} for k in ("open", "high", "low", "close", "quote_volume", "funding")}
    for f in sorted(UNIVERSE_DIR.glob(f"*_{tf}.parquet")):
        sym = f.stem.rsplit("_", 1)[0]
        b = pd.read_parquet(f)
        if len(b) < min_days:
            continue
        idx = pd.to_datetime(b["open_time"], utc=True)
        for k in ("open", "high", "low", "close", "quote_volume"):
            fields[k][sym] = pd.Series(b[k].to_numpy(float), index=idx)
        fp = UNIVERSE_DIR / f"{sym}_funding.parquet"
        if fp.exists():
            fu = pd.read_parquet(fp)
            t = pd.to_datetime(fu["fundingTime"], utc=True).dt.floor("D" if tf == "1d" else "4h")
            fields["funding"][sym] = fu.groupby(t)["fundingRate"].sum().astype(float)
    panel = {k: pd.DataFrame(v).sort_index() for k, v in fields.items()}
    idx = panel["close"].index
    panel["funding"] = panel["funding"].reindex(idx).fillna(0.0)
    return panel


def run_weights(panel: dict[str, pd.DataFrame], w: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                fee: float = 0.0002, slippage: float = 0.0, funding: str = "actual") -> dict:
    """Simulate weights decided at each day's close; returns daily equity curve and cost breakdown."""
    o = panel["open"]
    w = w.reindex(o.index).fillna(0.0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)  # return earned by weight decided at t
    days = w.index[(w.index >= start) & (w.index <= end)]
    w = w.loc[days]
    r = r_next.loc[days]
    turn = w.diff().abs().sum(axis=1)
    turn.iloc[0] = w.iloc[0].abs().sum()
    if funding == "actual":
        f = panel["funding"].shift(-1).reindex(days).fillna(0.0)  # funding paid during the holding day
        fund = (w * f).sum(axis=1)
    else:
        fund = w.clip(lower=0).sum(axis=1) * 0.0003
    gross = (w * r).sum(axis=1)
    net = gross - turn * (fee + slippage) - fund
    eq = (1 + net).cumprod()
    return dict(equity=eq, gross=gross, net=net, turnover=turn, funding=fund)


def summarize(res: dict) -> dict:
    eq, net = res["equity"], res["net"]
    days = max(len(eq), 1)
    g = float(eq.iloc[-1])
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq.to_numpy()]))[1:]
    return dict(net_pct=100 * (g - 1), cagr_pct=100 * (g ** (365 / days) - 1) if g > 0 else -100.0,
                monthly_geo_pct=100 * (g ** (30.4375 / days) - 1) if g > 0 else -100.0,
                sharpe=float(net.mean() / net.std() * np.sqrt(365)) if net.std() > 0 else 0.0,
                dd_pct=100 * float(np.max(1 - eq.to_numpy() / peak)), turnover_per_day=float(res["turnover"].mean()),
                funding_pct=100 * float(res["funding"].sum()))
