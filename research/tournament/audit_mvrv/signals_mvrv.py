"""audit_mvrv M1 signal — independent blind implementation (PLAN.md).

Rule: BTC MVRV-z from frozen data/raw/onchain_20260924/btc.csv (CapMVRVCur):
  zM(D) = (MVRV(D) - mean(W)) / std(W, ddof=1), W = trailing up-to-365 daily values
  ending at D inclusive, min 180 non-NaN else NaN; std==0 -> NaN.
Availability: day D usable from D+1 02:00 UTC; D*(T) = max{D : D+1 02:00 UTC <= T}.
Gate M1: all majors' book LONG rows x0.5 while z(T) > 2.0, else x1.0 (NaN -> 1.0).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BTC_CSV = ROOT / "data/raw/onchain_20260924/btc.csv"

WIN = 365
MINP = 180
THRESH = 2.0
GATE_MULT = 0.5
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")


def load_mvrv_daily(csv_path: Path | str = BTC_CSV) -> pd.Series:
    """Daily MVRV series indexed by UTC midnight (day D)."""
    df = pd.read_csv(csv_path, usecols=["time", "CapMVRVCur"])
    t = pd.to_datetime(df["time"], utc=True)
    day = t.dt.floor("D")
    s = pd.Series(df["CapMVRVCur"].to_numpy(dtype=float), index=day)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    s.index.name = "day"
    return s


def compute_zm(mvrv: pd.Series, win: int = WIN, minp: int = MINP) -> pd.Series:
    """Trailing z-score ending at D inclusive (causal in D)."""
    mvrv = mvrv.sort_index()
    mean = mvrv.rolling(win, min_periods=minp).mean()
    std = mvrv.rolling(win, min_periods=minp).std(ddof=1)
    z = (mvrv - mean) / std
    z = z.where(std.fillna(0) != 0)
    z[std.isna()] = np.nan
    return z


def z_at_T(T: pd.DatetimeIndex, zm: pd.Series) -> pd.Series:
    """Map daily zM to decision times T via D+1 02:00 UTC availability.

    D*(T) = max{D : D+1 02:00 UTC <= T}. Implemented as merge_asof backward of
    (T - 02:00) floored to day onto zm's day index.
    """
    T = pd.to_datetime(T, utc=True)
    days = pd.DatetimeIndex(sorted(set(zm.index.floor("D"))))
    z = zm.reindex(days)
    # availability time of each day D
    avail = days + pd.Timedelta(days=1, hours=2)
    # for each T, last avail <= T
    pos = np.searchsorted(avail.values, T.values, side="right") - 1
    out = pd.Series(np.nan, index=T)
    ok = pos >= 0
    out.iloc[ok] = z.to_numpy()[pos[ok]]
    out.index.name = "T"
    return out


def m1_multiplier(zT: pd.Series, thresh: float = THRESH) -> pd.Series:
    """Per-T M1 multiplier: 0.5 when z > thresh else 1.0 (NaN -> 1.0)."""
    m = pd.Series(1.0, index=zT.index)
    m[zT.fillna(-np.inf) > thresh] = GATE_MULT
    return m


def apply_gate(sb: pd.DataFrame, mult: pd.Series) -> pd.DataFrame:
    """Apply per-T multiplier to LONG rows (bear-filtered weight > 0) of standard books.

    Rows before CUTOFF are never gated (v426 convention). Shorts/flats unchanged.
    """
    mult = mult.reindex(sb.index).fillna(1.0)
    gated = sb.copy()
    allow = sb.index >= CUTOFF
    for c in sb.columns:
        long_rows = (sb[c] > 0) & allow
        gated.loc[long_rows, c] = sb.loc[long_rows, c] * mult.loc[long_rows.index[long_rows]].to_numpy()
    return gated


def control_multiplier(sb: pd.DataFrame, mult: pd.Series,
                       anchors=("2021-09-24", "2022-09-24", "2023-09-24",
                                "2024-09-24", "2025-09-24")) -> tuple[pd.DataFrame, dict]:
    """Exposure-matched control: per-year constant = realised mean mult over LONG rows."""
    mult = mult.reindex(sb.index).fillna(1.0)
    ctrl = sb.copy()
    means: dict[str, float] = {}
    for a in anchors:
        a0 = pd.Timestamp(a, tz="UTC")
        seg = (sb.index >= max(a0, CUTOFF)) & (sb.index < a0 + pd.Timedelta(days=365))
        vals = []
        for c in sb.columns:
            lr = seg & (sb[c] > 0).to_numpy()
            if lr.any():
                vals.append(mult.to_numpy()[lr])
        m = float(np.concatenate(vals).mean()) if vals and len(np.concatenate(vals)) else 1.0
        means[a] = m
        for c in sb.columns:
            lr = seg & (sb[c] > 0).to_numpy()
            ctrl.loc[lr, c] = sb.to_numpy()[lr, sb.columns.get_loc(c)] * m
    return ctrl, means


def gated_share(sb: pd.DataFrame, mult: pd.Series,
                anchors=("2021-09-24", "2022-09-24", "2023-09-24",
                         "2024-09-24", "2025-09-24")) -> dict:
    """Share of book long rows gated (mult != 1) + mean multiplier per anchor year."""
    mult = mult.reindex(sb.index).fillna(1.0)
    out: dict[str, dict] = {}
    for a in anchors:
        a0 = pd.Timestamp(a, tz="UTC")
        seg = (sb.index >= a0) & (sb.index < a0 + pd.Timedelta(days=365))
        n_long = int(sum(((sb[c] > 0) & seg).sum() for c in sb.columns))
        n_gate = 0
        acc = []
        for c in sb.columns:
            lr = ((sb[c] > 0) & seg).to_numpy()
            n_gate += int((mult.to_numpy()[lr] != 1.0).sum())
            if lr.any():
                acc.append(mult.to_numpy()[lr])
        mean_m = float(np.concatenate(acc).mean()) if acc and len(np.concatenate(acc)) else 1.0
        out[a] = dict(n_long=n_long, n_gated=n_gate,
                      share=round(n_gate / n_long, 4) if n_long else 0.0,
                      mean_mult=round(mean_m, 4))
    return out
