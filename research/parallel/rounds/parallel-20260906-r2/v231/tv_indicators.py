"""Popular TradingView indicators as causal 4h-bar features (registry v231, fixed list before any evaluation).

Every value at row i uses bars 0..i only (the row is known at the close of bar i). Distances are in ATR(14) units so they are
comparable across assets and eras. Swing pivots (market structure) are confirmed only after their 3 right-hand bars have closed.
Parameters are the indicators' standard TradingView defaults (no tuning).

  SuperTrend (10, 3)                    tv_st_dir (+1/-1), tv_st_dist
  Squeeze Momentum, LazyBear (20, 2, 1.5) tv_sqz_on (BB inside KC), tv_sqz_mom, tv_sqz_slope
  WaveTrend, LazyBear (10, 21)          tv_wt1, tv_wt_diff
  Williams VIX Fix (22)                 tv_wvf_z (z over 50 bars)
  Ichimoku (9, 26, 52)                  tv_ich_cloud (close vs the displaced cloud), tv_ich_tk
  Anchored VWAP (week, month, UTC)      tv_vwap_w, tv_vwap_m
  Volume profile POC (180 bars, 50 bins) tv_poc
  Market structure (3/3 pivots)         tv_ms_trend (+1 last break up / -1 down), tv_ms_hi, tv_ms_lo
  Fisher transform (10)                 tv_fisher
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TV = ("tv_st_dir", "tv_st_dist", "tv_sqz_on", "tv_sqz_mom", "tv_sqz_slope", "tv_wt1", "tv_wt_diff", "tv_wvf_z", "tv_ich_cloud",
      "tv_ich_tk", "tv_vwap_w", "tv_vwap_m", "tv_poc", "tv_ms_trend", "tv_ms_hi", "tv_ms_lo", "tv_fisher")


def _atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _linreg_last(s, n):
    # value of the least-squares line at the last point of each rolling window (TradingView linreg(src, n, 0))
    x = np.arange(n, dtype=float)
    xm = x.mean()
    den = ((x - xm) ** 2).sum()

    def f(w):
        b = ((x - xm) * (w - w.mean())).sum() / den
        return w.mean() + b * (n - 1 - xm)
    return s.rolling(n).apply(f, raw=True)


def supertrend(h, l, c, n=10, m=3.0):
    atr = _atr(h, l, c, n).to_numpy()
    hl2 = ((h + l) / 2).to_numpy()
    cc = c.to_numpy()
    up, dn = hl2 - m * atr, hl2 + m * atr
    fu, fd = up.copy(), dn.copy()
    d = np.ones(len(cc))
    line = np.full(len(cc), np.nan)
    for i in range(1, len(cc)):
        if np.isnan(atr[i]):
            continue
        fu[i] = max(up[i], fu[i - 1]) if not np.isnan(fu[i - 1]) and cc[i - 1] > fu[i - 1] else up[i]
        fd[i] = min(dn[i], fd[i - 1]) if not np.isnan(fd[i - 1]) and cc[i - 1] < fd[i - 1] else dn[i]
        if d[i - 1] == -1 and cc[i] > fd[i - 1]:
            d[i] = 1
        elif d[i - 1] == 1 and cc[i] < fu[i - 1]:
            d[i] = -1
        else:
            d[i] = d[i - 1]
        line[i] = fu[i] if d[i] == 1 else fd[i]
    return pd.Series(d, index=c.index), pd.Series(line, index=c.index)


def market_structure(h, l, c, k=3):
    hh, ll, cc = h.to_numpy(), l.to_numpy(), c.to_numpy()
    n = len(cc)
    sh, sl = np.nan, np.nan
    trend = np.zeros(n)
    last_h, last_l = np.full(n, np.nan), np.full(n, np.nan)
    tr = 0.0
    for i in range(n):
        j = i - k  # candidate pivot whose k right-hand bars are now closed
        if j - k >= 0:
            if hh[j] == hh[j - k:i + 1].max():
                sh = hh[j]
            if ll[j] == ll[j - k:i + 1].min():
                sl = ll[j]
        if not np.isnan(sh) and cc[i] > sh:
            tr = 1.0
        elif not np.isnan(sl) and cc[i] < sl:
            tr = -1.0
        trend[i], last_h[i], last_l[i] = tr, sh, sl
    return trend, last_h, last_l


def anchored_vwap(b, freq):
    tp = (b["high"] + b["low"] + b["close"]) / 3
    v = b["volume"].astype(float).clip(lower=0)
    key = b["open_time"].dt.to_period(freq)
    pv = (tp * v).groupby(key.to_numpy()).cumsum()
    vv = v.groupby(key.to_numpy()).cumsum()
    return pv / vv.replace(0, np.nan)


def poc(b, n=180, bins=50):
    tp = ((b["high"] + b["low"] + b["close"]) / 3).to_numpy()
    v = b["volume"].astype(float).clip(lower=0).to_numpy()
    out = np.full(len(tp), np.nan)
    for i in range(n - 1, len(tp)):
        p, w = tp[i - n + 1:i + 1], v[i - n + 1:i + 1]
        if w.sum() <= 0:
            continue
        hist, edges = np.histogram(p, bins=bins, weights=w)
        k = int(hist.argmax())
        out[i] = (edges[k] + edges[k + 1]) / 2
    return out


def fisher(h, l, n=10):
    hl2 = (h + l) / 2
    mx, mn = hl2.rolling(n).max(), hl2.rolling(n).min()
    raw = (2 * ((hl2 - mn) / (mx - mn).replace(0, np.nan) - 0.5)).fillna(0).to_numpy()
    val = np.zeros(len(raw))
    fi = np.zeros(len(raw))
    for i in range(1, len(raw)):
        val[i] = np.clip(0.66 * raw[i] + 0.67 * val[i - 1], -0.999, 0.999)
        fi[i] = 0.5 * np.log((1 + val[i]) / (1 - val[i])) + 0.5 * fi[i - 1]
    s = pd.Series(fi, index=h.index)
    s[mx.isna()] = np.nan
    return s


def tv_features(b: pd.DataFrame) -> pd.DataFrame:
    """b: 4h bars (open_time, open, high, low, close, volume), sorted; returns the TV feature frame on b's index."""
    h, l, c = b["high"].astype(float), b["low"].astype(float), b["close"].astype(float)
    atr = _atr(h, l, c, 14)
    x = pd.DataFrame(index=b.index)
    d, line = supertrend(h, l, c)
    x["tv_st_dir"], x["tv_st_dist"] = d, (c - line) / atr
    # squeeze momentum (LazyBear)
    basis, dev = c.rolling(20).mean(), 2.0 * c.rolling(20).std(ddof=0)
    pc = c.shift(1)
    rng = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1).rolling(20).mean()  # LazyBear useTrueRange
    x["tv_sqz_on"] = ((basis - dev > basis - 1.5 * rng) & (basis + dev < basis + 1.5 * rng)).astype(float)
    mid = ((h.rolling(20).max() + l.rolling(20).min()) / 2 + basis) / 2
    mom = _linreg_last(c - mid, 20) / atr
    x["tv_sqz_mom"], x["tv_sqz_slope"] = mom, mom - mom.shift(3)
    # WaveTrend (LazyBear)
    ap = (h + l + c) / 3
    esa = ap.ewm(span=10, adjust=False).mean()
    dd = (ap - esa).abs().ewm(span=10, adjust=False).mean()
    ci = (ap - esa) / (0.015 * dd.replace(0, np.nan))
    wt1 = ci.ewm(span=21, adjust=False).mean()
    wt2 = wt1.rolling(4).mean()
    x["tv_wt1"], x["tv_wt_diff"] = wt1, wt1 - wt2
    # Williams VIX Fix
    wvf = 100 * (c.rolling(22).max() - l) / c.rolling(22).max()
    x["tv_wvf_z"] = (wvf - wvf.rolling(50).mean()) / wvf.rolling(50).std()
    # Ichimoku: the cloud plotted at bar i was computed at bar i - 26
    ten = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kij = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa = ((ten + kij) / 2).shift(26)
    sb = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    top, bot = pd.concat([sa, sb], axis=1).max(axis=1), pd.concat([sa, sb], axis=1).min(axis=1)
    x["tv_ich_cloud"] = np.where(c > top, (c - top) / atr, np.where(c < bot, (c - bot) / atr, 0.0))
    x.loc[sb.isna(), "tv_ich_cloud"] = np.nan
    x["tv_ich_tk"] = (ten - kij) / atr
    ot = b["open_time"].dt.tz_convert(None)
    bb = b.assign(open_time=ot)
    x["tv_vwap_w"] = (c - anchored_vwap(bb, "W-SUN").to_numpy()) / atr
    x["tv_vwap_m"] = (c - anchored_vwap(bb, "M").to_numpy()) / atr
    x["tv_poc"] = (c - poc(b)) / atr
    tr, sh, sl = market_structure(h, l, c)
    x["tv_ms_trend"], x["tv_ms_hi"], x["tv_ms_lo"] = tr, (c - sh) / atr, (c - sl) / atr
    x["tv_fisher"] = fisher(h, l)
    return x[list(TV)]
