"""N2 CME weekend-gap features. Pure functions of (CME daily closes, Binance hourly bars).

Friday settlement proxy = Yahoo BTC=F / ETH=F Friday daily-bar close (CME ~16:00 CT settlement).
Sunday reopen = Binance {BTC,ETH}USDT hourly open at 22:00 UTC in US daylight time
(second Sunday of March .. first Sunday of November) else 23:00 UTC (CME Globex 17:00 CT).
gap_sigma = ln(reopen/settle) / sigma90 (sigma90 = trailing-90d std of Binance daily log
returns ending Friday, strictly causal). gap_fill_MF = 1 if Mon..Fri hourly range touches settle.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

SYMS = {"BTC": "BTC=F", "ETH": "ETH=F"}
SPOT = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}


def _dst_bounds(year: int) -> tuple[dt.date, dt.date]:
    """(dst_start, dst_end) Sundays: 2nd Sun of March .. 1st Sun of November (US rule)."""
    march1 = dt.date(year, 3, 1)
    # first Sunday of March: 7 - weekday(Mar1)%... weekday Mon=0..Sun=6
    first_sun_mar = march1 + dt.timedelta(days=(6 - march1.weekday()) % 7)
    dst_start = first_sun_mar + dt.timedelta(days=7)
    nov1 = dt.date(year, 11, 1)
    dst_end = nov1 + dt.timedelta(days=(6 - nov1.weekday()) % 7)
    return dst_start, dst_end


def sunday_reopen_hour(sunday: pd.Timestamp) -> pd.Timestamp:
    """UTC hour of the CME Globex Sunday reopen for a given Sunday date."""
    start, end = _dst_bounds(sunday.year)
    d = sunday.date()
    hour = 22 if (start <= d < end) else 23
    return pd.Timestamp(sunday.year, sunday.month, sunday.day, hour, tz="UTC")


def load_cme_daily(raw_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Yahoo chart payloads -> {coin: DataFrame(date, close)} with tz-aware UTC midnight dates."""
    raw_dir = Path(raw_dir)
    out = {}
    for coin, sym in SYMS.items():
        f = raw_dir / f"cme_{sym.replace('=', '')}_daily.json"
        payload = json.loads(f.read_text())["chart"]["result"][0]
        ts = payload["timestamp"]
        q = payload["indicators"]["quote"][0]
        df = pd.DataFrame({
            "date": [pd.Timestamp(t, unit="s", tz="UTC").normalize() for t in ts],
            "open": q.get("open"), "high": q.get("high"),
            "low": q.get("low"), "close": q.get("close"),
        }).dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        out[coin] = df
    return out


def weekend_gaps(cme: dict[str, pd.DataFrame], hourly: pd.DataFrame) -> pd.DataFrame:
    """One row per (coin, Friday date). Columns: friday, settle, reopen, sigma90, gap_sigma,
    gap_abs, gap_fill_MF (NaN when inputs missing)."""
    hourly = hourly.copy()
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    spot = {c: s[s["sym"] == SPOT[c]].set_index("t").sort_index() for c, s in
            [("BTC", hourly), ("ETH", hourly)]}
    # Binance daily opens at 00:00 UTC per coin (for sigma90)
    daily_open = {}
    for c, s in spot.items():
        d = s["open"].resample("1h").first()  # hourly grid guard
        daily_open[c] = d[d.index.time == dt.time(0, 0)]
    rows = []
    for coin, df in cme.items():
        df = df.copy()
        df["dow"] = df["date"].dt.dayofweek
        fridays = df[df["dow"] == 4]
        logret = np.log(daily_open[coin] / daily_open[coin].shift(1))
        for _, fr in fridays.iterrows():
            fri = fr["date"]
            settle = float(fr["close"])
            hist = logret[logret.index < fri].tail(90)
            sigma90 = float(hist.std(ddof=1)) if len(hist) >= 60 else np.nan
            sunday = (fri + pd.Timedelta(days=2)).normalize()
            rh = sunday_reopen_hour(sunday)
            sp = spot[coin]
            reopen = float(sp["open"].get(rh, np.nan)) if rh in sp.index else np.nan
            mon = (fri + pd.Timedelta(days=3)).normalize()
            end = (fri + pd.Timedelta(days=8)).normalize()
            wk = sp[(sp.index >= mon) & (sp.index < end)]
            filled = (bool((wk["low"].min() <= settle) and (wk["high"].max() >= settle))
                      if len(wk) else np.nan)
            gap = np.log(reopen / settle) / sigma90 if np.isfinite(reopen) and np.isfinite(sigma90) and sigma90 > 0 else np.nan
            rows.append(dict(coin=coin, friday=fri.normalize(), settle=settle, reopen=reopen,
                             sigma90=sigma90, gap_sigma=gap,
                             gap_abs=abs(gap) if np.isfinite(gap) else np.nan,
                             gap_fill_MF=filled))
    return pd.DataFrame(rows)
