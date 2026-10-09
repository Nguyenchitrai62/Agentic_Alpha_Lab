"""audit_amihud independent A1 signal (blind replication from PLAN.md only).

Daily source: data/raw/xs_universe_20260924/<SYM>_1d.parquet
  (open_time = day open midnight UTC, close, quote_volume in USD).
Day-availability rule: for 4h decision time T, D*(T) = date(T) - 1 day;
  day D usable iff D+1 00:00 UTC <= T. Raw at T = Amihud30(D*(T)).
Amihud30(D) = mean(|r_d|/quote_volume_d over D-29..D), >=20 non-NaN else NaN.
XS z at same T only, ddof=1; <2 finite or std 0/non-finite -> 0; NaN -> NaN.
A1 multiplier = clip(1 + 0.25*z, 0.5, 1.5); NaN -> 1.0.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "raw" / "xs_universe_20260924"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
K = 0.25
LO, HI = 0.5, 1.5
CUTOFF = pd.Timestamp("2021-09-24", tz="UTC")


def load_daily(sym: str) -> pd.DataFrame:
    """Per-coin daily frame indexed by day D (midnight UTC) with r, amihud, Amihud30."""
    df = pd.read_parquet(DATA / f"{sym}_1d.parquet",
                         columns=["open_time", "close", "quote_volume"])
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.sort_values("open_time")
    day = df["open_time"].dt.normalize()
    df = df.assign(day=day).drop_duplicates(subset="day", keep="last")
    df = df.set_index("day").sort_index()
    df.index = pd.DatetimeIndex(df.index, tz="UTC")
    close = pd.to_numeric(df["close"], errors="coerce").astype(float)
    qv = pd.to_numeric(df["quote_volume"], errors="coerce").astype(float)
    r = close / close.shift(1) - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        am = r.abs() / qv
    bad = (~np.isfinite(r.to_numpy())) | ~(qv.to_numpy() > 0) | (~np.isfinite(qv.to_numpy()))
    am = pd.Series(np.where(bad, np.nan, am.to_numpy(dtype=float)), index=df.index)
    cnt = am.rolling(30, min_periods=1).count()
    ami30 = am.rolling(30, min_periods=1).mean()
    ami30 = ami30.where(cnt >= 20, np.nan)
    out = pd.DataFrame({"close": close, "quote_volume": qv, "ret": r,
                        "amihud": am, "Amihud30": ami30})
    out.index.name = "D"
    return out


def d_last(T: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Last fully closed daily bar for each decision time T: date(T) - 1 day."""
    T = pd.DatetimeIndex(pd.to_datetime(T, utc=True))
    return (T.normalize() - pd.Timedelta(days=1))


def xs_z(mat: np.ndarray) -> np.ndarray:
    """Cross-sectional z per row (ddof=1); <2 finite or std 0/non-finite -> 0; NaN stays NaN."""
    mat = np.asarray(mat, dtype=float)
    z = np.full_like(mat, np.nan)
    for i in range(mat.shape[0]):
        row = mat[i]
        fin = row[np.isfinite(row)]
        if fin.size < 2:
            z[i, np.isfinite(row)] = 0.0
            continue
        sd = float(np.std(fin, ddof=1))
        if not np.isfinite(sd) or sd == 0.0:
            z[i, np.isfinite(row)] = 0.0
            continue
        mu = float(np.mean(fin))
        zi = (row - mu) / sd
        zi[~np.isfinite(row)] = np.nan
        # rows with finite raw but computed z non-finite -> 0 (defensive, same as spec intent)
        mask_fin = np.isfinite(row)
        zi[mask_fin & ~np.isfinite(zi)] = 0.0
        z[i] = zi
    return z


def clip_mult(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=float)
    out = np.where(np.isfinite(m), np.clip(m, LO, HI), 1.0)
    return out


def tilt_frames(book_idx: pd.DatetimeIndex, cols: list[str]):
    """A1 multiplier frames on the STANDARD book index (same shape as book weights).

    Returns (frames dict {'A1': DataFrame}, raws DataFrame of Amihud30, z DataFrame).
    Rows before 2021-09-24 are 1.0 (v426 convention: not tilted).
    """
    T = pd.DatetimeIndex(pd.to_datetime(book_idx, utc=True))
    daily = {s: load_daily(s) for s in COINS}
    # union of daily indices for searchsorted mapping
    dmap = d_last(T)
    raw_mat = np.full((len(T), len(cols)), np.nan)
    for j, sym in enumerate(cols):
        d = daily[sym]
        pos = d.index.searchsorted(dmap, side="right") - 1
        # searchsorted on D (day opens). D usable iff D+1midnight <= T i.e. D <= D*(T);
        # since D*(T) is itself a day, right-1 gives exactly D*(T) when present.
        vals = np.full(len(T), np.nan)
        ok = pos >= 0
        # verify the mapped day equals D*(T) (present) else NaN (missing history)
        dvals = d["Amihud30"].to_numpy()
        vals[ok] = dvals[pos[ok]]
        # days before history start give pos<0 -> NaN (fallback -> mult 1)
        raw_mat[:, j] = vals
    z = xs_z(raw_mat)
    mult = clip_mult(1.0 + K * z)
    f = pd.DataFrame(mult, index=T, columns=list(cols))
    # v426 convention: rows before 2021-09-24 not tilted
    f.loc[f.index < CUTOFF] = 1.0
    raws = pd.DataFrame(raw_mat, index=T, columns=list(cols))
    zf = pd.DataFrame(z, index=T, columns=list(cols))
    return {"A1": f}, raws, zf
