"""oc_lit_fhlh signal: BTC first-30-minute (FH) return gate (H3, PLAN-fixed).

PLAN-fixed definitions (no fits except per-anchor M3 medians):
  Day D = calendar date, 00:00 UTC anchor.
  FH(D) = close(00:29 1m bar) / open(00:00 1m bar) - 1, BTCUSDT perp 1m.
  Uses only bars with open_time in [D 00:00, D 00:29] (close <= 00:29:59.999).
  Availability: FH(D) known at D + 00:30:00 UTC.
  D*(T) = latest D with D+00:30 <= T (T in [D 00:00, D 00:30) uses D-1).
  M3 median: med(A) = median(|FH|) over D in [A-372d, A-7d) per anchor A.
  Variants: M1 longs 1.0 if FH>0 else 0.6; M2 adds shorts 1.0 if FH<0 else 0.6;
  M3 = M1 unless |FH| < med(A) -> 1.0. NaN/unknown -> 1.0.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BTC_DIR = ROOT / "data/raw/btc_intraday_20260924"

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")
GATE_LO = 0.6
MED_LOOKBACK = 372
MED_EMBARGO = 7

_DAILY_CACHE = None


def load_btc_1m() -> pd.DataFrame:
    """BTC 1m open_time/open/close sorted (UTC). Light columns only."""
    parts = []
    for f in sorted(BTC_DIR.glob("klines_1m_*.parquet")):
        d = pd.read_parquet(f, columns=["open_time", "open", "close"])
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.sort_values("open_time").drop_duplicates("open_time")
    return df


def build_daily_fh(m1: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily FH frame: index day D (UTC midnight), columns fh/avail."""
    if m1 is None:
        m1 = load_btc_1m()
    m1 = m1.sort_values("open_time")
    ot = m1["open_time"]
    # Map open_time -> open / close via indexed series.
    m1i = m1.set_index("open_time").sort_index()
    opens = m1i["open"]
    closes = m1i["close"]
    days = pd.date_range(
        (ot.min().floor("D") - pd.Timedelta(days=1)),
        ot.max().ceil("D"),
        freq="D",
        tz="UTC",
    )
    fh_vals = np.full(len(days), np.nan)
    for i, d in enumerate(days):
        try:
            o = float(opens.loc[d])
            c = float(closes.loc[d + pd.Timedelta(minutes=29)])
        except KeyError:
            continue
        if np.isfinite(o) and np.isfinite(c) and o > 0:
            fh_vals[i] = c / o - 1.0
    out = pd.DataFrame({"fh": fh_vals}, index=days)
    out["avail"] = out.index + pd.Timedelta(minutes=30)
    return out


def daily() -> pd.DataFrame:
    global _DAILY_CACHE
    if _DAILY_CACHE is None:
        _DAILY_CACHE = build_daily_fh()
    return _DAILY_CACHE


def medians(daily_df: pd.DataFrame | None = None) -> dict[str, float]:
    """Per-anchor median(|FH|) over [A-372d, A-7d). Keys = 'YYYY-MM-DD'."""
    if daily_df is None:
        daily_df = daily()
    out: dict[str, float] = {}
    for a in ANCH:
        lo = a - pd.Timedelta(days=MED_LOOKBACK)
        hi = a - pd.Timedelta(days=MED_EMBARGO)
        w = daily_df[(daily_df.index >= lo) & (daily_df.index < hi)]["fh"]
        w = w[np.isfinite(w.to_numpy(float))]
        out[str(a.date())] = float(np.median(np.abs(w.to_numpy(float)))) if len(w) >= 200 else float("nan")
    return out


def asof_fh(daily_df: pd.DataFrame, T) -> np.ndarray:
    """Latest known FH at each decision time T (array-like datetimes, UTC)."""
    T = pd.to_datetime(T, utc=True)
    avail_ns = daily_df["avail"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = daily_df["fh"].to_numpy(float)
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(avail_ns, Tns, side="right") - 1
    out = np.full(len(T), np.nan)
    ok = (ii >= 0) & (ii < len(vals))
    out[ok] = vals[ii[ok]]
    return out


def asof_median(daily_df: pd.DataFrame, T, med: dict[str, float] | None = None) -> np.ndarray:
    """Per-T M3 median of its anchor year (NaN before first anchor)."""
    if med is None:
        med = medians(daily_df)
    T = pd.to_datetime(T, utc=True)
    bounds = ANCH + [ANCH[-1] + pd.Timedelta(days=365)]
    out = np.full(len(T), np.nan)
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    for k in range(5):
        sel = (Tns >= bounds[k].value) & (Tns < bounds[k + 1].value)
        out[sel] = med[str(ANCH[k].date())]
    return out


def gate_mults(fh: np.ndarray, med: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """PLAN-fixed multipliers. NaN fh -> 1.0; NaN med in M3 -> 1.0."""
    fh = np.asarray(fh, float)
    m1 = np.ones_like(fh)
    m1[np.isfinite(fh) & (fh <= 0)] = GATE_LO
    s2 = np.ones_like(fh)
    s2[np.isfinite(fh) & ~(fh < 0)] = GATE_LO
    if med is None:
        m3 = m1.copy()
    else:
        med = np.asarray(med, float)
        m3 = np.ones_like(fh)
        strong = np.isfinite(fh) & np.isfinite(med) & (np.abs(fh) >= med)
        m3[strong & (fh <= 0)] = GATE_LO
    return {"M1_long": m1, "M2_short": s2, "M3_long": m3}
