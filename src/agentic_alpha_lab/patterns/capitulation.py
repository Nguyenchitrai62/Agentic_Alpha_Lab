"""mj W16 capitulation / liquidation-cascade reversals: fixed causal definitions.

Single-asset module (timeframe-agnostic: 15m/1h majors, also 1h/4h/1d BTC).
Row t uses only bars.iloc[:t+1] (closed bars). No external history is loaded;
all baselines are trailing and exclude the current bar via shift(1), and ATR
is a forward-only Wilder RMA, so truncation at any cut leaves rows <= cut
identical (see tests with common.assert_causal).

Fixed definitions (chosen before any event study; log post-hoc changes below):
- ATR14: Wilder RMA (alpha=1/14, adjust=False, min_periods=14) of true range.
  atr_base = ATR14.shift(1); atr_pct_base = atr_base / close.shift(1).
- ret = log(close / close.shift(1)).
  ret_flush_down: ret < -RET_MULT * atr_pct_base (RET_MULT=3).
  ret_sqz_up:     ret > +RET_MULT * atr_pct_base.
- prior20low = low.shift(1).rolling(20, min_periods=20).min();
  prior20high = high.shift(1).rolling(20, min_periods=20).max().
  low_flush:  low  < prior20low  - BRK_MULT * atr_base (BRK_MULT=1).
  high_flush: high > prior20high + BRK_MULT * atr_base.
- qv = quote_volume if present else volume * close. mu/sd over
  qv.shift(1).rolling(60, min_periods=60) (ddof=0, sd==0 -> NaN).
  vol_flush: (qv - mu) / sd > VOL_Z (VOL_Z=3).
- range = high - low; lower_wick = min(open,close) - low; upper_wick =
  high - max(open,close); ratios = wick / range (range<=0 -> 0.0).
  recovery wick: lower (down) / upper (up) ratio >= WICK_REC (0.5).
  no-wick continuation: ratio < WICK_CONT (0.2).
- flush_down = (ret_flush_down | low_flush) & vol_flush.
  flush_down_wick = flush_down & (lower_wick >= 0.5).
  flush_down_nowick = flush_down & (lower_wick < 0.2).
  Mirror for squeeze-up (upper wick).
- Multi-asset cascade (>=3 of 5 majors flush in the same bar) is a
  study-level construction (needs aligned multi-asset bars, which a
  single-asset compute(bars)/events(bars) cannot see); see
  research/mj/capitulation_study.py which builds cap_ev_cascade_rev/cont
  from the single-asset events. The BTC OI-flush cross-check uses
  agentic_alpha_lab.patterns.positioning.pos_ev_oi_flush in the study.

Events (int8 {-1,0,1}, signal at the flush bar itself; common.event_study
enters at the next open):
- cap_ev_down_rev: +1 on flush_down_wick (reversal hypothesis).
- cap_ev_down_cont: -1 on flush_down_nowick (continuation).
- cap_ev_up_rev: -1 on flush_up_wick (mirror reversal).
- cap_ev_up_cont: +1 on flush_up_nowick (mirror continuation).
- cap_ev_rev: +1 down-wick / -1 up-wick.
- cap_ev_cont: -1 down-nowick / +1 up-nowick.

Post-hoc change log: none.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PREFIX = "cap_"
ATR_PERIOD = 14
RET_MULT = 3.0
BRK_MULT = 1.0
LOWBACK = 20
VOL_WINDOW = 60
VOL_Z = 3.0
WICK_REC = 0.5
WICK_CONT = 0.2


def _atr14(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / ATR_PERIOD, adjust=False, min_periods=ATR_PERIOD).mean()


def _quote_volume(bars: pd.DataFrame) -> pd.Series:
    if "quote_volume" in bars:
        return bars["quote_volume"].astype(float)
    c = bars["close"].astype(float)
    v = bars["volume"].astype(float) if "volume" in bars else pd.Series(np.nan, index=bars.index)
    return v * c


def _frame(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    o = bars["open"].astype(float)
    h = bars["high"].astype(float)
    lo = bars["low"].astype(float)
    c = bars["close"].astype(float)
    atr = _atr14(h, lo, c)
    atr_base = atr.shift(1)
    prev_c = c.shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = np.log(c / prev_c)
        atr_pct_base = atr_base / prev_c
        ret_atr = ret / atr_pct_base
    prior_low = lo.shift(1).rolling(LOWBACK, min_periods=LOWBACK).min()
    prior_high = h.shift(1).rolling(LOWBACK, min_periods=LOWBACK).max()
    low_dist = (lo - prior_low) / atr_base
    high_dist = (h - prior_high) / atr_base

    qv = _quote_volume(bars)
    qv_prev = qv.shift(1)
    mu = qv_prev.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).mean()
    sd = qv_prev.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std(ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        qv_z = (qv - mu) / sd.replace(0, np.nan)

    rng = (h - lo).to_numpy(float)
    body_lo = pd.concat([o, c], axis=1).min(axis=1).to_numpy(float)
    body_hi = pd.concat([o, c], axis=1).max(axis=1).to_numpy(float)
    lo_n = lo.to_numpy(float)
    hi_n = h.to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        lower_w = np.where(rng > 0, (body_lo - lo_n) / np.where(rng > 0, rng, 1.0), 0.0)
        upper_w = np.where(rng > 0, (hi_n - body_hi) / np.where(rng > 0, rng, 1.0), 0.0)
        range_atr = np.where(
            np.isfinite(atr_base.to_numpy(float)) & (atr_base.to_numpy(float) > 0),
            rng / np.where(atr_base.to_numpy(float) > 0, atr_base.to_numpy(float), np.nan),
            np.nan,
        )
    lower_w = pd.Series(np.clip(lower_w, 0.0, 1.0), index=idx).where(
        np.isfinite(lower_w), 0.0
    )
    upper_w = pd.Series(np.clip(upper_w, 0.0, 1.0), index=idx).where(
        np.isfinite(upper_w), 0.0
    )

    ret_flush_down = (ret < -RET_MULT * atr_pct_base).fillna(False)
    low_flush = (lo < prior_low - BRK_MULT * atr_base).fillna(False)
    vol_flush = (qv_z > VOL_Z).fillna(False)
    ret_sqz_up = (ret > RET_MULT * atr_pct_base).fillna(False)
    high_flush = (h > prior_high + BRK_MULT * atr_base).fillna(False)

    flush_down = (ret_flush_down | low_flush) & vol_flush
    flush_up = (ret_sqz_up | high_flush) & vol_flush
    down_wick = flush_down & (lower_w >= WICK_REC)
    down_nowick = flush_down & (lower_w < WICK_CONT)
    up_wick = flush_up & (upper_w >= WICK_REC)
    up_nowick = flush_up & (upper_w < WICK_CONT)

    return pd.DataFrame(
        {
            "atr": atr,
            "atr_base": atr_base,
            "atr_pct_base": atr_pct_base,
            "ret": ret,
            "ret_atr": ret_atr,
            "low_dist": low_dist,
            "high_dist": high_dist,
            "qv_z": qv_z,
            "lower_w": lower_w,
            "upper_w": upper_w,
            "range_atr": pd.Series(range_atr, index=idx),
            "flush_down": flush_down,
            "down_wick": down_wick,
            "down_nowick": down_nowick,
            "flush_up": flush_up,
            "up_wick": up_wick,
            "up_nowick": up_nowick,
        },
        index=idx,
    )


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    """Float features, same index as bars (prefix cap_)."""
    f = _frame(bars)
    out = pd.DataFrame(index=bars.index)
    out["cap_atr14"] = f["atr"]
    out["cap_atr_pct"] = f["atr"] / bars["close"].astype(float)
    out["cap_ret"] = f["ret"]
    out["cap_ret_atr"] = f["ret_atr"]
    out["cap_low_dist_atr"] = f["low_dist"]
    out["cap_high_dist_atr"] = f["high_dist"]
    out["cap_qv_z60"] = f["qv_z"]
    out["cap_lower_wick"] = f["lower_w"]
    out["cap_upper_wick"] = f["upper_w"]
    out["cap_range_atr"] = f["range_atr"]
    out["cap_flush_down"] = f["flush_down"].astype(float)
    out["cap_flush_down_wick"] = f["down_wick"].astype(float)
    out["cap_flush_down_nowick"] = f["down_nowick"].astype(float)
    out["cap_flush_up"] = f["flush_up"].astype(float)
    out["cap_flush_up_wick"] = f["up_wick"].astype(float)
    out["cap_flush_up_nowick"] = f["up_nowick"].astype(float)
    return out.astype(float)


def events(bars: pd.DataFrame) -> pd.DataFrame:
    """int8 directional hypotheses in {-1, 0, 1}."""
    f = _frame(bars)
    idx = bars.index
    ev: dict[str, pd.Series] = {}
    ev["cap_ev_down_rev"] = (f["down_wick"].to_numpy(bool).astype(np.int8) * np.int8(1)).astype(np.int8)
    ev["cap_ev_down_rev"] = pd.Series(ev["cap_ev_down_rev"], index=idx, dtype="int8")
    ev["cap_ev_down_cont"] = pd.Series(
        np.where(f["down_nowick"].to_numpy(bool), np.int8(-1), np.int8(0)), index=idx
    ).astype("int8")
    ev["cap_ev_up_rev"] = pd.Series(
        np.where(f["up_wick"].to_numpy(bool), np.int8(-1), np.int8(0)), index=idx
    ).astype("int8")
    ev["cap_ev_up_cont"] = pd.Series(
        np.where(f["up_nowick"].to_numpy(bool), np.int8(1), np.int8(0)), index=idx
    ).astype("int8")
    rev = np.zeros(len(idx), dtype=np.int8)
    rev[f["down_wick"].to_numpy(bool)] = np.int8(1)
    rev[f["up_wick"].to_numpy(bool)] = np.int8(-1)
    ev["cap_ev_rev"] = pd.Series(rev, index=idx, dtype="int8")
    cont = np.zeros(len(idx), dtype=np.int8)
    cont[f["down_nowick"].to_numpy(bool)] = np.int8(-1)
    cont[f["up_nowick"].to_numpy(bool)] = np.int8(1)
    ev["cap_ev_cont"] = pd.Series(cont, index=idx, dtype="int8")
    return pd.DataFrame(ev, index=idx).astype("int8")
