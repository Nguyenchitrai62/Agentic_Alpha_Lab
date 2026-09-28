"""Premium-index / predicted-funding features from Binance 1m premium-index klines (registry v231, fixed before evaluation).

Binance funding: F = P_avg + clamp(I - P_avg, -0.05%, +0.05%), I = 0.01% per 8h interval, P_avg = time-weighted average of the premium
index over the interval with linearly increasing weights (1, 2, ..., n); the 1m kline close is used as the sample (Binance samples every
5 s). At the close of 4h bar t (time T = t + 4h) every 1m premium kline with open_time < T is known, so the predicted funding of the
running interval and all premium statistics below use only data before T. Rows = 4h bar open times (as the panels).

  pf_pred        predicted funding of the running interval from its samples so far (bps per interval)
  pf_pred_chg    pf_pred minus the last settled rate (bps)
  pf_prem_bar    mean premium over the bar (bps)
  pf_prem_last   mean premium of the bar's last 15 minutes minus the bar mean (bps; last-minute pressure, e.g. funding hunters)
  pf_prem_24h    mean premium over the last 24 h (bps)
  pf_prem_z      (24h mean - 90-day mean of the 24h means) / 90-day std
  pf_prem_chg    24h mean - 7-day mean (bps)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PF = ("pf_pred", "pf_pred_chg", "pf_prem_bar", "pf_prem_last", "pf_prem_24h", "pf_prem_z", "pf_prem_chg")
D = Path("data/raw/binance_premium_20260928")
# interest component per 8h interval: 0.01% for the majors except BNBUSDT (0), read from the settled rates BEFORE the first anchor
# (2020-01..2021-09-23: BNB median 0.0 bp and 39.5% of settlements exactly 0; the other four median 1.0 bp, ~50% exactly 1 bp)
INTEREST = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001, "SOLUSDT": 0.0001, "BNBUSDT": 0.0, "XRPUSDT": 0.0001}


def load(sym: str):
    p = pd.read_parquet(D / f"{sym}_premium_1m.parquet")[["open_time", "close"]].set_index("open_time")["close"].astype(float)
    f = pd.read_parquet(D / f"{sym}_funding.parquet")
    f = f.set_index("calc_time")[["funding_interval_hours", "last_funding_rate"]].astype(float)
    f.index = f.index.floor("min")
    # the monthly archive ends before the premium data: extend the (deterministic) settlement grid with unknown rates
    last, h = f.index[-1], float(f["funding_interval_hours"].iloc[-1])
    grid = pd.date_range(last + pd.Timedelta(hours=h), p.index[-1] + pd.Timedelta(hours=h), freq=f"{int(h)}h")
    f = pd.concat([f, pd.DataFrame({"funding_interval_hours": h, "last_funding_rate": float("nan")}, index=grid)])
    f.attrs["sym"] = sym
    return p, f


def reconstruct(p: pd.Series, f: pd.DataFrame, at: pd.DatetimeIndex, interest: float | None = None) -> pd.Series:
    """Predicted funding at each time in `at` for the interval running at that time, from 1m samples before the time."""
    i_rate = INTEREST.get(f.attrs.get("sym"), 0.0001) if interest is None else interest
    settle = f.index.to_numpy()
    hours = f["funding_interval_hours"].to_numpy()
    ti = p.index.to_numpy()
    cs_w = np.concatenate([[0.0], np.cumsum(p.to_numpy())])  # prefix sums for the weighted average
    idx = np.arange(len(ti), dtype=float)
    cs_iw = np.concatenate([[0.0], np.cumsum(p.to_numpy() * idx)])
    out = np.full(len(at), np.nan)
    for k, T in enumerate(at.to_numpy()):
        j = np.searchsorted(settle, T, side="left")  # next settlement >= T (the running interval ends there)
        if j >= len(settle):
            h = hours[-1] if len(hours) else 8
        else:
            h = hours[j]
        start = (settle[j] if j < len(settle) else T) - np.timedelta64(int(h * 60), "m")
        if start > T:  # T is before this interval started (e.g. the interval length changed); fall back to the previous one
            start = settle[j - 1] if j > 0 else T
        a, b = np.searchsorted(ti, start, side="left"), np.searchsorted(ti, T, side="left")  # samples with open_time in [start, T)
        n = b - a
        if n < 30:
            continue
        s = cs_w[b] - cs_w[a]
        sw = (cs_iw[b] - cs_iw[a]) - (a - 1) * s  # weights 1..n
        pavg = sw / (n * (n + 1) / 2)
        out[k] = pavg + np.clip(i_rate - pavg, -0.0005, 0.0005)
    return pd.Series(out, index=at)


def premium_features(sym: str, bar_open: pd.DatetimeIndex) -> pd.DataFrame:
    p, f = load(sym)
    T = bar_open + pd.Timedelta(hours=4)
    pred = reconstruct(p, f, T)
    # last settled rate known at T: the archive value, or (after the archive ends) the reconstruction at that settlement
    rec_settle = reconstruct(p, f, f.index)
    last_settled = f["last_funding_rate"].fillna(rec_settle)
    last_settled.index.name = "calc_time"
    ls = pd.merge_asof(pd.DataFrame({"T": T}), last_settled.rename("r").reset_index().rename(columns={"calc_time": "T"}),
                       on="T", direction="backward")["r"].to_numpy()  # settled at or before T (published at the settlement)
    g = p.groupby(p.index.floor("4h"))
    bar_mean = g.mean()
    mins = (p.index - p.index.floor("4h")) / pd.Timedelta(minutes=1)
    last15 = p[mins >= 225].groupby(p.index[mins >= 225].floor("4h")).mean()
    cnt = g.count()
    bm = bar_mean.where(cnt >= 200).reindex(bar_open)
    m24 = bar_mean.where(cnt >= 200).rolling(6, min_periods=5).mean().reindex(bar_open)
    m7d = bar_mean.where(cnt >= 200).rolling(42, min_periods=36).mean().reindex(bar_open)
    z_m, z_s = m24.rolling(540, min_periods=270).mean(), m24.rolling(540, min_periods=270).std()
    x = pd.DataFrame(index=bar_open)
    x["pf_pred"] = pred.to_numpy() * 1e4
    x["pf_pred_chg"] = (pred.to_numpy() - ls) * 1e4
    x["pf_prem_bar"] = bm.to_numpy() * 1e4
    x["pf_prem_last"] = (last15.reindex(bar_open).to_numpy() - bm.to_numpy()) * 1e4
    x["pf_prem_24h"] = m24.to_numpy() * 1e4
    x["pf_prem_z"] = ((m24 - z_m) / z_s).to_numpy()
    x["pf_prem_chg"] = (m24 - m7d).to_numpy() * 1e4
    return x[list(PF)]


def validate(sym: str) -> dict:
    """Data-quality check: the reconstruction at each settlement vs the settled rate."""
    p, f = load(sym)
    f = f[(f.index >= p.index[0] + pd.Timedelta(hours=8)) & f["last_funding_rate"].notna()]
    rec = reconstruct(p, f, f.index)
    act = f["last_funding_rate"]
    ok = rec.notna()
    err = (rec[ok] - act[ok]) * 1e4
    return {"n": int(ok.sum()), "corr": round(float(np.corrcoef(rec[ok], act[ok])[0, 1]), 4), "mae_bps": round(float(err.abs().mean()), 3),
            "p95_abs_bps": round(float(err.abs().quantile(0.95)), 3), "exact_within_0.1bp": round(float((err.abs() < 0.1).mean()), 3)}
