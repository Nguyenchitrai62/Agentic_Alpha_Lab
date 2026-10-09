"""oc_stablegate signal: stablecoin (USDT+USDC) 30d net-creation impulse z.

PLAN-fixed definitions (no fits):
  cap(D) = Cap_usdt(D) + Cap_usdc(D) per UTC day D.
  impulse(D) = log(cap(D) / cap(D-30)).
  z(D) = (impulse(D) - mean(W)) / std(W, ddof=1), W = trailing <=730 impulse
         values ending at D inclusive, min 365 non-NaN else NaN; std==0 -> NaN.
  Availability: day D usable from D+1 04:00 UTC. z(T) = z(D*(T)),
  D*(T) = max{D : D+1 04:00 UTC <= T}; NaN/unknown -> caller uses mult 1.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CSV = ROOT / "data/raw/onchain_20260924/stablecoins.csv"

WIN = 730
MINP = 365
LAG_DAYS = 30
AVAIL = pd.Timedelta(hours=28)  # D 00:00 + 28h = D+1 04:00 UTC


def load_daily() -> pd.DataFrame:
    """Daily summed cap frame: index day (UTC midnight), columns cap/impulse/z."""
    df = pd.read_csv(CSV, parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    piv = df.pivot_table(index="time", columns="asset",
                         values="CapMrktCurUSD", aggfunc="sum").sort_index()
    # Full daily index (no gaps in this file, but reindex to be explicit).
    full = pd.date_range(piv.index.min().floor("D"), piv.index.max().floor("D"),
                         freq="D", tz="UTC")
    piv = piv.reindex(full)
    cap = piv["usdt"] + piv["usdc"]
    out = pd.DataFrame({"cap": cap})
    out["cap_lag30"] = out["cap"].shift(LAG_DAYS)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["impulse"] = np.log(out["cap"] / out["cap_lag30"])
    out.loc[~(out["cap"] > 0) | ~(out["cap_lag30"] > 0), "impulse"] = np.nan
    r = out["impulse"].rolling(WIN, min_periods=MINP)
    mu = r.mean().shift(0)  # window ending at D inclusive (current row included)
    # NOTE: rolling().mean() at row D already uses rows (D-729..D); strictly causal
    # in D. No .shift needed beyond excluding nothing; history only.
    sd = r.std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["z"] = (out["impulse"] - mu) / sd
    out.loc[~np.isfinite(out["z"]), "z"] = np.nan
    # Availability timestamp of each day's z.
    out["avail"] = out.index + AVAIL
    return out


def asof_z(daily: pd.DataFrame, T) -> np.ndarray:
    """Latest known z at each decision time T (array-like datetimes, UTC)."""
    T = pd.to_datetime(T, utc=True)
    avail_ns = daily["avail"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = daily["z"].to_numpy(float)
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(avail_ns, Tns, side="right") - 1
    out = np.full(len(T), np.nan)
    ok = (ii >= 0) & (ii < len(vals))
    out[ok] = vals[ii[ok]]
    return out


def gate_mult(z: np.ndarray, thresh: float, mult: float = 0.75) -> np.ndarray:
    """Book-long multiplier: mult where z < thresh, else 1 (NaN -> 1)."""
    z = np.asarray(z, float)
    m = np.ones_like(z)
    m[np.isfinite(z) & (z < thresh)] = mult
    return m


def dip_mult(z: np.ndarray, mode: str) -> np.ndarray:
    """Dip rung multiplier per PLAN: D1 two-sided, D2 upside-only."""
    z = np.asarray(z, float)
    up = 0.32 / 0.26
    dn = 0.20 / 0.26
    m = np.ones_like(z)
    if mode == "D1":
        m[np.isfinite(z) & (z > 1.0)] = up
        m[np.isfinite(z) & (z < -1.0)] = dn
    elif mode == "D2":
        m[np.isfinite(z) & (z > 1.0)] = up
    else:
        raise ValueError(mode)
    return m
