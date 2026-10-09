"""oc_lit_xs signal: Amihud (H4) + MAX (H5) cross-sectional book tilts.

PLAN-fixed definitions (no fits, causal):
  Daily per coin D (UTC midnight): r_d = close_d/close_{d-1} - 1.
  amihud_d = |r_d| / quote_volume_d (NaN if quote missing/non-positive).
  Amihud30(D) = mean(amihud over D-29..D), min 20 else NaN.
  Size30(D)   = mean(quote_volume over D-29..D), min 20 else NaN (A3 only).
  MAX21(D)    = max(r over D-20..D), min 15 else NaN.
  Source: data/raw/xs_universe_20260924/<SYM>_1d.parquet (full span, see PLAN).

  Decision time T (4h bar timestamp): D*(T) = date(T) - 1 day
  (day D usable iff D+1 00:00 <= T). Raws at T use only days <= D*(T).
  XS z at same T only: z = (x-mean)/std(ddof=1) across finite syms;
  <2 finite or std==0/non-finite -> 0 for finite raws; NaN raw -> NaN.
  A3: rank Size30 ascending; terciles [0,1]->g0, [2,3]->g1, [4]->g2;
  z within group (>=2 finite else 0).

  Multipliers (clip [0.5,1.5], NaN->1):
  A1 both-legs: 1+0.25*z_illiq | A2 longs-only: 1+0.25*max(z_illiq,0) on longs
  A3 both-legs: 1+0.25*z_illiq_terc | X1 both: 1+0.25*z_max
  X2 longs-only: 1+0.25*z_max on longs | X3 both (falsification): 1-0.25*z_max
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
XSDIR = ROOT / "data/raw/xs_universe_20260924"

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
AMI_WIN, AMI_MIN = 30, 20
SIZE_WIN, SIZE_MIN = 30, 20
MAX_WIN, MAX_MIN = 21, 15
K = 0.25
LO, HI = 0.5, 1.5

_VARIANTS = ("A1", "A2", "A3", "X1", "X2", "X3")

_daily_cache: dict[str, pd.DataFrame] = {}


def load_daily(sym: str) -> pd.DataFrame:
    """Daily raw frame for one symbol, indexed by day midnight UTC.

    Columns: close, quote_volume, r, amihud_d, Amihud30, Size30, MAX21.
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
    out["Amihud30"] = out["amihud_d"].rolling(AMI_WIN, min_periods=AMI_MIN).mean()
    out["Size30"] = out["quote_volume"].rolling(SIZE_WIN, min_periods=SIZE_MIN).mean()
    out["MAX21"] = out["r"].rolling(MAX_WIN, min_periods=MAX_MIN).max()
    _daily_cache[sym] = out
    return out


