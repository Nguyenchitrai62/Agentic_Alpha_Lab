"""oc_lit_position signals: H6 OI 7d-change z + H8 BTC MVRV-z (PLAN-fixed).

H6 (per coin c, per decision time T):
  OI_now  = last sum_open_interest with create_time <= T - 5min
  OI_7d   = last sum_open_interest with create_time <= T - 7d - 5min
  d7 = ln(OI_now / OI_7d), NaN if missing/non-positive
  z  = (d7 - mean(W)) / std(W, ddof=1), W = trailing up-to-2190 prior d7
       strictly before T, min 540 finite else NaN; std==0 -> NaN.
  O1 mult: 0.5 where z > 2.0 else 1 (NaN -> 1)
  O2 mult: 0.5 where z > 1.5 else 1 (NaN -> 1)

H8 (BTC cycle, shared across majors):
  MVRV(D) = CapMVRVCur(D) (daily UTC; values ~0.75..3.96 are the ratio itself)
  zM(D) = (MVRV - mean(W)) / std(W, ddof=1), W = trailing <=365 daily values
          ending at D inclusive, min 180 else NaN; std==0 -> NaN.
  Day D usable from D+1 02:00 UTC; z(T) = zM(D*(T)), D*(T) = max{D: avail <= T}.
  M1 mult: 0.5 where z > 2.0 else 1 (NaN -> 1)
  M2 mult: 0.5 where z > 2.0, 1.1 where z < 0.0, else 1 (NaN -> 1)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

OI_DIR = ROOT / "data/raw/um_metrics_20260926"
OI_COL = "sum_open_interest"
OI_LAG = pd.Timedelta(minutes=5)
OI_LOOKBACK = pd.Timedelta(days=7)
H6_TRAIL = 2190  # 365d of 4h bars
H6_MINP = 540
O1_THRESH = 2.0
O2_THRESH = 1.5
BOOK_MULT = 0.5

BTC_CSV = ROOT / "data/raw/onchain_20260924/btc.csv"
H8_WIN = 365
H8_MINP = 180
H8_AVAIL = pd.Timedelta(hours=26)  # D 00:00 + 26h = D+1 02:00 UTC
M1_THRESH = 2.0
M2_LO_THRESH = 0.0
M2_GREED_MULT = 1.1

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")


def load_oi(sym: str):
    m = pd.read_parquet(OI_DIR / f"{sym}_metrics.parquet",
                        columns=["create_time", OI_COL])
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.drop_duplicates("create_time").sort_values("create_time")
    t = m["create_time"].values.astype("datetime64[ns]").astype(np.int64)
    v = m[OI_COL].to_numpy(dtype=float)
    return t, v


def h6_d7_z(bar_ns: np.ndarray, oi_t: np.ndarray, oi_v: np.ndarray):
    """Causal (d7, z) for one coin on a 4h grid. bar_ns int64 ns ascending."""
    n = len(bar_ns)
    d7 = np.full(n, np.nan)
    if n == 0:
        return d7, np.full(n, np.nan)
    lag = OI_LAG.value
    lb = OI_LOOKBACK.value
    q_now = bar_ns - lag
    q_7 = bar_ns - lb - lag
    i_now = np.searchsorted(oi_t, q_now, side="right") - 1
    i_7 = np.searchsorted(oi_t, q_7, side="right") - 1
    ok = (i_now >= 0) & (i_7 >= 0)
    o_now = np.full(n, np.nan)
    o_7 = np.full(n, np.nan)
    o_now[ok] = oi_v[i_now[ok]]
    o_7[ok] = oi_v[i_7[ok]]
    good = ok & np.isfinite(o_now) & np.isfinite(o_7) & (o_now > 0) & (o_7 > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        d7[good] = np.log(o_now[good] / o_7[good])
    s = pd.Series(d7)
    mu = s.shift(1).rolling(H6_TRAIL, min_periods=H6_MINP).mean().to_numpy()
    sd = s.shift(1).rolling(H6_TRAIL, min_periods=H6_MINP).std(ddof=1).to_numpy()
    z = np.full(n, np.nan)
    okstat = np.isfinite(mu) & np.isfinite(sd) & (sd > 0) & np.isfinite(d7)
    z[okstat] = (d7[okstat] - mu[okstat]) / sd[okstat]
    return d7, z


def h6_mults(z: np.ndarray, thresh: float, mult: float = BOOK_MULT):
    z = np.asarray(z, float)
    m = np.ones_like(z)
    m[np.isfinite(z) & (z > thresh)] = mult
    return m


def load_mvrv_daily() -> pd.DataFrame:
    """Daily MVRV frame: index day UTC midnight, columns mvrv/z/avail."""
    df = pd.read_csv(BTC_CSV, parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates("time").sort_values("time")
    day = df["time"].dt.floor("D")
    df = df.assign(day=day).drop_duplicates("day").sort_values("day")
    full = pd.date_range(df["day"].min(), df["day"].max(), freq="D", tz="UTC")
    df = df.set_index("day").reindex(full)
    mvrv = df["CapMVRVCur"].to_numpy(dtype=float)
    out = pd.DataFrame({"mvrv": mvrv}, index=full)
    r = out["mvrv"].rolling(H8_WIN, min_periods=H8_MINP)
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
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(avail_ns, Tns, side="right") - 1
    out = np.full(len(T), np.nan)
    ok = (ii >= 0) & (ii < len(vals))
    out[ok] = vals[ii[ok]]
    return out


def h8_mults(z: np.ndarray, mode: str):
    z = np.asarray(z, float)
    m = np.ones_like(z)
    if mode == "M1":
        m[np.isfinite(z) & (z > M1_THRESH)] = BOOK_MULT
    elif mode == "M2":
        m[np.isfinite(z) & (z > M1_THRESH)] = BOOK_MULT
        lo = np.isfinite(z) & (z < M2_LO_THRESH) & ~(z > M1_THRESH)
        m[lo] = M2_GREED_MULT
    else:
        raise ValueError(mode)
    return m
