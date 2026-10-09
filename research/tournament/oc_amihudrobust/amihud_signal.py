"""oc_amihudrobust signal: parameterised Amihud XS tilt (frozen A1 + jitters).

Copied logic from research/tournament/oc_lit_xs/xs_signal.py (not edited there).
PLAN-fixed, causal:

  Daily per coin D (UTC midnight): r_d = close_d/close_{d-1} - 1.
  amihud_d = |r_d| / quote_volume_d (NaN if quote missing/non-positive).
  AmihudW(D) = mean(amihud over D-W+1..D), min_periods = round(W*2/3)
    (base W=30/min20; jitters W=20/min13, W=45/min30).
  Decision time T (4h bar timestamp): D*(T) = date(T) - 1 day
  (day D usable iff D+1 00:00 <= T). Raws at T use only days <= D*(T).
  XS z at same T only: z = (x-mean)/std(ddof=1) across finite syms;
  <2 finite or std==0/non-finite -> 0 for finite raws; NaN raw -> NaN.
  Multiplier (clip [0.5,1.5], NaN->1): A1 both-legs 1+K*z_illiq.

Source: data/raw/xs_universe_20260924/<SYM>_1d.parquet (full span, see PLAN).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
XSDIR = ROOT / "data/raw/xs_universe_20260924"

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
K_BASE = 0.25
W_BASE, MIN_BASE = 30, 20
LO, HI = 0.5, 1.5

_daily_cache: dict[str, pd.DataFrame] = {}
_raw_cache: dict[tuple, np.ndarray] = {}


def load_daily(sym: str) -> pd.DataFrame:
    """Daily raw frame for one symbol, indexed by day midnight UTC.

    Columns: close, quote_volume, r, amihud_d.
    Reindexed to a full consecutive daily index (gaps stay NaN, no ffill).
    """
    if sym in _daily_cache:
        return _daily_cache[sym]
    f = XSDIR / f"{sym}_1d.parquet"
    df = pd.read_parquet(f, columns=["open_time", "close", "quote_volume"])
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.sort_values("open_time")
    day = df["open_time"].dt.floor("D")
    df = df.assign(day=day).groupby("day", as_index=True).last(numeric_only=False)
    df = df[["close", "quote_volume"]]
    df.index = pd.to_datetime(df.index, utc=True)
    full = pd.date_range(df.index.min(), df.index.max(), freq="D", tz="UTC")
    df = df.reindex(full)
    close = pd.to_numeric(df["close"], errors="coerce").astype(float)
    qv = pd.to_numeric(df["quote_volume"], errors="coerce").astype(float)
    r = close / close.shift(1) - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        amihud_d = r.abs() / qv
    amihud_d[(~np.isfinite(r)) | ~(qv > 0)] = np.nan
    out = pd.DataFrame({"close": close, "quote_volume": qv, "r": r,
                        "amihud_d": amihud_d})
    _daily_cache[sym] = out
    return out


def amihud_window(d: pd.DataFrame, W: int, minp: int) -> pd.Series:
    return d["amihud_d"].rolling(W, min_periods=minp).mean()


def d_last(T: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last fully-closed daily bar for each decision time T: date(T) - 1 day."""
    T = pd.to_datetime(T, utc=True)
    return (T.floor("D") - pd.Timedelta(days=1))


def raw_amihud_matrix(T: pd.DatetimeIndex, W: int, minp: int,
                      cols: list[str] | None = None) -> np.ndarray:
    """Trailing-W Amihud value at D*(T) per symbol. Shape (len(T), len(cols))."""
    cols = cols or SYMS
    key = ("ami", W, minp, tuple(cols), len(T),
           str(pd.to_datetime(T, utc=True)[0]) if len(T) else "",
           str(pd.to_datetime(T, utc=True)[-1]) if len(T) else "")
    if key in _raw_cache:
        return _raw_cache[key]
    Dl = d_last(T)
    Dl_ns = Dl.values.astype("datetime64[ns]").astype(np.int64)
    mat = np.full((len(T), len(cols)), np.nan)
    for j, s in enumerate(cols):
        d = load_daily(s)
        aw = amihud_window(d, W, minp)
        idx_ns = d.index.values.astype("datetime64[ns]").astype(np.int64)
        pos = np.searchsorted(idx_ns, Dl_ns, side="left")
        vals = aw.to_numpy(float)
        ii = np.asarray(pos)
        ok = (ii >= 0) & (ii < len(d))
        match = np.zeros(len(T), dtype=bool)
        match[ok] = (idx_ns[ii[ok]] == Dl_ns[ok])
        mat[match, j] = vals[ii[match]]
    _raw_cache[key] = mat
    return mat


def xs_z(mat: np.ndarray) -> np.ndarray:
    """Cross-sectional z across columns at each row (same-T only). NaN->NaN."""
    mat = np.asarray(mat, float)
    out = np.full_like(mat, np.nan)
    mu = np.nanmean(mat, axis=1)
    sd = np.nanstd(mat, axis=1, ddof=1)
    finite = np.isfinite(mat)
    nfin = finite.sum(axis=1)
    for i in range(mat.shape[0]):
        if nfin[i] < 2 or not np.isfinite(sd[i]) or sd[i] == 0:
            row = mat[i]
            out[i, finite[i]] = 0.0
        else:
            out[i] = (mat[i] - mu[i]) / sd[i]
    out[~finite] = np.nan
    return out


def clip_mult(m: np.ndarray) -> np.ndarray:
    """Clip to [0.5,1.5]; NaN -> 1.0."""
    m = np.asarray(m, float)
    out = np.ones_like(m)
    ok = np.isfinite(m)
    out[ok] = np.minimum(HI, np.maximum(LO, m[ok]))
    return out


def a1_mult(T: pd.DatetimeIndex, K: float = K_BASE,
            W: int = W_BASE, minp: int = MIN_BASE,
            cols: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Frozen-A1-style multiplier frame (both legs) for given K/W.

    Returns (frame DataFrame on T x cols, info dict with z/raw/coverage).
    """
    cols = list(cols) if cols is not None else list(SYMS)
    T = pd.to_datetime(T, utc=True)
    ami = raw_amihud_matrix(T, W, minp, cols)
    z = xs_z(ami)
    m = clip_mult(1.0 + K * np.where(np.isfinite(z), z, np.nan))
    frame = pd.DataFrame(m, index=T, columns=cols)
    info = dict(z=z, ami=ami,
                cov=float(np.isfinite(ami).all(axis=1).mean()) if len(T) else 0.0)
    return frame, info