def d_last(T: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last fully-closed daily bar for each decision time T: date(T) - 1 day."""
    T = pd.to_datetime(T, utc=True)
    return (T.floor("D") - pd.Timedelta(days=1))


def _raw_matrix(T: pd.DatetimeIndex, col: str,
                cols: list[str] | None = None) -> np.ndarray:
    """Raw trailing value at D*(T) per symbol. Shape (len(T), len(cols))."""
    cols = cols or SYMS
    Dl = d_last(T)
    Dl_ns = Dl.values.astype("datetime64[ns]").astype(np.int64)
    mat = np.full((len(T), len(cols)), np.nan)
    for j, s in enumerate(cols):
        d = load_daily(s)
        idx = d.index
        idx_ns = idx.values.astype("datetime64[ns]").astype(np.int64)
        pos = np.searchsorted(idx_ns, Dl_ns, side="left")
        # searchsorted gives insertion point; we need exact match (days are midnight).
        # pos p means idx[p] >= D; exact iff idx[p] == D.
        vals = d[col].to_numpy(float)
        ii = np.asarray(pos)
        ok = (ii >= 0) & (ii < len(idx))
        # verify exact day match
        match = np.zeros(len(T), dtype=bool)
        match[ok] = (idx_ns[ii[ok]] == Dl_ns[ok])
        # For T before the first daily bar, pos=0 but no match -> stays NaN.
        mat[match, j] = vals[ii[match]]
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
    # NaN raws stay NaN
    out[~finite] = np.nan
    return out


def xs_z_tercile(ami: np.ndarray, size: np.ndarray) -> np.ndarray:
    """Size-tercile-neutralised Amihud z. Rank Size30 ascending per row.

    Terciles by rank for 5 coins: ranks [0,1]->g0, [2,3]->g1, [4]->g2.
    NaN size ranks last. NaN ami -> NaN z.
    """
    ami = np.asarray(ami, float)
    size = np.asarray(size, float)
    n, m = ami.shape
    out = np.full_like(ami, np.nan)
    for i in range(n):
        a, s = ami[i], size[i]
        order = np.argsort(np.where(np.isfinite(s), s, np.inf), kind="stable")
        groups = np.empty(m, dtype=int)
        groups[order[0:2]] = 0
        groups[order[2:4]] = 1
        groups[order[4:5]] = 2
        for g in (0, 1, 2):
            cols = np.where(groups == g)[0]
            vals = a[cols]
            fin = np.isfinite(vals)
            if fin.sum() < 2:
                out[i, cols[fin]] = 0.0
                continue
            sd = float(np.nanstd(vals, ddof=1))
            if not np.isfinite(sd) or sd == 0:
                out[i, cols[fin]] = 0.0
            else:
                mu = float(np.nanmean(vals))
                z = (vals - mu) / sd
                out[i, cols] = z
        out[i, ~np.isfinite(a)] = np.nan
    return out


def clip_mult(m: np.ndarray) -> np.ndarray:
    """Clip to [0.5,1.5]; NaN -> 1.0."""
    m = np.asarray(m, float)
    out = np.ones_like(m)
    ok = np.isfinite(m)
    out[ok] = np.minimum(HI, np.maximum(LO, m[ok]))
    return out


def variant_mult_frame(z_illiq: np.ndarray, z_terc: np.ndarray,
                       z_max: np.ndarray, variant: str) -> np.ndarray:
    """Per-cell multiplier matrix (NaN-safe, clipped) for one variant."""
    if variant == "A1":
        return clip_mult(1.0 + K * np.where(np.isfinite(z_illiq), z_illiq, np.nan))
    if variant == "A2":
        return clip_mult(1.0 + K * np.where(np.isfinite(z_illiq),
                                           np.maximum(z_illiq, 0.0), np.nan))
    if variant == "A3":
        return clip_mult(1.0 + K * np.where(np.isfinite(z_terc), z_terc, np.nan))
    if variant == "X1":
        return clip_mult(1.0 + K * np.where(np.isfinite(z_max), z_max, np.nan))
    if variant == "X2":
        return clip_mult(1.0 + K * np.where(np.isfinite(z_max), z_max, np.nan))
    if variant == "X3":
        return clip_mult(1.0 - K * np.where(np.isfinite(z_max), z_max, np.nan))
    raise ValueError(variant)


def tilt_frames(T: pd.DatetimeIndex,
                cols: list[str] | None = None) -> tuple[dict[str, pd.DataFrame], dict]:
    """Multiplier frames per variant on decision-time index T (columns=cols).

    Returns (frames, info) with frames[variant] a DataFrame of per-cell
    multipliers (NaN-free: unknown -> 1.0, clipped). info holds z matrices
    and coverage counts for REPORT.
    """
    cols = list(cols) if cols is not None else list(SYMS)
    T = pd.to_datetime(T, utc=True)
    ami = _raw_matrix(T, "Amihud30", cols)
    siz = _raw_matrix(T, "Size30", cols)
    mx = _raw_matrix(T, "MAX21", cols)
    z_illiq = xs_z(ami)
    z_terc = xs_z_tercile(ami, siz)
    z_max = xs_z(mx)
    frames: dict[str, pd.DataFrame] = {}
    for v in _VARIANTS:
        frames[v] = pd.DataFrame(variant_mult_frame(z_illiq, z_terc, z_max, v),
                                 index=T, columns=cols)
    info = dict(z_illiq=z_illiq, z_terc=z_terc, z_max=z_max,
                ami=ami, size=siz, mx=mx,
                cov_ami=float(np.isfinite(ami).all(axis=1).mean()) if len(T) else 0.0,
                cov_max=float(np.isfinite(mx).all(axis=1).mean()) if len(T) else 0.0)
    return frames, info
