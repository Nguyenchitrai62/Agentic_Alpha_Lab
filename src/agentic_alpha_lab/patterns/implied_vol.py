"""W8 options implied volatility (Deribit DVOL) for BTC (vf round).

Fixed definitions (do not change after seeing results; log any change below):

Data: Deribit public DVOL hourly candles 2021-03-24..2026-09-24
(``data/raw/dvol_20260924/dvol_hourly.parquet`` + ``manifest.json``; Deribit
public API, no auth, resolution=3600, <=1000 rows per call, 0.2s sleep).
A DVOL hourly candle with timestamp ts is available at ts + 1 hour; every
value is aligned strictly as-of each BTC bar close (merge_asof backward on
availability time).

Hourly-domain indicators (all causal, trailing on hourly DVOL closes):
- dvol_level: as-of DVOL close (vol points, e.g. 60 = 60% ann.).
- dvol_chg_1d = log(dvol / dvol 24h ago); dvol_chg_7d = log(dvol / dvol 168h
  ago); NaN when either side is unavailable/non-positive.
- dvol_z_90d: z of DVOL level vs trailing 90d of hourly closes
  (window = 2160 prints, min_periods = full window, ddof=0, std==0 -> NaN),
  computed in hourly time then as-of joined.
- dvol_rv_30d: 30d realized vol, annualized, same units as DVOL: population
  std (ddof=0) of trailing 720 BTC hourly log returns (Binance 1h closes,
  full history incl. opened year) * sqrt(365*24) * 100, min_periods = 720,
  computed in hourly time then as-of joined.
- dvol_spread = dvol_level - dvol_rv_30d (vol points).
- dvol_ratio = dvol_level / dvol_rv_30d (NaN when RV missing/non-positive).
- DVOL term proxy: none (single DVOL index only).

Thresholds fixed a priori from level distributions only (no forward returns):
- SPIKE_Z = 2.0 (per spec).
- SPREAD_HI = +25.0 vol points (~p94 of spread), SPREAD_LO = -10.0 (~p4.5).
- CRUSH_DROP = -0.08 (1d log change < -8%) with trailing-7d max z > 2.0.

Events (int8 {-1,0,1}, causal, edge-triggered on as-of series):
- dvol_ev_spike_revert: +1 when z crosses up through +2.0 (contrarian).
- dvol_ev_spike_panic: -1 on the same crossing (panic continuation).
- dvol_ev_ivrv: +1 when spread crosses up through +25.0;
  -1 when spread crosses down through -10.0.
- dvol_ev_crush: +1 on the rising edge of (chg_1d < -0.08 while max z over
  the prior 7d of hourly prints, excluding the current print, > 2.0).

Row t uses only information available at bars.close_time[t]; rows <= cut are
identical under truncation (external hourly history is loaded whole and
joined as-of, so truncation only drops rows).

Post-hoc change log: none.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common

PREFIX = "dvol_"
DVOL_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "dvol_20260924"

Z_WINDOW = 2160  # 90d of hourly prints
CHG_1D = 24  # hourly prints
CHG_7D = 168  # hourly prints
RV_WINDOW = 720  # 30d of BTC hourly returns
HOURS_PER_YEAR = 365 * 24
SPIKE_Z = 2.0
SPREAD_HI = 25.0
SPREAD_LO = -10.0
CRUSH_DROP = -0.08
CRUSH_LOOKBACK = 168  # 7d of hourly prints

_DVOL_CACHE: dict | None = None
_RV_CACHE: dict | None = None


def _i64(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).values.astype("datetime64[ns]").astype("int64")


def _load_dvol() -> dict:
    """Hourly DVOL closes + causal hourly indicators; availability = ts + 1h."""
    global _DVOL_CACHE
    if _DVOL_CACHE is None:
        d = pd.read_parquet(DVOL_DIR / "dvol_hourly.parquet")
        d = d.sort_values("ts").reset_index(drop=True)
        ts = pd.to_datetime(d["ts_utc"], utc=True)
        avail = ts + pd.Timedelta(hours=1)
        close = d["dvol_close"].astype(float).to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            chg_1d = np.log(close / np.concatenate([np.full(CHG_1D, np.nan), close[:-CHG_1D]]))
            chg_7d = np.log(close / np.concatenate([np.full(CHG_7D, np.nan), close[:-CHG_7D]]))
        bad = ~(np.isfinite(close)) | (close <= 0)
        chg_1d[bad] = np.nan
        s = pd.Series(close)
        mu = s.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean().to_numpy(float)
        sd = s.rolling(Z_WINDOW, min_periods=Z_WINDOW).std(ddof=0).to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (close - mu) / sd
        z[~(np.isfinite(z))] = np.nan
        z[bad] = np.nan
        _DVOL_CACHE = {
            "avail": avail.values.astype("datetime64[ns]").astype("int64"),
            "close": close,
            "chg_1d": chg_1d,
            "chg_7d": chg_7d,
            "z": z,
        }
    return _DVOL_CACHE


def _load_rv() -> dict:
    """30d annualized realized vol from BTC 1h closes (full history)."""
    global _RV_CACHE
    if _RV_CACHE is None:
        bars = common.load_bars("1h", include_opened_year=True)
        bars = bars.sort_values("close_time").reset_index(drop=True)
        ct = pd.to_datetime(bars["close_time"], utc=True)
        c = bars["close"].astype(float).to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.log(c / np.concatenate([[np.nan], c[:-1]]))
        rv = (
            pd.Series(r)
            .rolling(RV_WINDOW, min_periods=RV_WINDOW)
            .std(ddof=0)
            .to_numpy(float)
            * np.sqrt(HOURS_PER_YEAR)
            * 100.0
        )
        rv[~(np.isfinite(rv))] = np.nan
        _RV_CACHE = {"t": ct.values.astype("datetime64[ns]").astype("int64"), "rv": rv}
    return _RV_CACHE


def _asof(vals: np.ndarray, t_src: np.ndarray, t_bar: np.ndarray) -> np.ndarray:
    pos = np.searchsorted(t_src, t_bar, side="right") - 1
    out = np.full(len(t_bar), np.nan)
    ok = pos >= 0
    out[ok] = vals[pos[ok]]
    return out


def _feature_cols() -> list[str]:
    return [
        "dvol_level",
        "dvol_chg_1d",
        "dvol_chg_7d",
        "dvol_z_90d",
        "dvol_rv_30d",
        "dvol_spread",
        "dvol_ratio",
    ]


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    close_col = "close_time" if "close_time" in bars else "open_time"
    t_bar = _i64(bars[close_col])
    D = _load_dvol()
    R = _load_rv()
    level = _asof(D["close"], D["avail"], t_bar)
    chg_1d = _asof(D["chg_1d"], D["avail"], t_bar)
    chg_7d = _asof(D["chg_7d"], D["avail"], t_bar)
    z = _asof(D["z"], D["avail"], t_bar)
    rv = _asof(R["rv"], R["t"], t_bar)
    with np.errstate(invalid="ignore"):
        spread = level - rv
        ratio = level / rv
    ratio[~(np.isfinite(ratio))] = np.nan
    df = pd.DataFrame(
        {
            "dvol_level": level,
            "dvol_chg_1d": chg_1d,
            "dvol_chg_7d": chg_7d,
            "dvol_z_90d": z,
            "dvol_rv_30d": rv,
            "dvol_spread": spread,
            "dvol_ratio": ratio,
        },
        index=idx,
    )
    return df.astype(float)


def _cross_up(x: pd.Series, thr: float) -> np.ndarray:
    xv = x.to_numpy(float)
    prev = np.concatenate([[np.nan], xv[:-1]])
    return (
        np.isfinite(xv)
        & np.isfinite(prev)
        & (xv > thr)
        & (prev <= thr)
    )


def _cross_down(x: pd.Series, thr: float) -> np.ndarray:
    xv = x.to_numpy(float)
    prev = np.concatenate([[np.nan], xv[:-1]])
    return (
        np.isfinite(xv)
        & np.isfinite(prev)
        & (xv < thr)
        & (prev >= thr)
    )


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    f = compute(bars)
    close_col = "close_time" if "close_time" in bars else "open_time"
    t_bar = _i64(bars[close_col])
    D = _load_dvol()

    z = f["dvol_z_90d"]
    spike = _cross_up(z, SPIKE_Z)
    ev_revert = pd.Series(np.where(spike, 1, 0), index=idx).astype("int8")
    ev_panic = pd.Series(np.where(spike, -1, 0), index=idx).astype("int8")

    sp = f["dvol_spread"]
    hi = _cross_up(sp, SPREAD_HI)
    lo = _cross_down(sp, SPREAD_LO)
    sig = np.zeros(len(bars), dtype=np.int8)
    sig[hi] = 1
    sig[lo] = -1
    ev_ivrv = pd.Series(sig, index=idx).astype("int8")

    # Crush after spike: prior-7d max z (hourly prints, excl. current) > 2
    # as-of each bar, plus as-of 1d change < -0.08; rising edge only.
    z_hourly = pd.Series(D["z"]).rolling(CRUSH_LOOKBACK, min_periods=1).max().shift(1)
    prior_max = _asof(z_hourly.to_numpy(float), D["avail"], t_bar)
    crush_level = (
        np.isfinite(f["dvol_chg_1d"].to_numpy(float))
        & (f["dvol_chg_1d"].to_numpy(float) < CRUSH_DROP)
        & np.isfinite(prior_max)
        & (prior_max > SPIKE_Z)
    )
    prev = np.concatenate([[False], crush_level[:-1]])
    crush = crush_level & ~prev
    ev_crush = pd.Series(np.where(crush, 1, 0), index=idx).astype("int8")

    out = pd.DataFrame(
        {
            "dvol_ev_spike_revert": ev_revert,
            "dvol_ev_spike_panic": ev_panic,
            "dvol_ev_ivrv": ev_ivrv,
            "dvol_ev_crush": ev_crush,
        },
        index=idx,
    )
    return out.astype("int8")
