"""W5 derivatives positioning: fixed causal definitions (do not change after results).

Data: base 5m metrics ``data/processed/btc_derivatives_metrics_20260905_v1/
metrics.parquet`` (2022-01-01..2026-03-22) plus extension
``data/raw/metrics_ext_20260924/metrics_ext.parquet`` (2026-03-23..2026-09-23)
from the public Binance archive; funding via ``common.load_funding(
include_opened_year=True)``. Full external history may be loaded, but every
value is aligned strictly as-of each bar close (merge_asof backward on
availability time):

- each metrics row is treated as available 5 minutes after ``create_time``;
- each funding print is available at its ``fundingTime``.

Row ``t`` of ``compute``/``events`` therefore uses only information available
at ``bars.close_time[t]`` (all joins are backward, all windows trailing).

Fixed definitions (chosen before any event study):
- TF = median ``open_time`` step of the input bars (1h/4h/1d). A "k-bar
  equivalent" lookback is ``k * TF`` of wall-clock time on the 5m OI series:
  ``pos_oi_chg_{1,6,24,72} = log(OI(t) / OI(t - k*TF))`` with ``OI`` =
  ``sum_open_interest`` as-of. NaN when either side is unavailable /
  non-positive (incl. all bars before 2022-01-01).
- ``pos_oi_z_30d``: z of as-of OI level vs trailing 30d of as-of values
  (window = 30d/TF bars, min_periods = full window, ddof=0, std==0 -> NaN).
- ``pos_oi_price_div_24``: 24-bar price log return (bars closes, shift(24))
  minus ``pos_oi_chg_24`` (price outruns OI when positive).
- Levels (as-of) and 30d z-scores (same trailing-bar window as OI z) for
  ``count_toptrader_long_short_ratio`` (``pos_top_count_*``),
  ``sum_toptrader_long_short_ratio`` (``pos_top_sum_*``),
  ``count_long_short_ratio`` (``pos_ls_global_*``); level + z for
  ``sum_taker_long_short_vol_ratio`` (``pos_taker_*``). Raw levels are
  z-scored (no logs: ratios can be 0/missing). Sparse 2022 top-trader fields
  stay NaN (never filled).
- ``pos_funding_z``: funding-rate z computed in print time over the trailing
  90 prints (~30d at 8h cadence, min_periods=90, ddof=0), then as-of joined.
- ``pos_fund_x_oi = pos_funding_z * pos_oi_z_30d``.

Events (int8 {-1,0,1}, causal, built only from compute() + trailing prices):
- ``pos_ev_crowd``: -1 when funding z > 2 and global L/S z > 2 (crowded
  long, contrarian short); +1 on the mirror (both < -2).
- ``pos_ev_crowd_top``: same with top-trader (sum) L/S z.
- ``pos_ev_oi_cont``: +1 when OI 6-bar change > +0.02 and 6-bar price return
  > 0; -1 when OI 6-bar change > +0.02 and price return < 0 (continuation).
- ``pos_ev_oi_flush``: +1 when OI 6-bar change < -0.03 (capitulation washout).

Post-hoc change log: none.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common

PREFIX = "pos_"
BASE_METRICS = (
    Path(__file__).resolve().parents[3]
    / "data" / "processed" / "btc_derivatives_metrics_20260905_v1" / "metrics.parquet"
)
EXT_METRICS = (
    Path(__file__).resolve().parents[3]
    / "data" / "raw" / "metrics_ext_20260924" / "metrics_ext.parquet"
)
AVAIL_LAG = pd.Timedelta(minutes=5)
Z_WINDOW_DAYS = 30
FUND_Z_PRINTS = 90  # ~30d at 8h funding cadence
OI_CHG_KS = (1, 6, 24, 72)
PRICE_RET_KS = (6, 24)
CROWD_Z = 2.0
SURGE_OI = 0.02
FLUSH_OI = -0.03

_METRICS_CACHE: dict | None = None
_FUND_CACHE: dict | None = None


def _i64(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).values.astype("datetime64[ns]").astype("int64")


def _load_metrics() -> dict:
    global _METRICS_CACHE
    if _METRICS_CACHE is None:
        base = pd.read_parquet(BASE_METRICS)
        frames = [base]
        if EXT_METRICS.exists():
            ext = pd.read_parquet(EXT_METRICS)
            frames.append(ext)
        m = pd.concat(frames, ignore_index=True)
        m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
        m = m.sort_values("create_time").drop_duplicates("create_time").reset_index(drop=True)
        avail = m["create_time"] + AVAIL_LAG
        _METRICS_CACHE = {
            "avail": _i64(avail),
            "oi": m["sum_open_interest"].astype(float).to_numpy(),
            "top_count": m["count_toptrader_long_short_ratio"].astype(float).to_numpy(),
            "top_sum": m["sum_toptrader_long_short_ratio"].astype(float).to_numpy(),
            "ls_global": m["count_long_short_ratio"].astype(float).to_numpy(),
            "taker": m["sum_taker_long_short_vol_ratio"].astype(float).to_numpy(),
        }
    return _METRICS_CACHE


def _load_funding_z() -> dict:
    global _FUND_CACHE
    if _FUND_CACHE is None:
        f = common.load_funding(include_opened_year=True)
        f = f.sort_values("fundingTime").reset_index(drop=True)
        fr = f["fundingRate"].astype(float)
        mu = fr.rolling(FUND_Z_PRINTS, min_periods=FUND_Z_PRINTS).mean()
        sd = fr.rolling(FUND_Z_PRINTS, min_periods=FUND_Z_PRINTS).std(ddof=0)
        z = (fr - mu) / sd.replace(0, np.nan)
        _FUND_CACHE = {"t": _i64(f["fundingTime"]), "z": z.to_numpy(float)}
    return _FUND_CACHE


def _infer_tf_seconds(bars: pd.DataFrame) -> float:
    try:
        if len(bars) >= 3:
            med = pd.to_datetime(bars["open_time"], utc=True).diff().median()
            if pd.notna(med) and med.total_seconds() > 0:
                return float(med.total_seconds())
    except Exception:
        pass
    return 4 * 3600.0


def _asof(vals: np.ndarray, t_src: np.ndarray, t_bar: np.ndarray) -> np.ndarray:
    pos = np.searchsorted(t_src, t_bar, side="right") - 1
    out = np.full(len(t_bar), np.nan)
    ok = pos >= 0
    out[ok] = vals[pos[ok]]
    return out


def _z_trailing(x: np.ndarray, window: int) -> np.ndarray:
    s = pd.Series(x)
    mu = s.rolling(window, min_periods=window).mean().to_numpy(float)
    sd = s.rolling(window, min_periods=window).std(ddof=0).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (x - mu) / sd
    z[~(np.isfinite(z))] = np.nan
    z[np.isnan(x)] = np.nan
    return z


def _oi_chg(oi: np.ndarray, t_avail: np.ndarray, t_bar: np.ndarray, lag_ns: int) -> np.ndarray:
    now = _asof(oi, t_avail, t_bar)
    then = _asof(oi, t_avail, t_bar - lag_ns)
    with np.errstate(divide="ignore", invalid="ignore"):
        chg = np.log(now / then)
    bad = ~(np.isfinite(now) & np.isfinite(then)) | (now <= 0) | (then <= 0)
    chg[bad] = np.nan
    return chg


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    close_col = "close_time" if "close_time" in bars else "open_time"
    t_bar = _i64(bars[close_col])
    tf = _infer_tf_seconds(bars)
    win = max(int(round(Z_WINDOW_DAYS * 86400.0 / tf)), 1)

    M = _load_metrics()
    out: dict[str, np.ndarray] = {}
    for k in OI_CHG_KS:
        lag_ns = int(round(k * tf * 1_000_000_000))
        out[f"pos_oi_chg_{k}"] = _oi_chg(M["oi"], M["avail"], t_bar, lag_ns)

    oi_asof = _asof(M["oi"], M["avail"], t_bar)
    out["pos_oi_z_30d"] = _z_trailing(oi_asof, win)

    bc = bars["close"].astype(float).to_numpy(float)
    price_ret: dict[int, np.ndarray] = {}
    for k in sorted(set(PRICE_RET_KS) | {24}):
        base = np.full(len(bc), np.nan)
        if len(bc) > k:
            base[k:] = bc[: len(bc) - k]
        with np.errstate(divide="ignore", invalid="ignore"):
            price_ret[k] = np.log(bc / base)
    with np.errstate(invalid="ignore"):
        out["pos_oi_price_div_24"] = price_ret[24] - out["pos_oi_chg_24"]

    for key, short in (("top_count", "top_count"), ("top_sum", "top_sum"),
                       ("ls_global", "ls_global"), ("taker", "taker")):
        lvl = _asof(M[key], M["avail"], t_bar)
        out[f"pos_{short}_lvl"] = lvl
        out[f"pos_{short}_z"] = _z_trailing(lvl, win)

    F = _load_funding_z()
    fz = _asof(F["z"], F["t"], t_bar)
    out["pos_funding_z"] = fz
    with np.errstate(invalid="ignore"):
        out["pos_fund_x_oi"] = fz * out["pos_oi_z_30d"]

    df = pd.DataFrame(out, index=idx)
    return df.astype(float)


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    f = compute(bars)
    bc = bars["close"].astype(float).to_numpy(float)
    base6 = np.full(len(bc), np.nan)
    if len(bc) > 6:
        base6[6:] = bc[: len(bc) - 6]
    with np.errstate(divide="ignore", invalid="ignore"):
        ret6 = np.log(bc / base6)

    ev: dict[str, pd.Series] = {}

    sig = pd.Series(0, index=idx)
    long_crowd = (f["pos_funding_z"] > CROWD_Z) & (f["pos_ls_global_z"] > CROWD_Z)
    short_crowd = (f["pos_funding_z"] < -CROWD_Z) & (f["pos_ls_global_z"] < -CROWD_Z)
    sig = sig.mask(long_crowd.fillna(False), -1)
    sig = sig.mask(short_crowd.fillna(False), 1).fillna(0)
    ev["pos_ev_crowd"] = sig.astype("int8")

    sig = pd.Series(0, index=idx)
    long_top = (f["pos_funding_z"] > CROWD_Z) & (f["pos_top_sum_z"] > CROWD_Z)
    short_top = (f["pos_funding_z"] < -CROWD_Z) & (f["pos_top_sum_z"] < -CROWD_Z)
    sig = sig.mask(long_top.fillna(False), -1)
    sig = sig.mask(short_top.fillna(False), 1).fillna(0)
    ev["pos_ev_crowd_top"] = sig.astype("int8")

    sig = pd.Series(0, index=idx)
    surge = (f["pos_oi_chg_6"] > SURGE_OI).fillna(False)
    rs = pd.Series(ret6, index=idx)
    sig = sig.mask(surge & (rs > 0).fillna(False), 1)
    sig = sig.mask(surge & (rs < 0).fillna(False), -1).fillna(0)
    ev["pos_ev_oi_cont"] = sig.astype("int8")

    sig = pd.Series(0, index=idx)
    sig = sig.mask((f["pos_oi_chg_6"] < FLUSH_OI).fillna(False), 1).fillna(0)
    ev["pos_ev_oi_flush"] = sig.astype("int8")

    return pd.DataFrame(ev, index=idx).astype("int8")
