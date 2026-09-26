"""W4 calendar seasonality: fixed textbook/calendar definitions, causal.

Row t uses only information known at bars.close_time[t]. All buckets are a
pure function of the bar's own UTC open/close timestamps (open_time is known
at open, hence at close), so rows <= cut are identical under truncation.

Recorded fixed definitions (chosen before any event study):
  HOD = open_time.hour (UTC, 0-23). hod_sin/cos = sin/cos(2*pi*HOD/24).
  DOW = open_time.dayofweek (Mon=0..Sun=6). dow_sin/cos = sin/cos(2*pi*DOW/7).
  WEEKEND = DOW >= 5.
  MONTH_START = day <= 2; MONTH_END = day >= last_day_of_month - 1
    (first/last 2 calendar days). Distances in whole days (float).
  SESSIONS (UTC, half-open on opening hour, overlapping allowed):
    Asia 00:00-08:00, EU 07:00-16:00, US 13:00-21:00.
  CME_GAP = Friday >= 21:00 UTC through Sunday < 22:00 UTC
    (Fri hod>=21 -> 1; Sat -> 1; Sun hod<22 -> 1; else 0).
  QEXPIRY = last Friday of Mar/Jun/Sep/Dec at 08:00 UTC.
    days_to = (next_expiry_strictly_after_close - close_time) / 86400.
    days_since = (close_time - last_expiry_at_or_before_close) / 86400.
    is_qexpiry_week = 1 if days_to <= 7 else 0.

No post-hoc tuning. No forward returns are used here.
"""

from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

PREFIX = "sea_"

ASIA_START, ASIA_END = 0, 8
EU_START, EU_END = 7, 16
US_START, US_END = 13, 21
QEXPIRY_MONTHS = (3, 6, 9, 12)
QEXPIRY_HOUR_UTC = 8


def _last_friday(year: int, month: int) -> int:
    last_day = calendar.monthrange(year, month)[1]
    dt = pd.Timestamp(year=year, month=month, day=last_day, tz="UTC")
    # Monday=0..Sunday=6; Friday=4
    back = (dt.dayofweek - 4) % 7
    return last_day - back


def _quarterly_expiries(year: int) -> list[pd.Timestamp]:
    return [
        pd.Timestamp(year=year, month=m, day=_last_friday(year, m),
                     hour=QEXPIRY_HOUR_UTC, tz="UTC")
        for m in QEXPIRY_MONTHS
    ]


