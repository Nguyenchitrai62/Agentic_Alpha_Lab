"""W7 macro risk regime for BTC (vf round).

Fixed definitions (do not change after seeing results; log any change below):

Data: daily closes 2019-06-01..2026-09-23 requested for SPY, QQQ, ^VIX, DX-Y.NYB,
^TNX, GLD from Yahoo Chart API v8 (Stooq free CSV returned HTTP 404 on this
host; disclosed in the manifest). Actual Yahoo last trading day at crawl time:
2026-09-18. Files: ``data/raw/macro_20260924/{spy,qqq,vix,dxy,tnx,gld}.csv``
plus ``manifest.json`` (source URL, row counts, SHA-256).

Availability: a US daily close for trading day D is known only after 22:00 UTC
of day D (spec: known after 21:00 UTC, use 22:00 UTC to be safe).
Weekends/holidays carry the last known value (forward-fill). For a BTC bar with
``close_time`` t, the as-of trading day is the latest date with
date+22h UTC <= t (merge_asof backward on availability time).

Daily indicators (all causal, rolling on daily closes, min_periods = window):
- SMA50 / SMA200 per asset.
- mac_{a}_dist_50d / _dist_200d = close / SMA - 1.
- mac_{a}_ret_20d = log(close / close.shift(20)).
- mac_{a}_rv_20d = population std (ddof=0) of daily log returns over 20 days.
- mac_risk_on_score (0-4) = (SPY>200d) + (QQQ>200d) + (VIX<20d median)
  + (DXY<200d); NaN until all four components are non-NaN.
- mac_btc_qqq_corr_60d = rolling 60-day Pearson correlation of BTC daily log
  returns (Binance 1d closes, full history) with QQQ daily log returns
  (min_periods=60).
- mac_dxy_chg_20d = log(DXY / DXY.shift(20)) (named separately per spec).

Events (int8 {-1,0,1}, edge-triggered, causal):
- mac_ev_risk_on: +1 when score rises to >=3 (prev <3), -1 when it falls to
  <=1 (prev >1); rows with NaN score never fire.
- mac_ev_vix_spike: -1 when VIX crosses above 1.2 * trailing-20d mean
  (rising edge only).
- mac_ev_dxy_breakout: -1 when DXY close crosses above its prior 55-trading-day
  maximum (shift(1) rolling-55 max; rising edge only).

Row t uses only information available at bars.close_time[t]; rows <= cut are
identical under truncation (external daily history is loaded whole and joined
as-of, so truncation only drops rows).

Post-hoc change log: none.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common

PREFIX = "mac_"
MACRO_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "macro_20260924"
ASSETS = ("spy", "qqq", "vix", "dxy", "tnx", "gld")

AVAIL_HOUR_UTC = 22
VIX_SPIKE_MULT = 1.2
VIX_MEAN_WINDOW = 20
VIX_MED_WINDOW = 20
RET_WINDOW = 20
CORR_WINDOW = 60
DXY_BREAK_WINDOW = 55
RISK_ON_HI = 3.0
RISK_ON_LO = 1.0

_DAILY_CACHE: pd.DataFrame | None = None
_AVAIL_CACHE: np.ndarray | None = None
_BTC_DAILY_CACHE: pd.DataFrame | None = None


def _load_daily() -> pd.DataFrame:
    """Per-asset daily closes indexed by date (union of trading days)."""
    global _DAILY_CACHE, _AVAIL_CACHE
    if _DAILY_CACHE is not None:
        return _DAILY_CACHE
    frames = {}
    for a in ASSETS:
        d = pd.read_csv(MACRO_DIR / f"{a}.csv", parse_dates=["date"])
        d = d.sort_values("date").drop_duplicates("date").reset_index(drop=True)
        frames[a] = d.set_index("date")["close"].astype(float)
    daily = pd.DataFrame(frames).sort_index()
    daily.index = pd.to_datetime(daily.index, utc=True).normalize()
    _DAILY_CACHE = daily
    _AVAIL_CACHE = (daily.index + pd.Timedelta(hours=AVAIL_HOUR_UTC)).values.astype(
        "datetime64[ns]"
    ).astype("int64")
    return daily


def _load_btc_daily() -> pd.DataFrame:
    """BTC 1d closes (full history incl. opened year) indexed by date."""
    global _BTC_DAILY_CACHE
    if _BTC_DAILY_CACHE is not None:
        return _BTC_DAILY_CACHE
    bars = common.load_bars("1d", include_opened_year=True)
    ct = pd.to_datetime(bars["close_time"], utc=True)
    dates = ct.dt.normalize()
    df = pd.DataFrame({"date": dates, "close": bars["close"].astype(float)})
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    _BTC_DAILY_CACHE = df
    return df


def _i64(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).values.astype("datetime64[ns]").astype("int64")


def _daily_indicators(daily: pd.DataFrame) -> pd.DataFrame:
    """All daily features indexed by trading day (causal rollings)."""
    ind = pd.DataFrame(index=daily.index)
    # Assets trade on different calendars; a single missing day would blank a
    # 200-day window for 200 days. Carry each asset's last known close forward.
    daily = daily.ffill()
    for a in ASSETS:
        c = daily[a]
        sma50 = c.rolling(50, min_periods=50).mean()
        sma200 = c.rolling(200, min_periods=200).mean()
        ind[f"mac_{a}_dist_50d"] = c / sma50 - 1
        ind[f"mac_{a}_dist_200d"] = c / sma200 - 1
        with np.errstate(divide="ignore", invalid="ignore"):
            ind[f"mac_{a}_ret_20d"] = np.log(c / c.shift(RET_WINDOW))
        r1 = np.log(c / c.shift(1))
        ind[f"mac_{a}_rv_20d"] = r1.rolling(RET_WINDOW, min_periods=RET_WINDOW).std(ddof=0)
        ind[f"_sma200_{a}"] = sma200
    spy_up = daily["spy"] > ind["_sma200_spy"]
    qqq_up = daily["qqq"] > ind["_sma200_qqq"]
    vix_med = daily["vix"].rolling(VIX_MED_WINDOW, min_periods=VIX_MED_WINDOW).median()
    vix_low = daily["vix"] < vix_med
    dxy_dn = daily["dxy"] < ind["_sma200_dxy"]
    parts = pd.DataFrame({"s": spy_up, "q": qqq_up, "v": vix_low, "d": dxy_dn})
    score = parts.sum(axis=1, min_count=1).astype(float)
    score[parts.isna().any(axis=1)] = np.nan
    ind["mac_risk_on_score"] = score
    ind["_vix_mean20"] = daily["vix"].rolling(VIX_MEAN_WINDOW, min_periods=VIX_MEAN_WINDOW).mean()
    ind["_dxy_max55"] = daily["dxy"].shift(1).rolling(DXY_BREAK_WINDOW, min_periods=DXY_BREAK_WINDOW).max()
    with np.errstate(divide="ignore", invalid="ignore"):
        ind["mac_dxy_chg_20d"] = np.log(daily["dxy"] / daily["dxy"].shift(RET_WINDOW))
    btc = _load_btc_daily()
    bdates = btc.index.union(daily.index).sort_values()
    b_aligned = btc["close"].reindex(bdates).ffill()
    q_aligned = daily["qqq"].reindex(bdates)
    with np.errstate(divide="ignore", invalid="ignore"):
        rb = np.log(b_aligned / b_aligned.shift(1))
        rq = np.log(q_aligned / q_aligned.shift(1))
    corr = rb.rolling(CORR_WINDOW, min_periods=CORR_WINDOW).corr(rq)
    ind["mac_btc_qqq_corr_60d"] = corr.reindex(daily.index)
    ind = ind.drop(columns=[c for c in ind.columns if c.startswith("_sma200_")])
    return ind


def _asof_rows(ind: pd.DataFrame, t_btc: np.ndarray) -> pd.DataFrame:
    daily = _load_daily()
    assert len(ind) == len(daily)
    avail = _AVAIL_CACHE
    assert avail is not None
    pos = np.searchsorted(avail, t_btc, side="right") - 1
    out = pd.DataFrame(index=range(len(t_btc)), columns=ind.columns, dtype=float)
    ok = pos >= 0
    if ok.any():
        out.iloc[np.flatnonzero(ok)] = ind.to_numpy()[pos[ok]]
    out.index = pd.RangeIndex(len(t_btc))
    return out


def _feature_cols() -> list[str]:
    cols: list[str] = []
    for a in ASSETS:
        cols += [f"mac_{a}_dist_50d", f"mac_{a}_dist_200d", f"mac_{a}_ret_20d", f"mac_{a}_rv_20d"]
    cols += ["mac_risk_on_score", "mac_btc_qqq_corr_60d", "mac_dxy_chg_20d"]
    return cols


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    daily = _load_daily()
    ind = _daily_indicators(daily)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    joined = _asof_rows(ind, t_btc)
    feat = joined[_feature_cols()]
    feat.index = bars.index
    return feat.astype(float)


def _edge_up(cur: pd.Series) -> np.ndarray:
    c = cur.to_numpy(bool)
    prev = np.concatenate([[False], c[:-1]])
    return c & ~prev


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    f = compute(bars)
    daily = _load_daily()
    ind = _daily_indicators(daily)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    sig = _asof_rows(ind[["_vix_mean20", "_dxy_max55"]], t_btc)
    sig.index = idx
    vix = _asof_rows(daily[["vix"]], t_btc)["vix"].to_numpy(float)
    dxy = _asof_rows(daily[["dxy"]], t_btc)["dxy"].to_numpy(float)
    vix_mean = sig["_vix_mean20"].to_numpy(float)
    dxy_max = sig["_dxy_max55"].to_numpy(float)

    s = f["mac_risk_on_score"]
    sp = s.shift(1)
    ev_risk = pd.Series(0, index=idx)
    ev_risk = ev_risk.mask((s >= RISK_ON_HI) & (sp < RISK_ON_HI) & s.notna() & sp.notna(), 1)
    ev_risk = ev_risk.mask((s <= RISK_ON_LO) & (sp > RISK_ON_LO) & s.notna() & sp.notna(), -1).fillna(0)

    spike = pd.Series(
        (~np.isnan(vix)) & (~np.isnan(vix_mean)) & (vix > VIX_SPIKE_MULT * vix_mean),
        index=idx,
    )
    ev_vix = pd.Series(np.where(_edge_up(spike), -1, 0), index=idx)

    brk = pd.Series(
        (~np.isnan(dxy)) & (~np.isnan(dxy_max)) & (dxy > dxy_max),
        index=idx,
    )
    ev_dxy = pd.Series(np.where(_edge_up(brk), -1, 0), index=idx)

    out = pd.DataFrame(
        {
            "mac_ev_risk_on": ev_risk.astype("int8"),
            "mac_ev_vix_spike": ev_vix.astype("int8"),
            "mac_ev_dxy_breakout": ev_dxy.astype("int8"),
        },
        index=idx,
    )
    return out.astype("int8")
