"""Opencode R6-M (v28 bigmodel): causal feature builders dung chung local + Kaggle.

Nguon (tat ca past-only, fit-normalization tren train-window tung fold):
  price40 (frozen) + deriv40 (lag48 scenario, disclosed) + flow40 (causal) +
  fund5 (as-of funding_time < signal_time) + macro4 (strict T-1) + cal4.
Output: flat (n,133), layout DONG BANG: [:40] price, [40:80] deriv,
[80:120] flow, [120:125] funding, [125:129] macro, [129:133] calendar.
"""
import torch  # noqa: F401  (torch truoc pandas: tranh loi DLL tren host nay)
import bisect
from pathlib import Path

import numpy as np
import pandas as pd

N_PRICE, N_DERIV, N_FLOW, N_FUND, N_MACRO, N_CAL = 40, 40, 40, 5, 4, 4
N_FLAT = N_PRICE + N_DERIV + N_FLOW + N_FUND + N_MACRO + N_CAL
assert N_FLAT == 133

FUND_NAMES = ["fund_rate", "fund_7d", "fund_30d", "fund_slope_7d", "fund_z30"]
MACRO_NAMES = ["risk_on", "spy_gap_ma50", "dxy_z60", "spy_amp20"]
CAL_NAMES = ["bars_to_funding", "sin_utc_hour", "cos_utc_hour", "is_weekend_utc"]


def build_funding(signal_time, funding_parquet):
    """As-of join: moi decision chi dung ky co funding_time < signal_time."""
    f = pd.read_parquet(funding_parquet)
    f = f.sort_values("funding_time").reset_index(drop=True)
    ft = pd.to_datetime(f["funding_time"], utc=True).to_numpy()
    rate = f["fundingRate"].to_numpy(dtype=np.float64)
    st = pd.to_datetime(signal_time, utc=True).to_numpy()
    pos = np.searchsorted(ft, st, side="left") - 1
    if (pos < 90).any():
        raise ValueError(f"Thieu lich su funding 90 ky cho {(pos < 90).sum()} decisions")
    out = np.empty((len(st), 5), dtype=np.float64)
    for i, p in enumerate(pos):
        w7 = rate[p - 20:p + 1]
        w30 = rate[p - 89:p + 1]
        mu30 = w30.mean()
        sd30 = w30.std(ddof=1)
        prev7 = rate[p - 41:p - 20].mean()
        out[i] = [rate[p], w7.mean(), mu30, w7.mean() - prev7,
                  (rate[p] - mu30) / max(sd30, 1e-9)]
    if not np.isfinite(out).all():
        raise ValueError("Nonfinite funding features")
    return out


def _daily_feature_table(macro_dir, decisions_utc_date):
    """Bang feature theo ngay, chi tu macro dong cua ngay < signal date."""
    spy = pd.read_parquet(Path(macro_dir) / "spy.parquet").sort_values("date").reset_index(drop=True)
    dxy = pd.read_parquet(Path(macro_dir) / "dxy.parquet").sort_values("date").reset_index(drop=True)
    spy["d"] = pd.to_datetime(spy["date"], utc=True).dt.date
    dxy["d"] = pd.to_datetime(dxy["date"], utc=True).dt.date
    sc, sh, sl = spy["close"].to_numpy(float), spy["high"].to_numpy(float), spy["low"].to_numpy(float)
    dc = dxy["close"].to_numpy(float)
    sdates = spy["d"].tolist()
    dmap = {d: i for i, d in enumerate(dxy["d"].tolist())}
    rows = {}
    for d in sorted(set(decisions_utc_date)):
        i = bisect.bisect_left(sdates, d) - 1  # ngay SPY gan nhat TRUOC D
        if i < 59:
            raise ValueError(f"Thieu lich su macro 60d cho {d}")
        ma50 = sc[i - 49:i + 1].mean()
        mu60, sd60 = dc[dmap[sdates[i]] - 59:dmap[sdates[i]] + 1].mean(), \
            dc[dmap[sdates[i]] - 59:dmap[sdates[i]] + 1].std(ddof=1)
        amp20 = (sh[i - 19:i + 1].max() - sl[i - 19:i + 1].min()) / sc[i]
        rows[d] = [1.0 if sc[i] > ma50 else 0.0, sc[i] / ma50 - 1.0,
                   (dc[dmap[sdates[i]]] - mu60) / max(sd60, 1e-9), amp20]
    return rows


def build_macro(signal_time, macro_dir):
    st = pd.to_datetime(signal_time, utc=True)
    table = _daily_feature_table(macro_dir, st.dt.date)
    out = np.array([table[d] for d in st.dt.date], dtype=np.float64)
    if not np.isfinite(out).all():
        raise ValueError("Nonfinite macro features")
    return out


def build_calendar(signal_time):
    t = pd.to_datetime(signal_time, utc=True)
    hh = t.dt.hour.to_numpy() if hasattr(t.dt.hour, "to_numpy") else np.asarray(t.dt.hour)
    mm = np.asarray(t.dt.minute, dtype=float)
    ss = np.asarray(t.dt.second, dtype=float)
    hod = hh + mm / 60.0 + ss / 3600.0
    mins_to_next = ((8 - (hh % 8)) % 8) * 60 - mm - ss / 60.0
    mins_to_next = np.where(mins_to_next <= 0, mins_to_next + 480, mins_to_next)
    dow = np.asarray(t.dt.dayofweek)
    return np.stack([mins_to_next / 5.0, np.sin(2 * np.pi * hod / 24.0),
                     np.cos(2 * np.pi * hod / 24.0), (dow >= 5).astype(float)], -1)


def build_flow(candles, signal_time):
    from agentic_alpha_lab.data.flow_features import flow_features
    feats, names = flow_features(candles, pd.Series(pd.to_datetime(signal_time, utc=True)))
    feats = np.asarray(feats, dtype=np.float64)
    if feats.shape[1] != N_FLOW or not np.isfinite(feats).all():
        raise ValueError(f"Flow shape/finite: {feats.shape}")
    return feats, names


def build_flat(decisions, candles, examples_npz, deriv_npz, funding_parquet, macro_dir):
    with np.load(examples_npz, allow_pickle=False) as z:
        price = z["features"].astype(np.float64)
    with np.load(deriv_npz, allow_pickle=False) as z:
        deriv = z["features"].astype(np.float64)
    if price.shape != (len(decisions), N_PRICE) or deriv.shape != (len(decisions), N_DERIV):
        raise ValueError(f"Shape price/deriv: {price.shape} {deriv.shape}")
    if not (np.isfinite(price).all() and np.isfinite(deriv).all()):
        raise ValueError("Nonfinite price/deriv")
    flow, _ = build_flow(candles, decisions["signal_time"])
    fund = build_funding(decisions["signal_time"], funding_parquet)
    macro = build_macro(decisions["signal_time"], macro_dir)
    cal = build_calendar(decisions["signal_time"])
    flat = np.concatenate([price, deriv, flow, fund, macro, cal], -1)
    if flat.shape != (len(decisions), N_FLAT) or not np.isfinite(flat).all():
        raise ValueError(f"Flat shape/finite: {flat.shape}")
    return flat
