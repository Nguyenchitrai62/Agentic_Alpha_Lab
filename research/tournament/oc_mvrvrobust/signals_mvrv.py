"""oc_mvrvrobust signals: frozen M1 + jitter mults (PLAN-fixed, copy of oc_lit_position H8 part).

MVRV(D) = CapMVRVCur(D) (daily UTC; ratio itself).
zM(D) = (MVRV - mean(W)) / std(W, ddof=1), W = trailing <= WIN daily values
        ending at D inclusive, min MINP else NaN; std==0 -> NaN.
Day D usable from D+1 02:00 UTC; z(T) = zM(D*(T)).
Frozen M1: WIN=365, MINP=180, thr 2.0, mult 0.5 on longs.
Jitters (one knob each): thr 1.75 / 2.25; WIN 270 / 450 (MINP stays 180).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

BTC_CSV = ROOT / "data" / "raw" / "onchain_20260924" / "btc.csv"
H8_MINP = 180
H8_AVAIL = pd.Timedelta(hours=26)  # D 00:00 + 26h = D+1 02:00 UTC
BOOK_MULT = 0.5

FROZEN = dict(win=365, thresh=2.0, mult=BOOK_MULT)
JITTERS = {
    "J_T175": dict(win=365, thresh=1.75, mult=BOOK_MULT),
    "J_T225": dict(win=365, thresh=2.25, mult=BOOK_MULT),
    "J_W270": dict(win=270, thresh=2.0, mult=BOOK_MULT),
    "J_W450": dict(win=450, thresh=2.0, mult=BOOK_MULT),
}


def load_mvrv_daily(win: int = 365) -> pd.DataFrame:
    """Daily MVRV frame for a given trailing window (causal, D-inclusive)."""
    df = pd.read_csv(BTC_CSV, parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates("time").sort_values("time")
    day = df["time"].dt.floor("D")
    df = df.assign(day=day).drop_duplicates("day").sort_values("day")
    full = pd.date_range(df["day"].min(), df["day"].max(), freq="D", tz="UTC")
    df = df.set_index("day").reindex(full)
    mvrv = df["CapMVRVCur"].to_numpy(dtype=float)
    out = pd.DataFrame({"mvrv": mvrv}, index=full)
    r = out["mvrv"].rolling(win, min_periods=H8_MINP)
    mu = r.mean()
    sd = r.std(ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["z"] = (out["mvrv"] - mu) / sd
    out.loc[~np.isfinite(out["z"]), "z"] = np.nan
    out["avail"] = out.index + H8_AVAIL
    return out


def h8_asof_z(daily: pd.DataFrame, T) -> np.ndarray:
    T = pd.to_datetime(T, utc=True)
    avail_ns = daily["avail"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = daily["z"].to_numpy(float)
    Tns = pd.to_datetime(T, utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(avail_ns, Tns, side="right") - 1
    out = np.full(len(T), np.nan)
    ok = (ii >= 0) & (ii < len(vals))
    out[ok] = vals[ii[ok]]
    return out


def m1_mults(z: np.ndarray, thresh: float = 2.0, mult: float = BOOK_MULT) -> np.ndarray:
    z = np.asarray(z, float)
    m = np.ones_like(z)
    m[np.isfinite(z) & (z > thresh)] = mult
    return m


def gate_mults(T, thresh: float = 2.0, win: int = 365) -> tuple[np.ndarray, np.ndarray]:
    """(z(T), mult(T)) for decision times T under given knob settings."""
    d = load_mvrv_daily(win=win)
    Tts = pd.to_datetime(T, utc=True)
    z = h8_asof_z(d, Tts)
    return z, m1_mults(z, thresh)