def _days_to_since_qexpiry(close_ts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized next/last quarterly expiry distances in days (float)."""
    c = pd.to_datetime(close_ts, utc=True)
    years = np.unique(c.dt.year.to_numpy())
    exps: list[pd.Timestamp] = []
    for y in list(years) + [int(years.min()) - 1, int(years.max()) + 1]:
        exps.extend(_quarterly_expiries(int(y)))
    exps = np.array(sorted(set(exps)))
    exp_ns = np.array([e.value for e in exps], dtype="int64")
    cv_ns = c.to_numpy(dtype="datetime64[ns]").astype("int64")
    nxt_pos = np.searchsorted(exp_ns, cv_ns, side="right")  # strictly after close
    prv_pos = np.searchsorted(exp_ns, cv_ns, side="right") - 1  # at-or-before close
    nxt_pos = np.clip(nxt_pos, 0, len(exp_ns) - 1)
    prv_pos = np.clip(prv_pos, 0, len(exp_ns) - 1)
    to_days = (exp_ns[nxt_pos] - cv_ns) / 86_400_000_000_000.0
    since_days = (cv_ns - exp_ns[prv_pos]) / 86_400_000_000_000.0
    return to_days.astype(float), since_days.astype(float)


def _timebase(bars: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    ot = pd.to_datetime(bars["open_time"], utc=True)
    if "close_time" in bars:
        ct = pd.to_datetime(bars["close_time"], utc=True)
    else:
        ct = ot
    return ot, ct


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    ot, ct = _timebase(bars)
    hod = ot.dt.hour.astype(float)
    dow = ot.dt.dayofweek.astype(float)
    day = ot.dt.day.astype(float)
    last_day = ot.apply(lambda t: float(calendar.monthrange(t.year, t.month)[1]))

    hod_sin = np.sin(2 * np.pi * hod / 24.0)
    hod_cos = np.cos(2 * np.pi * hod / 24.0)
    dow_sin = np.sin(2 * np.pi * dow / 7.0)
    dow_cos = np.cos(2 * np.pi * dow / 7.0)

    is_weekend = (dow >= 5).astype(float)
    is_month_start = (day <= 2).astype(float)
    is_month_end = (day >= last_day - 1).astype(float)
    days_from_start = (day - 1).astype(float)
    days_to_end = (last_day - day).astype(float)

    h = ot.dt.hour.to_numpy()
    sess_asia = ((h >= ASIA_START) & (h < ASIA_END)).astype(float)
    sess_eu = ((h >= EU_START) & (h < EU_END)).astype(float)
    sess_us = ((h >= US_START) & (h < US_END)).astype(float)

    dow_i = ot.dt.dayofweek.to_numpy()
    cme = (
        ((dow_i == 4) & (h >= 21)) | (dow_i == 5) | ((dow_i == 6) & (h < 22))
    ).astype(float)

    to_q, since_q = _days_to_since_qexpiry(ct)
    is_qweek = (to_q <= 7.0).astype(float)

    out = pd.DataFrame(
        {
            "sea_hod": hod.to_numpy(float),
            "sea_hod_sin": hod_sin.to_numpy(float),
            "sea_hod_cos": hod_cos.to_numpy(float),
            "sea_dow": dow.to_numpy(float),
            "sea_dow_sin": dow_sin.to_numpy(float),
            "sea_dow_cos": dow_cos.to_numpy(float),
            "sea_is_weekend": is_weekend.to_numpy(float),
            "sea_is_month_start": is_month_start.to_numpy(float),
            "sea_is_month_end": is_month_end.to_numpy(float),
            "sea_days_from_month_start": days_from_start.to_numpy(float),
            "sea_days_to_month_end": days_to_end.to_numpy(float),
            "sea_sess_asia": sess_asia,
            "sea_sess_eu": sess_eu,
            "sea_sess_us": sess_us,
            "sea_cme_gap_window": cme,
            "sea_days_to_qexpiry": to_q,
            "sea_days_since_qexpiry": since_q,
            "sea_is_qexpiry_week": is_qweek,
        },
        index=bars.index,
    )
    return out.astype(float)


DOW_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def events(bars: pd.DataFrame) -> pd.DataFrame:
    """Bucket dummies, all direction +1 (1 in bucket else 0), int8."""
    ot, _ = _timebase(bars)
    h = ot.dt.hour.to_numpy()
    d = ot.dt.dayofweek.to_numpy()
    out = pd.DataFrame(index=bars.index)
    for hh in range(24):
        out[f"sea_ev_hod_{hh:02d}"] = np.where(h == hh, np.int8(1), np.int8(0)).astype(np.int8)
    for i, name in enumerate(DOW_NAMES):
        out[f"sea_ev_dow_{name}"] = np.where(d == i, np.int8(1), np.int8(0)).astype(np.int8)
    out["sea_ev_sess_asia"] = np.where((h >= ASIA_START) & (h < ASIA_END), np.int8(1), np.int8(0)).astype(np.int8)
    out["sea_ev_sess_eu"] = np.where((h >= EU_START) & (h < EU_END), np.int8(1), np.int8(0)).astype(np.int8)
    out["sea_ev_sess_us"] = np.where((h >= US_START) & (h < US_END), np.int8(1), np.int8(0)).astype(np.int8)
    return out.astype("int8")
