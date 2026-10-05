"""N1 Wikipedia attention features. Pure functions of view history (causality-testable).

Conventions: `views` is a DataFrame indexed by UTC date (pd.Timestamp, tz-naive midnight),
columns = coins [BTC, ETH, SOL, BNB, XRP], values = daily views (union across title variants).
Feature row D uses only views on days <= D; trailing statistics end at D-1. Row D is usable
from D+1 00:00 UTC only (day-D pageviews complete after D 23:59 UTC).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

COINS = ["BTC", "ETH", "SOL", "BNB", "XRP"]
ZWIN = 90


def load_views(raw_dir: str | Path) -> pd.DataFrame:
    """Union daily views per coin across title variants from raw yearly JSON chunks."""
    raw_dir = Path(raw_dir)
    per_coin: dict[str, pd.Series] = {}
    for coin in COINS:
        acc: dict[pd.Timestamp, float] = {}
        for f in sorted(raw_dir.glob(f"wiki_{coin}_*.json")):
            payload = json.loads(f.read_text())
            for it in payload.get("items", []):
                day = pd.Timestamp(it["timestamp"][:8], tz="UTC").tz_localize(None)
                acc[day] = acc.get(day, 0.0) + float(it["views"])
        s = pd.Series(acc, dtype=float).sort_index()
        s.index.name = "day"
        per_coin[coin] = s
    days = pd.DatetimeIndex(sorted({d for s in per_coin.values() for d in s.index}))
    out = pd.DataFrame({c: per_coin[c].reindex(days) for c in COINS}, index=days)
    out.index.name = "day"
    return out


def compute_features(views: pd.DataFrame) -> pd.DataFrame:
    """wiki_z90 / wiki_chg7 / wiki_share per (day, coin). Row D uses nothing after day D."""
    views = views.reindex(columns=COINS)
    logv = np.log(views + 1.0)
    roll_mean = logv.shift(1).rolling(ZWIN, min_periods=ZWIN).mean()
    roll_std = logv.shift(1).rolling(ZWIN, min_periods=ZWIN).std(ddof=1).clip(lower=1e-6)
    z90 = (logv - roll_mean) / roll_std
    wk_mean = views.shift(1).rolling(7, min_periods=7).mean()
    chg7 = np.log(views + 1.0) - np.log(wk_mean + 1.0)
    share = views.div(views.sum(axis=1).replace(0.0, np.nan), axis=0)
    feats = {}
    for coin in COINS:
        feats[(coin, "wiki_z90")] = z90[coin]
        feats[(coin, "wiki_chg7")] = chg7[coin]
        feats[(coin, "wiki_share")] = share[coin]
    out = pd.DataFrame(feats)
    out.columns = pd.MultiIndex.from_tuples(out.columns, names=["coin", "feature"])
    return out
