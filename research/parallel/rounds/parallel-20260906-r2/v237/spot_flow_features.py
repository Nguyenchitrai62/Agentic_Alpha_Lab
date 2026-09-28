"""Spot vs perpetual large-order taker flow features (registry v237, fixed before evaluation).

Inputs (per UTC 4h bar and notional tier, taker buy / sell notional and count; rows known at the bar close):
  data/raw/aggflow_spot_20260928/{SYM}_flow_4h.parquet  Binance SPOT aggTrades (scripts/fetch_aggtrades_flow.py --market spot)
  data/raw/aggflow_20260928/{SYM}_flow_4h.parquet       Binance USD-M aggTrades (v236)
Features (rolling over rows <= t only):
  sp_big_imb6    spot (buy - sell) of the >= 100k tiers / spot total notional over 6 bars
  sp_big_imb42   the same over 42 bars
  sp_ret_imb6    spot (buy - sell) of the < 10k tier / spot total over 6 bars (spot retail)
  sp_perp_div6   sp_big_imb6 - perp big imbalance over 6 bars (spot-led vs perp-led large-order flow)
  sp_share_z     z-score (540 bars) of the 6-bar spot share of the spot + perp notional
NaN before the spot archive starts (fetched from 2019-06) or where either archive has a gap.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SP = ("sp_big_imb6", "sp_big_imb42", "sp_ret_imb6", "sp_perp_div6", "sp_share_z")
DS, DP = Path("data/raw/aggflow_spot_20260928"), Path("data/raw/aggflow_20260928")
TIERS = ("lt10k", "10k_100k", "100k_1m", "ge1m")
BIG = ("100k_1m", "ge1m")


def _load(d: Path, sym: str) -> pd.DataFrame | None:
    p = d / f"{sym}_flow_4h.parquet"
    if not p.exists():
        return None
    f = pd.read_parquet(p).sort_index()
    return f.reindex(pd.date_range(f.index[0], f.index[-1], freq="4h", tz="UTC")).fillna(0.0)


def _parts(f: pd.DataFrame):
    tot = sum(f.get(f"buy_{k}", 0.0) + f.get(f"sell_{k}", 0.0) for k in TIERS)
    big = sum(f.get(f"buy_{k}", 0.0) - f.get(f"sell_{k}", 0.0) for k in BIG)
    ret = f.get("buy_lt10k", 0.0) - f.get("sell_lt10k", 0.0)
    return tot, big, ret


def spot_flow_features(sym: str, bar_open: pd.DatetimeIndex) -> pd.DataFrame:
    s, p = _load(DS, sym), _load(DP, sym)
    out = pd.DataFrame(index=bar_open, columns=list(SP), dtype=float)
    if s is None:
        return out
    idx = s.index if p is None else s.index.union(p.index)
    s = s.reindex(idx)
    stot, sbig, sret = _parts(s.fillna(0.0))
    stot = stot.where(s.notna().all(axis=1))

    def ratio(num, den, n):
        return num.rolling(n, min_periods=n).sum() / den.rolling(n, min_periods=n).sum().replace(0, np.nan)

    x = pd.DataFrame(index=idx)
    x["sp_big_imb6"], x["sp_big_imb42"] = ratio(sbig, stot, 6), ratio(sbig, stot, 42)
    x["sp_ret_imb6"] = ratio(sret, stot, 6)
    if p is not None:
        p = p.reindex(idx)
        ptot, pbig, _ = _parts(p.fillna(0.0))
        ptot = ptot.where(p.notna().all(axis=1))
        x["sp_perp_div6"] = x["sp_big_imb6"] - ratio(pbig, ptot, 6)
        share = stot.rolling(6, min_periods=6).sum() / (stot + ptot).rolling(6, min_periods=6).sum()
        x["sp_share_z"] = (share - share.rolling(540, min_periods=270).mean()) / share.rolling(540, min_periods=270).std()
    else:
        x["sp_perp_div6"] = np.nan
        x["sp_share_z"] = np.nan
    x.loc[stot.fillna(0) == 0] = np.nan
    return x.reindex(bar_open)[list(SP)]
