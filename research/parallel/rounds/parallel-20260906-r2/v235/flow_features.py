"""Large-order ("whale") vs retail taker-flow features from Binance aggTrades 4h aggregates (registry v235, fixed before evaluation).

Input: data/raw/aggflow_20260928/{SYM}_flow_4h.parquet (scripts/fetch_aggtrades_flow.py): per UTC 4h bar and notional tier
(lt10k, 10k_100k, 100k_1m, ge1m USDT) the taker-buy notional, taker-sell notional and count. A bar's aggregate uses only trades
inside the bar, so the row of bar t is known at its close (t + 4h). Rolling statistics use rows <= t only.
  fl_big_imb6   (buy - sell) of the >= 100k tiers / total notional, summed over the last 6 bars (1 day)
  fl_big_imb42  the same over 42 bars (7 days)
  fl_ret_imb6   (buy - sell) of the < 10k tier / total notional over 6 bars (retail)
  fl_div6       fl_big_imb6 - fl_ret_imb6 (large orders vs retail)
  fl_big_share_z  z-score (540 bars) of the 6-bar share of >= 100k notional in the total
  fl_whale_n_z    z-score (540 bars) of the 6-bar count of >= 1M trades (log1p)
NaN before the archive starts (2020-01; later for SOL / BNB / XRP), as the other late-starting data (options, premium).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FL = ("fl_big_imb6", "fl_big_imb42", "fl_ret_imb6", "fl_div6", "fl_big_share_z", "fl_whale_n_z")
D = Path("data/raw/aggflow_20260928")
BIG = ("100k_1m", "ge1m")


def flow_features(sym: str, bar_open: pd.DatetimeIndex) -> pd.DataFrame:
    f = pd.read_parquet(D / f"{sym}_flow_4h.parquet").sort_index()
    f = f.reindex(pd.date_range(f.index[0], f.index[-1], freq="4h", tz="UTC")).fillna(0.0)
    tiers = ("lt10k", "10k_100k", "100k_1m", "ge1m")
    tot = sum(f.get(f"buy_{k}", 0.0) + f.get(f"sell_{k}", 0.0) for k in tiers)
    big = sum(f.get(f"buy_{k}", 0.0) - f.get(f"sell_{k}", 0.0) for k in BIG)
    bigv = sum(f.get(f"buy_{k}", 0.0) + f.get(f"sell_{k}", 0.0) for k in BIG)
    ret = f.get("buy_lt10k", 0.0) - f.get("sell_lt10k", 0.0)
    wn = np.log1p(f.get("n_ge1m", 0.0).rolling(6, min_periods=6).sum())

    def ratio(num, n):
        return num.rolling(n, min_periods=n).sum() / tot.rolling(n, min_periods=n).sum().replace(0, np.nan)

    def z(s):
        return (s - s.rolling(540, min_periods=270).mean()) / s.rolling(540, min_periods=270).std()

    x = pd.DataFrame(index=f.index)
    x["fl_big_imb6"], x["fl_big_imb42"] = ratio(big, 6), ratio(big, 42)
    x["fl_ret_imb6"] = ratio(ret, 6)
    x["fl_div6"] = x["fl_big_imb6"] - x["fl_ret_imb6"]
    x["fl_big_share_z"] = z(ratio(bigv, 6))
    x["fl_whale_n_z"] = z(wn)
    x.loc[tot == 0] = np.nan  # archive gaps
    return x.reindex(bar_open)[list(FL)]
