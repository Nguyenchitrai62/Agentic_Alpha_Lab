"""Intrabar whale-flow features from the 1m order-level store (registry v252, fixed before evaluation).

Input: data/raw/aggflow_20260929_orders_1m/{SYM}/*.parquet (scripts/fetch_aggtrades_flow.py --orders --out data/raw/aggflow_20260929_orders):
per UTC minute and taker-ORDER notional bin (lt1k, 1k_10k, 10k_30k, 30k_100k, 100k_300k, 300k_1m, 1m_3m, ge3m USDT) the taker-buy / sell
notional and order counts; 1m closes from the Binance 1m klines used by the engine. The row of 4h bar t aggregates minutes t .. t+239 only,
so it is known at the bar close (t + 4h); rolling statistics use rows <= t.
  fi_big_imb_last1h  (buy - sell) of >= 100k orders in the LAST hour of the bar / total notional of that hour (late whale pressure)
  fi_absorb6         over 6 bars: >= 100k buys in minutes that closed DOWN minus >= 100k sells in minutes that closed UP, / total notional
                     (whales absorbing moves against them vs chasing)
  fi_mid_imb6        (buy - sell) of the 30k-100k bin over 6 bars / total notional (the tier between retail and whales)
  fi_burst_z         z-score (540 bars) of log1p(largest one-minute >= 300k notional in the bar / mean one-minute total notional of the bar)
NaN where the store has no trades for the bar (archive gaps, before the symbol's archive starts).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FI = ("fi_big_imb_last1h", "fi_absorb6", "fi_mid_imb6", "fi_burst_z")
D = Path("data/raw/aggflow_20260929_orders_1m")
BINS = ("lt1k", "1k_10k", "10k_30k", "30k_100k", "100k_300k", "300k_1m", "1m_3m", "ge3m")
BIG = ("100k_300k", "300k_1m", "1m_3m", "ge3m")
BURST = ("300k_1m", "1m_3m", "ge3m")


def _closes(sym: str) -> pd.Series:
    d = Path("data/raw/btc_intraday_20260924") if sym == "BTCUSDT" else Path("data/raw/majors_intraday_20260924")
    pat = "klines_1m_20*.parquet" if sym == "BTCUSDT" else f"{sym}_1m_20*.parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "close"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").set_index("open_time")["close"].astype(float).sort_index()


def bar_table(sym: str, store: Path | None = None) -> pd.DataFrame:
    """Per 4h bar: the raw intrabar aggregates the features are built from."""
    files = sorted((store or D).joinpath(sym).glob("*.parquet"))
    m = pd.concat([pd.read_parquet(f) for f in files]).groupby(level=0).sum().sort_index()
    m.index = pd.DatetimeIndex(m.index).tz_convert("UTC") if m.index.tz is not None else pd.DatetimeIndex(m.index).tz_localize("UTC")
    col = lambda side, bins: sum(m[f"{side}_{b}"] if f"{side}_{b}" in m else 0.0 for b in bins)
    tot = col("buy", BINS) + col("sell", BINS)
    bb, bs = col("buy", BIG), col("sell", BIG)
    c = _closes(sym).reindex(m.index)
    r = c.pct_change(fill_method=None)  # minute return: close of this minute vs the previous minute (both inside the data up to t)
    bar = m.index.floor("4h")
    last = (m.index - bar) >= pd.Timedelta(minutes=180)
    x = pd.DataFrame({"tot": tot, "big_net_last": (bb - bs).where(last, 0.0), "tot_last": tot.where(last, 0.0),
                      "absorb": bb.where(r < 0, 0.0) - bs.where(r > 0, 0.0),
                      "mid_net": col("buy", ("30k_100k",)) - col("sell", ("30k_100k",)),
                      "burst": col("buy", BURST) + col("sell", BURST)}, index=m.index)
    g = x.groupby(bar)
    out = g[["tot", "big_net_last", "tot_last", "absorb", "mid_net"]].sum()
    out["burst_max"] = g["burst"].max()
    out["tot_mean"] = out["tot"] / 240.0
    return out


def intrabar_features(sym: str, bar_open: pd.DatetimeIndex, table: pd.DataFrame | None = None) -> pd.DataFrame:
    f = bar_table(sym) if table is None else table
    f = f.reindex(pd.date_range(f.index[0], f.index[-1], freq="4h", tz="UTC"))
    tot = f["tot"].fillna(0.0)

    def ratio(num, n):
        return num.fillna(0.0).rolling(n, min_periods=n).sum() / tot.rolling(n, min_periods=n).sum().replace(0, np.nan)

    x = pd.DataFrame(index=f.index)
    x["fi_big_imb_last1h"] = f["big_net_last"] / f["tot_last"].replace(0, np.nan)
    x["fi_absorb6"] = ratio(f["absorb"], 6)
    x["fi_mid_imb6"] = ratio(f["mid_net"], 6)
    b = np.log1p(f["burst_max"] / f["tot_mean"].replace(0, np.nan))
    x["fi_burst_z"] = (b - b.rolling(540, min_periods=270).mean()) / b.rolling(540, min_periods=270).std()
    x.loc[tot == 0] = np.nan
    return x.reindex(bar_open)[list(FI)]
