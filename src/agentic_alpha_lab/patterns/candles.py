"""W1 candlestick patterns: textbook definitions as causal features/events.

Row t uses only bars[:t+1]. ATR14 is a 14-bar simple moving mean of the true
range (causal, includes current bar). Trend filter: DOWNTREND = close < close5
ago AND close < SMA10; UPTREND = mirror. Sizes relative to ATR14/bar range.

No post-hoc tuning: definitions fixed before running the event study.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PREFIX = "cdl_"

# ---- recorded textbook parameters ----
ATR_PERIOD = 14
SMA_TREND = 10
TREND_LOOKBACK = 5
DOJI_BODY_RANGE = 0.10
SPIN_BODY_LO = 0.10
SPIN_BODY_HI = 0.30
SPIN_WICK_MIN = 0.25
DRAGON_UPPER_MAX = 0.15
DRAGON_LOWER_MIN = 0.60
GRAVE_LOWER_MAX = 0.15
GRAVE_UPPER_MIN = 0.60
LONGLEG_WICK_MIN = 0.30
LONGLEG_RANGE_ATR = 0.70
MARUBOZU_SHADOW_MAX = 0.10
MARUBOZU_BODY_MIN = 0.90
HAMMER_LOWER_MIN = 0.60
HAMMER_UPPER_MAX = 0.20
HAMMER_BODY_MAX = 0.30
HAMMER_CLV_MIN = 0.55
SHOOT_UPPER_MIN = 0.60
SHOOT_LOWER_MAX = 0.20
SHOOT_BODY_MAX = 0.30
SHOOT_CLV_MAX = 0.45
PIN_LOWER_MIN = 0.60
PIN_UPPER_MAX = 0.20
PIN_BODY_MAX = 0.35
TWEEZER_TOL_ATR = 0.10
HARAMI_PREV_BODY_ATR = 0.30
SOLDIERS_BODY_ATR = 0.20
RANGE_EPS = 1e-12


def _atr14(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()


def _frame(bars: pd.DataFrame) -> pd.DataFrame:
    o = bars["open"].astype(float)
    h = bars["high"].astype(float)
    lw = bars["low"].astype(float)
    c = bars["close"].astype(float)
    body = c - o
    abs_body = body.abs()
    rng = (h - lw).clip(lower=0.0)
    safe_rng = rng.clip(lower=RANGE_EPS)
    upper = h - pd.concat([o, c], axis=1).max(axis=1)
    lower = pd.concat([o, c], axis=1).min(axis=1) - lw
    atr = _atr14(h, lw, c)
    safe_atr = atr.clip(lower=RANGE_EPS)
    sma10 = c.rolling(SMA_TREND).mean()
    c5 = c.shift(TREND_LOOKBACK)
    downtrend = (c < c5) & (c < sma10)
    uptrend = (c > c5) & (c > sma10)
    clv = ((c - lw) / safe_rng).clip(0.0, 1.0)
    clv = clv.where(rng > 0, 0.5)
    prev_c = c.shift(1)
    prev_o = o.shift(1)
    prev_h = h.shift(1)
    prev_l = lw.shift(1)
    return pd.DataFrame(
        {
            "o": o, "h": h, "l": lw, "c": c, "body": body,
            "abs_body": abs_body, "rng": rng, "safe_rng": safe_rng,
            "upper": upper.clip(lower=0.0), "lower": lower.clip(lower=0.0),
            "atr": atr, "safe_atr": safe_atr, "sma10": sma10,
            "downtrend": downtrend.fillna(False), "uptrend": uptrend.fillna(False),
            "clv": clv, "prev_c": prev_c, "prev_o": prev_o,
            "prev_h": prev_h, "prev_l": prev_l,
        },
        index=bars.index,
    )


def _patterns(f: pd.DataFrame) -> pd.DataFrame:
    body_r = f["abs_body"] / f["safe_rng"]
    up_r = f["upper"] / f["safe_rng"]
    lo_r = f["lower"] / f["safe_rng"]
    valid_range = f["rng"] > 0
    atr_ok = f["atr"].notna()

    doji = (body_r <= DOJI_BODY_RANGE) & valid_range
    dragonfly = doji & (lo_r >= DRAGON_LOWER_MIN) & (up_r <= DRAGON_UPPER_MAX)
    gravestone = doji & (up_r >= GRAVE_UPPER_MIN) & (lo_r <= GRAVE_LOWER_MAX)
    longlegged = doji & (up_r >= LONGLEG_WICK_MIN) & (lo_r >= LONGLEG_WICK_MIN) & (
        atr_ok & (f["rng"] >= LONGLEG_RANGE_ATR * f["safe_atr"])
    )
    spinning = (
        (body_r > SPIN_BODY_LO) & (body_r <= SPIN_BODY_HI)
        & (up_r >= SPIN_WICK_MIN) & (lo_r >= SPIN_WICK_MIN) & valid_range
    )
    maru_shape = ((f["upper"] + f["lower"]) <= MARUBOZU_SHADOW_MAX * f["safe_rng"]) & (
        body_r >= MARUBOZU_BODY_MIN
    ) & valid_range
    marubozu_bull = maru_shape & (f["body"] > 0)
    marubozu_bear = maru_shape & (f["body"] < 0)

    hammer_shape = (
        (lo_r >= HAMMER_LOWER_MIN) & (up_r <= HAMMER_UPPER_MAX)
        & (body_r <= HAMMER_BODY_MAX) & (f["clv"] >= HAMMER_CLV_MIN) & valid_range
    )
    hammer = hammer_shape & f["downtrend"]
    hanging_man = hammer_shape & f["uptrend"]
    inv_shape = (
        (up_r >= SHOOT_UPPER_MIN) & (lo_r <= SHOOT_LOWER_MAX)
        & (body_r <= SHOOT_BODY_MAX) & (f["clv"] <= SHOOT_CLV_MAX) & valid_range
    )
    inverted_hammer = inv_shape & f["downtrend"]
    shooting_star = inv_shape & f["uptrend"]
    pinbar_bull = (
        (lo_r >= PIN_LOWER_MIN) & (up_r <= PIN_UPPER_MAX)
        & (body_r <= PIN_BODY_MAX) & valid_range
    )
    pinbar_bear = (
        (up_r >= PIN_LOWER_MIN) & (lo_r <= PIN_UPPER_MAX)
        & (body_r <= PIN_BODY_MAX) & valid_range
    )

    po = f["prev_o"]
    pc = f["prev_c"]
    prev_green = pc > po
    prev_red = pc < po
    curr_green = f["c"] > f["o"]
    curr_red = f["c"] < f["o"]
    has_prev = po.notna() & pc.notna()
    engulf_bull = (
        has_prev & prev_red & curr_green
        & (f["o"] <= pc) & (f["c"] >= po)
    )
    engulf_bear = (
        has_prev & prev_green & curr_red
        & (f["o"] >= pc) & (f["c"] <= po)
    )
    prev_body_atr = (pc - po).abs() / f["safe_atr"]
    curr_body_atr = f["abs_body"] / f["safe_atr"]
    harami_bull = (
        has_prev & atr_ok & prev_red
        & (prev_body_atr >= HARAMI_PREV_BODY_ATR) & curr_green
        & (f["o"] > pc) & (f["c"] < po) & (curr_body_atr < prev_body_atr)
    )
    harami_bear = (
        has_prev & atr_ok & prev_green
        & (prev_body_atr >= HARAMI_PREV_BODY_ATR) & curr_red
        & (f["o"] < pc) & (f["c"] > po) & (curr_body_atr < prev_body_atr)
    )
    prev_mid = (po + pc) / 2.0
    piercing = (
        has_prev & f["downtrend"] & prev_red & (f["body"] > 0)
        & (f["o"] < pc) & (f["c"] > prev_mid) & (f["c"] < po)
    )
    dark_cloud = (
        has_prev & f["uptrend"] & prev_green & (f["body"] < 0)
        & (f["o"] > pc) & (f["c"] < prev_mid) & (f["c"] > po)
    )

    o2 = f["o"].shift(1)
    c2 = f["c"].shift(1)
    o3 = f["o"].shift(2)
    c3 = f["c"].shift(2)
    three_ok = o2.notna() & c2.notna() & o3.notna() & c3.notna() & atr_ok
    b1 = (c3 - o3) > 0
    b2 = (c2 - o2) > 0
    b3 = (f["c"] - f["o"]) > 0
    s1 = (c3 - o3) < 0
    s2 = (c2 - o2) < 0
    s3 = (f["c"] - f["o"]) < 0
    soldiers = (
        three_ok & b1 & b2 & b3
        & ((c2 - o2) >= SOLDIERS_BODY_ATR * f["safe_atr"])
        & ((f["c"] - f["o"]) >= SOLDIERS_BODY_ATR * f["safe_atr"])
        & (c2 > c3) & (f["c"] > c2)
        & (o2 > o3) & (o2 < c3) & (f["o"] > o2) & (f["o"] < c2)
        & ((f["h"] - f["c"]) <= 0.3 * f["safe_rng"])
    )
    crows = (
        three_ok & s1 & s2 & s3
        & ((o3 - c3) >= SOLDIERS_BODY_ATR * f["safe_atr"])
        & ((o2 - c2) >= SOLDIERS_BODY_ATR * f["safe_atr"])
        & (c2 < c3) & (f["c"] < c2)
        & (o2 < o3) & (o2 > c3) & (f["o"] < o2) & (f["o"] > c2)
        & ((f["c"] - f["l"]) <= 0.3 * f["safe_rng"])
    )
    # Morning/evening star: 3-bar with middle small body. Crypto gaps rare so
    # gap requirement relaxed to star body below/above neighbours' closes.
    mid_body_r = (c2 - o2).abs() / ((f["h"].shift(1) - f["l"].shift(1)).clip(lower=RANGE_EPS))
    mid_small = mid_body_r <= 0.35
    morning_star = (
        three_ok & f["downtrend"] & ((c3 - o3) < 0) & mid_small & ((f["c"] - f["o"]) > 0)
        & (c2 < c3) & (f["c"] > (o3 + c3) / 2.0)
    )
    evening_star = (
        three_ok & f["uptrend"] & ((c3 - o3) > 0) & mid_small & ((f["c"] - f["o"]) < 0)
        & (c2 > c3) & (f["c"] < (o3 + c3) / 2.0)
    )

    tol = TWEEZER_TOL_ATR * f["safe_atr"]
    # Equal highs/lows within tolerance, with confirming close direction.
    tweezer_top = (
        has_prev & atr_ok & ((f["h"] - f["prev_h"]).abs() <= tol)
        & (f["uptrend"]) & (f["c"] < c2)
    )
    tweezer_bottom = (
        has_prev & atr_ok & ((f["l"] - f["prev_l"]).abs() <= tol)
        & (f["downtrend"]) & (f["c"] > c2)
    )
    inside_bar = has_prev & (f["h"] <= f["prev_h"]) & (f["l"] >= f["prev_l"])
    outside_bar = has_prev & (f["h"] > f["prev_h"]) & (f["l"] < f["prev_l"])

    out = pd.DataFrame(
        {
            "cdl_doji": doji,
            "cdl_dragonfly_doji": dragonfly,
            "cdl_gravestone_doji": gravestone,
            "cdl_longlegged_doji": longlegged,
            "cdl_spinning_top": spinning,
            "cdl_marubozu_bull": marubozu_bull,
            "cdl_marubozu_bear": marubozu_bear,
            "cdl_hammer": hammer,
            "cdl_hanging_man": hanging_man,
            "cdl_inverted_hammer": inverted_hammer,
            "cdl_shooting_star": shooting_star,
            "cdl_pinbar_bull": pinbar_bull,
            "cdl_pinbar_bear": pinbar_bear,
            "cdl_engulfing_bull": engulf_bull,
            "cdl_engulfing_bear": engulf_bear,
            "cdl_harami_bull": harami_bull,
            "cdl_harami_bear": harami_bear,
            "cdl_piercing_line": piercing,
            "cdl_dark_cloud": dark_cloud,
            "cdl_morning_star": morning_star,
            "cdl_evening_star": evening_star,
            "cdl_three_white_soldiers": soldiers,
            "cdl_three_black_crows": crows,
            "cdl_tweezer_top": tweezer_top,
            "cdl_tweezer_bottom": tweezer_bottom,
            "cdl_inside_bar": inside_bar,
            "cdl_outside_bar": outside_bar,
        },
        index=f.index,
    )
    return out.fillna(False)


# Traditionally implied direction per pattern (+1 bullish, -1 bearish, 0 indecision).
DIRECTION = {
    "cdl_doji": 0,
    "cdl_dragonfly_doji": 1,
    "cdl_gravestone_doji": -1,
    "cdl_longlegged_doji": 0,
    "cdl_spinning_top": 0,
    "cdl_marubozu_bull": 1,
    "cdl_marubozu_bear": -1,
    "cdl_hammer": 1,
    "cdl_hanging_man": -1,
    "cdl_inverted_hammer": 1,
    "cdl_shooting_star": -1,
    "cdl_pinbar_bull": 1,
    "cdl_pinbar_bear": -1,
    "cdl_engulfing_bull": 1,
    "cdl_engulfing_bear": -1,
    "cdl_harami_bull": 1,
    "cdl_harami_bear": -1,
    "cdl_piercing_line": 1,
    "cdl_dark_cloud": -1,
    "cdl_morning_star": 1,
    "cdl_evening_star": -1,
    "cdl_three_white_soldiers": 1,
    "cdl_three_black_crows": -1,
    "cdl_tweezer_top": -1,
    "cdl_tweezer_bottom": 1,
    "cdl_inside_bar": 0,
    "cdl_outside_bar": 0,
}


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    """Float features, same index as bars."""
    f = _frame(bars)
    pats = _patterns(f)
    body_atr = f["body"] / f["safe_atr"]
    out = pd.DataFrame(index=bars.index)
    out["cdl_body_range"] = (f["body"] / f["safe_rng"]).where(f["rng"] > 0, 0.0)
    out["cdl_body_abs_range"] = (f["abs_body"] / f["safe_rng"]).where(f["rng"] > 0, 0.0)
    out["cdl_upper_wick_ratio"] = (f["upper"] / f["safe_rng"]).where(f["rng"] > 0, 0.0)
    out["cdl_lower_wick_ratio"] = (f["lower"] / f["safe_rng"]).where(f["rng"] > 0, 0.0)
    out["cdl_body_atr"] = body_atr.where(f["atr"].notna(), np.nan)
    out["cdl_abs_body_atr"] = (f["abs_body"] / f["safe_atr"]).where(f["atr"].notna(), np.nan)
    out["cdl_range_atr"] = (f["rng"] / f["safe_atr"]).where(f["atr"].notna(), np.nan)
    out["cdl_clv"] = f["clv"]
    out["cdl_gap_atr"] = ((f["o"] - f["prev_c"]) / f["safe_atr"]).where(
        f["prev_c"].notna() & f["atr"].notna(), np.nan
    )
    out["cdl_body_sum_3_atr"] = (
        f["body"].rolling(3).sum() / f["safe_atr"]
    ).where(f["atr"].notna(), np.nan)
    for col in pats.columns:
        out[col] = pats[col].astype(float)
    return out.astype(float)


def events(bars: pd.DataFrame) -> pd.DataFrame:
    """int8 directional hypotheses in {-1, 0, 1}."""
    pats = _patterns(_frame(bars))
    out = pd.DataFrame(index=bars.index)
    for col, d in DIRECTION.items():
        out[col] = (pats[col].astype(np.int8) * np.int8(d)).astype(np.int8)
    return out
