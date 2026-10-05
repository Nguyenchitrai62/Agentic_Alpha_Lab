"""oc_regime: slow daily market-regime variables from hourly bars (causal).

Every regime value labelled day D (00:00 UTC) uses ONLY bars with t < D.
Daily close C(sym, day) = close of the last hourly bar of `day`
(missing days -> NaN, never forward-filled across days for trend math;
correlations/breadth use pairwise-complete data).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HOURLY = ROOT / "research/tournament/data/hourly.parquet"
RAW = ROOT / "data/raw"
BTC_DIR = RAW / "btc_intraday_20260924"
MAJORS_DIR = RAW / "majors_intraday_20260924"
ALTS26_DIR = RAW / "alts_intraday_20260926"
ALTS30_DIR = RAW / "alts2020_intraday_20260930"
HOURLY_END_DAY = pd.Timestamp("2025-09-23", tz="UTC").date()  # last day in hourly.parquet

VARS = ["trend30", "trend90", "volratio", "corr30", "stress30", "breadth50", "dd90", "vollevel"]


def load_hourly() -> pd.DataFrame:
    h = pd.read_parquet(HOURLY)
    h["t"] = pd.to_datetime(h["t"], utc=True)
    return h.sort_values("t").reset_index(drop=True)


def daily_closes_from_hourly(h: pd.DataFrame) -> pd.DataFrame:
    """Pivot to daily closes; day D = close of last bar with floor(t)=D (< D+1 00:00)."""
    h = h.copy()
    h["day"] = h["t"].dt.floor("D")
    h = h.sort_values("t")
    last = h.groupby(["sym", "day"], observed=True)["close"].last()
    daily = last.unstack("sym").sort_index()
    daily.index = pd.to_datetime(daily.index, utc=True)
    return daily


def load_1m_close(sym: str) -> pd.Series:
    """1m close series for one sym (raw dirs); index = bar open_time (UTC)."""
    if sym == "BTCUSDT":
        files = sorted(BTC_DIR.glob("klines_1m_*.parquet"))
        parts = [pd.read_parquet(f, columns=["open_time", "close"]) for f in files]
        m = pd.concat(parts)
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    else:
        files = sorted(MAJORS_DIR.glob(f"{sym}_1m_*.parquet")) or \
            sorted(ALTS26_DIR.glob(f"{sym}_1m_*.parquet")) or \
            sorted(ALTS30_DIR.glob(f"{sym}_1m_*.parquet"))
        if not files:
            raise FileNotFoundError(f"no 1m files for {sym}")
        parts = [pd.read_parquet(f, columns=["open_time", "close"]) for f in files]
        m = pd.concat(parts)
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    return pd.Series(m["close"].to_numpy(float), index=m["open_time"].to_numpy())


def daily_closes_from_1m(syms: list[str]) -> pd.DataFrame:
    """Daily closes from 1m raw (one sym at a time, low RAM); day D = last close with t < D+1."""
    days = {}
    for s in syms:
        c = load_1m_close(s)
        day = pd.to_datetime(c.index, utc=True).floor("D")
        last = c.groupby(day).last()
        last.index = pd.to_datetime(last.index, utc=True)
        days[s] = last
    daily = pd.DataFrame(days).sort_index()
    return daily


def splice_daily(hourly_daily: pd.DataFrame, onem_daily: pd.DataFrame) -> pd.DataFrame:
    """Use hourly-derived closes up to HOURLY_END_DAY, 1m-derived after."""
    cut = pd.Timestamp("2025-09-23", tz="UTC")
    a = hourly_daily[hourly_daily.index <= cut]
    b = onem_daily[onem_daily.index > cut]
    return pd.concat([a, b]).sort_index()


def compute_regimes(daily: pd.DataFrame) -> pd.DataFrame:
    """Daily regime panel; row D uses daily closes of days < D only.

    daily: index = day (00:00 UTC, = C of that calendar day), columns = syms.
    Returns index = regime day D (00:00 UTC), columns = VARS.
    """
    daily = daily.sort_index()
    days = daily.index
    logd = np.log(daily)
    R = logd.diff()  # R.loc[D] = log C(D)/C(D-1)
    btc = daily["BTCUSDT"] if "BTCUSDT" in daily else daily.iloc[:, 0]
    rb = np.log(btc).diff()
    Ridx = R.mean(axis=1, skipna=True).where(R.notna().sum(axis=1) >= 10)
    out = pd.DataFrame(index=days, columns=VARS, dtype=float)
    C = daily
    for i, D in enumerate(days):
        if D < pd.Timestamp("2021-01-01", tz="UTC"):
            continue
        # windows ending at D-1 (strictly before D)
        if i < 1:
            continue
        b1 = btc.iloc[i - 1]
        w30 = R.iloc[max(0, i - 30):i]
        w90 = R.iloc[max(0, i - 90):i]
        if len(w30) == 30 and np.isfinite(b1) and btc.iloc[i - 30] > 0:
            out.at[D, "trend30"] = float(np.log(b1 / btc.iloc[i - 30]))
        if len(w90) == 90 and np.isfinite(b1) and btc.iloc[i - 90] > 0:
            out.at[D, "trend90"] = float(np.log(b1 / btc.iloc[i - 90]))
        tr = rb.iloc[max(0, i - 394):i].rolling(30, min_periods=30).std()
        tr = tr.dropna()
        if len(tr) >= 360 and np.isfinite(tr.iloc[-1]) and tr.iloc[-1] > 0:
            med = float(tr.iloc[-365:].median())
            if med > 0:
                out.at[D, "volratio"] = float(tr.iloc[-1] / med)
        if len(w30) == 30:
            c = w30.corr(min_periods=30)
            vals = c.to_numpy()[np.triu_indices(len(c), 1)]
            vals = vals[np.isfinite(vals)]
            if len(vals) >= 45:  # >= 10 coins worth of pairs
                out.at[D, "corr30"] = float(vals.mean())
        sig_w = Ridx.iloc[max(0, i - 395):max(0, i - 30)]
        if len(sig_w.dropna()) >= 365:
            sig = float(sig_w.dropna().iloc[-365:].std())
            if sig > 0 and len(w30) == 30:
                seg = Ridx.iloc[i - 30:i]
                out.at[D, "stress30"] = float((seg < -3 * sig).sum())
        w50 = C.iloc[max(0, i - 50):i]
        if len(w50) == 50:
            sma = w50.mean()
            ok = w50.iloc[-1].notna() & sma.notna() & (w50.notna().sum() == 50)
            if int(ok.sum()) >= 10:
                out.at[D, "breadth50"] = float((w50.iloc[-1][ok] > sma[ok]).mean())
        w90c = btc.iloc[max(0, i - 90):i]
        if len(w90c) == 90 and np.isfinite(b1):
            mx = float(w90c.max())
            if mx > 0:
                out.at[D, "dd90"] = float(np.log(b1 / mx))
        if len(w30) == 30:
            seg = Ridx.iloc[i - 30:i]
            if int(seg.notna().sum()) == 30:
                out.at[D, "vollevel"] = float(seg.abs().mean())
    out.index = pd.to_datetime(out.index, utc=True)
    return out


def regimes_from_hourly_truncated(h: pd.DataFrame, day: pd.Timestamp) -> pd.Series:
    """Regime row for `day` computed from bars with t < day only (causality probe)."""
    day = pd.Timestamp(day)
    day = day.tz_convert("UTC") if day.tzinfo is not None else day.tz_localize("UTC")
    day = day.floor("D")
    ht = h[h["t"] < day].copy()
    daily = daily_closes_from_hourly(ht)
    if day not in daily.index:
        daily = daily.reindex(daily.index.union(pd.DatetimeIndex([day])))
    reg = compute_regimes(daily)
    return reg.loc[day] if day in reg.index else pd.Series(dtype=float)
