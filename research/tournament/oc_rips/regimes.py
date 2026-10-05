"""oc_rips regimes: slow daily variables from 1m closes, causal day rule.

Every value labelled day D uses ONLY minutes with t < D 00:00 UTC, via daily
closes C(sym, E) = last non-NaN 1m close with open_time < (E+1) 00:00 UTC.
Formulas match research/tournament/oc_regime/regime.py (trend90, volratio,
breadth50) plus below200; universe for breadth50 is the 5 majors (fixed in
PLAN.md so the panel covers the full span to 2026-09-24).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def daily_closes_from_minutes(df: pd.DataFrame) -> pd.Series:
    """df has columns open_time (UTC), close. Returns daily Series (UTC days)."""
    d = df.copy()
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d = d.dropna(subset=["close"]).sort_values("open_time")
    day = d["open_time"].dt.floor("D")
    out = d.groupby(day)["close"].last()
    out.index = pd.to_datetime(out.index, utc=True)
    return out


def build_regimes(daily: pd.DataFrame) -> pd.DataFrame:
    """daily: index=day (00:00 UTC, C of that calendar day), columns=syms."""
    daily = daily.sort_index()
    days = pd.to_datetime(daily.index, utc=True)
    btc = daily["BTCUSDT"] if "BTCUSDT" in daily else daily.iloc[:, 0]
    logc = np.log(btc.where(btc > 0))
    lr = logc.diff()
    reg = pd.DataFrame(index=days, columns=["trend90", "below200", "volratio", "breadth50"],
                       dtype=float)
    closes = daily
    for i, D in enumerate(days):
        # --- trend90: log(C[D-1]/C[D-91]) ---
        if i >= 91:
            c1, c0 = btc.iloc[i - 1], btc.iloc[i - 91]
            if np.isfinite(c1) and np.isfinite(c0) and c1 > 0 and c0 > 0:
                reg.at[D, "trend90"] = float(np.log(c1 / c0))
        # --- below200: C[D-1] < mean of 200 closes ending D-1 ---
        if i >= 200:
            w = btc.iloc[i - 200:i]
            if int(w.notna().sum()) == 200 and (w > 0).all():
                reg.at[D, "below200"] = float(1.0 if w.iloc[-1] < w.mean() else 0.0)
        # --- volratio: std30 / median(trailing 30d stds, 365) ---
        if i >= 394:
            seg = lr.iloc[i - 394:i]
            stds = seg.rolling(30, min_periods=30).std().dropna()
            if len(stds) >= 360 and np.isfinite(stds.iloc[-1]) and stds.iloc[-1] > 0:
                med = float(stds.iloc[-365:].median())
                if med > 0:
                    reg.at[D, "volratio"] = float(stds.iloc[-1] / med)
        # --- breadth50 over the 5 majors ---
        if i >= 50:
            w = closes.iloc[i - 50:i]
            sma = w.mean()
            last = w.iloc[-1]
            ok = last.notna() & sma.notna() & (w.notna().sum() == 50)
            if int(ok.sum()) >= 1:
                reg.at[D, "breadth50"] = float((last[ok] > sma[ok]).mean())
    reg.index = pd.to_datetime(reg.index, utc=True)
    return reg


def regimes_truncated(daily: pd.DataFrame, day: pd.Timestamp) -> pd.Series:
    """Regime row for `day` from daily closes of days < day only (probe)."""
    day = pd.Timestamp(day)
    day = day.tz_convert("UTC") if day.tzinfo is not None else day.tz_localize("UTC")
    day = day.floor("D")
    past = daily[daily.index < day]
    reg = build_regimes(past.reindex(past.index.union(pd.DatetimeIndex([day]))))
    return reg.loc[day] if day in reg.index else pd.Series(dtype=float)
