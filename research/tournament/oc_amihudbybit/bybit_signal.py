"""oc_amihudbybit signal: venue-consistent Amihud tilt (Bybit volumes, AB1).

PLAN-fixed, causal. AB1 mirrors A1 (oc_lit_xs) exactly except the Amihud input:
  Bybit daily from data/raw/bybit_linear_1m_20261004/<SYM>_1m.parquet
  (USES THE TURNOVER COLUMN, USDT; present for all 5 symbols).

Bybit daily per coin D (UTC midnight):
  day D = minutes with 00:00(D) <= open_time < 00:00(D+1).
  close_d = close of the last minute bar of day D (NaN if empty).
  turnover_d = sum(turnover) over day D (NaN if empty/non-positive).
  r_d = close_d / close_{d-1} - 1 (NaN if either missing/non-finite).
  amihud_d = |r_d| / turnover_d (NaN if r non-finite or turnover
    missing/non-positive/non-finite).
  Amihud30(D) = mean(amihud over D-29..D), min 20 else NaN.
Full consecutive daily index per coin (gaps stay NaN, no ffill).

Decision time T: D*(T) = date(T) - 1 day (day D usable iff D+1 00:00 <= T).
XS z at same T only: z = (x-mean)/std(ddof=1) across finite syms;
<2 finite or std==0/non-finite -> 0 for finite raws; NaN raw -> NaN.
AB1 multiplier (both legs): clip(1 + 0.25*z, [0.5,1.5]), NaN -> 1.0.

Also ships a bit-exact Binance A1 path (same code as oc_lit_xs/xs_signal.py)
for the A1 reproduction rows.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BYBIT_DIR = ROOT / "data/raw/bybit_linear_1m_20261004"
XSDIR = ROOT / "data/raw/xs_universe_20260924"

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
AMI_WIN, AMI_MIN = 30, 20
K = 0.25
LO, HI = 0.5, 1.5
TURNOVER_COL = "turnover"  # PLAN-fixed: turnover column is used (present).

_daily_bybit_cache: dict[str, pd.DataFrame] = {}
_daily_bin_cache: dict[str, pd.DataFrame] = {}


def load_bybit_daily(sym: str) -> pd.DataFrame:
    """Bybit daily frame for one symbol, indexed by day midnight UTC.

    Columns: close, turnover, r, amihud_d, Amihud30.
    """
    if sym in _daily_bybit_cache:
        return _daily_bybit_cache[sym]
    f = BYBIT_DIR / f"{sym}_1m.parquet"
    df = pd.read_parquet(f, columns=["open_time", "close", "volume", "turnover"])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.sort_values("open_time")
    if TURNOVER_COL not in df.columns:
        raise KeyError(f"{TURNOVER_COL} missing in {f}")
    day = df["open_time"].dt.floor("D")
    g = df.groupby(day)
    close = g["close"].last()
    turnover = g[TURNOVER_COL].sum(min_count=1)
    close.index = pd.to_datetime(close.index, utc=True)
    turnover.index = pd.to_datetime(turnover.index, utc=True)
    full = pd.date_range(close.index.min(), close.index.max(), freq="D", tz="UTC")
    close = close.reindex(full)
    turnover = turnover.reindex(full)
    close = pd.to_numeric(close, errors="coerce").astype(float)
    turnover = pd.to_numeric(turnover, errors="coerce").astype(float)
    turnover[~(turnover > 0)] = np.nan
    r = close / close.shift(1) - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        amihud_d = r.abs() / turnover
    amihud_d[(~np.isfinite(r))] = np.nan
    amihud_d[~np.isfinite(turnover)] = np.nan
    out = pd.DataFrame({"close": close, "turnover": turnover, "r": r,
                        "amihud_d": amihud_d})
    out["Amihud30"] = out["amihud_d"].rolling(AMI_WIN, min_periods=AMI_MIN).mean()
    _daily_bybit_cache[sym] = out
    return out


def load_binance_daily(sym: str) -> pd.DataFrame:
    """Binance daily frame (bit-exact oc_lit_xs logic), indexed by day midnight UTC."""
    if sym in _daily_bin_cache:
        return _daily_bin_cache[sym]
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
    out["Amihud30"] = out["amihud_d"].rolling(AMI_WIN, min_periods=AMI_MIN).mean()
    _daily_bin_cache[sym] = out
    return out


def d_last(T: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last fully-closed daily bar for each decision time T: date(T) - 1 day."""
    T = pd.to_datetime(T, utc=True)
    return (T.floor("D") - pd.Timedelta(days=1))


def _raw_matrix(T: pd.DatetimeIndex, col: str, loader,
                cols: list[str] | None = None) -> np.ndarray:
    """Trailing Amihud30 value at D*(T) per symbol. Shape (len(T), len(cols))."""
    cols = cols or SYMS
    Dl = d_last(T)
    Dl_ns = Dl.values.astype("datetime64[ns]").astype(np.int64)
    mat = np.full((len(T), len(cols)), np.nan)
    for j, s in enumerate(cols):
        d = loader(s)
        idx = d.index
        idx_ns = idx.values.astype("datetime64[ns]").astype(np.int64)
        pos = np.searchsorted(idx_ns, Dl_ns, side="left")
        vals = d[col].to_numpy(float)
        ii = np.asarray(pos)
        ok = (ii >= 0) & (ii < len(idx))
        match = np.zeros(len(T), dtype=bool)
        match[ok] = (idx_ns[ii[ok]] == Dl_ns[ok])
        mat[match, j] = vals[ii[match]]
    return mat


def raw_bybit_matrix(T: pd.DatetimeIndex,
                     cols: list[str] | None = None) -> np.ndarray:
    return _raw_matrix(T, "Amihud30", load_bybit_daily, cols)


def raw_binance_matrix(T: pd.DatetimeIndex,
                       cols: list[str] | None = None) -> np.ndarray:
    return _raw_matrix(T, "Amihud30", load_binance_daily, cols)


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


def ab1_mult(T: pd.DatetimeIndex,
             cols: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """AB1 (Bybit Amihud) multiplier frame, both legs, on T x cols."""
    cols = list(cols) if cols is not None else list(SYMS)
    T = pd.to_datetime(T, utc=True)
    ami = raw_bybit_matrix(T, cols)
    z = xs_z(ami)
    m = clip_mult(1.0 + K * np.where(np.isfinite(z), z, np.nan))
    frame = pd.DataFrame(m, index=T, columns=cols)
    info = dict(z=z, ami=ami,
                cov=float(np.isfinite(ami).all(axis=1).mean()) if len(T) else 0.0)
    return frame, info


def a1_mult(T: pd.DatetimeIndex,
            cols: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """A1 (Binance Amihud) multiplier frame, both legs, on T x cols."""
    cols = list(cols) if cols is not None else list(SYMS)
    T = pd.to_datetime(T, utc=True)
    ami = raw_binance_matrix(T, cols)
    z = xs_z(ami)
    m = clip_mult(1.0 + K * np.where(np.isfinite(z), z, np.nan))
    frame = pd.DataFrame(m, index=T, columns=cols)
    info = dict(z=z, ami=ami,
                cov=float(np.isfinite(ami).all(axis=1).mean()) if len(T) else 0.0)
    return frame, info
