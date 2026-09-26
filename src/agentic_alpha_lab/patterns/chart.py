"""W2 classical chart patterns (pattern_lab_r1).

Textbook-first definitions, fixed before any event study. All rows causal:
row t uses only bars[:t+1]. Pivots become visible only at their confirmation
bar (fractal: pivot bar i visible at i+k; zigzag: leg confirmed only on a
threshold reversal bar).

Recorded constants (ATR units unless noted):
  ATR_LEN=14 (Wilder), FRACTAL_K_SMALL=2, FRACTAL_K_LARGE=5,
  ZIGZAG_ATR_MULT=3.0, TOL_EQUAL_ATR=0.40, BREAK_TOL_ATR=0.10,
  RETEST_TOL_ATR=0.20, EXPIRY_BARS=40, LOOKBACK_STRUCT=120,
  HEAD_MIN_ATR=0.75, SHOULDER_TOL_ATR=0.60, TIME_SYM=(0.33, 3.0),
  TRI_LOOKBACK=50, TRI_FLAT_ATR=0.75, TRI_RISE_ATR=0.25,
  RECT_LOOKBACK=40, RECT_H_MIN_ATR=0.50, RECT_H_MAX_ATR=5.0,
  FLAG_POLE_LOOKBACK=20, FLAG_CONSOL=10, FLAG_POLE_MIN_ATR=2.0,
  FLAG_RANGE_MAX_ATR=1.5, WEDGE_LOOKBACK=60, SR_N_LEVELS=8,
  RETEST_WINDOW=10, DON_N1=20, DON_N2=55.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ATR_LEN = 14
FRACTAL_K_SMALL = 2
FRACTAL_K_LARGE = 5
ZIGZAG_ATR_MULT = 3.0
TOL_EQUAL_ATR = 0.40
BREAK_TOL_ATR = 0.10
RETEST_TOL_ATR = 0.20
EXPIRY_BARS = 40
LOOKBACK_STRUCT = 120
HEAD_MIN_ATR = 0.75
SHOULDER_TOL_ATR = 0.60
TIME_SYM_LO = 0.33
TIME_SYM_HI = 3.0
TRI_LOOKBACK = 50
TRI_FLAT_ATR = 0.75
TRI_RISE_ATR = 0.25
RECT_LOOKBACK = 40
RECT_H_MIN_ATR = 0.50
RECT_H_MAX_ATR = 5.0
FLAG_POLE_LOOKBACK = 20
FLAG_CONSOL = 10
FLAG_POLE_MIN_ATR = 2.0
FLAG_RANGE_MAX_ATR = 1.5
WEDGE_LOOKBACK = 60
SR_N_LEVELS = 8
RETEST_WINDOW = 10
DON_N1 = 20
DON_N2 = 55

EVENT_COLS = [
    "chp_double_top", "chp_double_bottom",
    "chp_triple_top", "chp_triple_bottom",
    "chp_head_shoulders", "chp_inv_head_shoulders",
    "chp_asc_triangle", "chp_desc_triangle", "chp_sym_triangle",
    "chp_rectangle_break",
    "chp_bull_flag", "chp_bear_flag",
    "chp_rising_wedge", "chp_falling_wedge",
    "chp_sr_break", "chp_sr_retest",
    "chp_donchian20_break", "chp_donchian55_break",
]

COMPUTE_COLS = [
    "chp_atr",
    "chp_dist_piv_high_small_atr", "chp_dist_piv_low_small_atr",
    "chp_dist_piv_high_large_atr", "chp_dist_piv_low_large_atr",
    "chp_dist_don20_up_atr", "chp_dist_don20_dn_atr",
    "chp_dist_don55_up_atr", "chp_dist_don55_dn_atr",
    "chp_bars_since_piv_high_large", "chp_bars_since_piv_low_large",
    "chp_bars_since_piv_small",
    "chp_range_height_atr",
    "chp_hh_count_3", "chp_ll_count_3",
    "chp_dist_neckline_atr",
]


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = ATR_LEN) -> np.ndarray:
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    return pd.Series(tr).ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean().to_numpy()


def _fractal(high: np.ndarray, low: np.ndarray, k: int):
    """Causal-delay fractal pivots. Pivot at i visible only at confirmation i+k."""
    n = len(high)
    hs = pd.Series(high)
    ls = pd.Series(low)
    is_h = pd.Series(np.ones(n, dtype=bool))
    is_l = pd.Series(np.ones(n, dtype=bool))
    for j in range(1, k + 1):
        is_h &= (hs >= hs.shift(j)) & (hs >= hs.shift(-j))
        is_l &= (ls <= ls.shift(j)) & (ls <= ls.shift(-j))
    is_h = is_h.fillna(False).to_numpy()
    is_l = is_l.fillna(False).to_numpy()
    # dedup: within k bars keep the most extreme
    hcand = list(np.where(is_h)[0])
    lcand = list(np.where(is_l)[0])
    hidx: list[int] = []
    for i in hcand:
        if hidx and i - hidx[-1] <= k:
            if high[i] > high[hidx[-1]]:
                hidx[-1] = i
        else:
            hidx.append(i)
    lidx: list[int] = []
    for i in lcand:
        if lidx and i - lidx[-1] <= k:
            if low[i] < low[lidx[-1]]:
                lidx[-1] = i
        else:
            lidx.append(i)
    hidx = np.array(hidx, dtype=np.int64)
    lidx = np.array(lidx, dtype=np.int64)
    hpx = high[hidx] if len(hidx) else np.zeros(0)
    lpx = low[lidx] if len(lidx) else np.zeros(0)
    hconf = hidx + k
    lconf = lidx + k
    hconf = hconf[hconf < n]
    hidx_c = hidx[: len(hconf)]
    hpx_c = hpx[: len(hconf)]
    lconf = lconf[lconf < n]
    lidx_c = lidx[: len(lconf)]
    lpx_c = lpx[: len(lconf)]

    def _ffill_unused():
        return None

    # build ffill series: value appears at confirmation bar, then held
    def _build(conf, idx_c, px_c):
        p = np.full(n, np.nan)
        ii = np.full(n, np.nan)
        flag = np.zeros(n, dtype=np.int8)
        # assign at confirmation bars (last wins on collision)
        for c, pi, pv in zip(conf, idx_c, px_c):
            p[c] = pv
            ii[c] = pi
            flag[c] = 1
        # ffill
        last_p = np.nan
        last_i = np.nan
        for t in range(n):
            if not np.isnan(p[t]):
                last_p = p[t]
                last_i = ii[t]
            else:
                p[t] = last_p
                ii[t] = last_i
        return p, ii, flag

    hp, hi, hflag = _build(hconf, hidx_c, hpx_c)
    lp, li, lflag = _build(lconf, lidx_c, lpx_c)
    return {
        "hidx": hidx_c, "hpx": hpx_c, "hconf": hconf,
        "lidx": lidx_c, "lpx": lpx_c, "lconf": lconf,
        "hp": hp, "hi": hi, "lp": lp, "li": li,
        "hflag": hflag, "lflag": lflag,
    }


def _zigzag(high: np.ndarray, low: np.ndarray, close: np.ndarray, atr: np.ndarray,
            mult: float = ZIGZAG_ATR_MULT):
    """Online ATR-threshold zigzag. Last leg unconfirmed; pivots listed at confirmation bar."""
    n = len(close)
    piv_idx: list[int] = []
    piv_px: list[float] = []
    piv_side: list[int] = []  # +1 high, -1 low
    piv_conf: list[int] = []
    if n == 0:
        return {"idx": np.zeros(0, dtype=np.int64), "px": np.zeros(0),
                "side": np.zeros(0, dtype=np.int8), "conf": np.zeros(0, dtype=np.int64)}
    direction = 0
    ext_idx = 0
    ext_px = close[0]
    for t in range(1, n):
        a = atr[t]
        if not np.isfinite(a) or a <= 0:
            continue
        th = mult * a
        if direction >= 0:
            if high[t] >= ext_px:
                ext_px = float(high[t])
                ext_idx = t
            if low[t] <= ext_px - th:
                piv_idx.append(ext_idx)
                piv_px.append(ext_px)
                piv_side.append(1)
                piv_conf.append(t)
                direction = -1
                ext_px = float(low[t])
                ext_idx = t
        if direction <= 0:
            # evaluate down leg (also runs right after a flip using same bar)
            if direction == -1:
                if low[t] <= ext_px:
                    ext_px = float(low[t])
                    ext_idx = t
                if high[t] >= ext_px + th:
                    piv_idx.append(ext_idx)
                    piv_px.append(ext_px)
                    piv_side.append(-1)
                    piv_conf.append(t)
                    direction = 1
                    ext_px = float(high[t])
                    ext_idx = t
    return {"idx": np.array(piv_idx, dtype=np.int64), "px": np.array(piv_px),
            "side": np.array(piv_side, dtype=np.int8),
            "conf": np.array(piv_conf, dtype=np.int64)}


def _prior_extremes(x: np.ndarray, n: int, how: str) -> np.ndarray:
    s = pd.Series(x)
    if how == "max":
        return s.rolling(n, min_periods=n).max().shift(1).to_numpy()
    return s.rolling(n, min_periods=n).min().shift(1).to_numpy()


def _slope(y: np.ndarray) -> float:
    y = np.asarray(y, float)
    m = len(y)
    if m < 2 or not np.all(np.isfinite(y)):
        return 0.0
    x = np.arange(m, dtype=float)
    sx = x.mean()
    denom = ((x - sx) ** 2).sum()
    if denom == 0:
        return 0.0
    return float(((x - sx) * (y - y.mean())).sum() / denom)


def _detect(bars: pd.DataFrame):
    n = len(bars)
    high = bars["high"].to_numpy(float)
    low = bars["low"].to_numpy(float)
    close = bars["close"].to_numpy(float)
    atr = _atr(high, low, close)
    small = _fractal(high, low, FRACTAL_K_SMALL)
    large = _fractal(high, low, FRACTAL_K_LARGE)
    _zz = _zigzag(high, low, close, atr)

    don20h = _prior_extremes(high, DON_N1, "max")
    don20l = _prior_extremes(low, DON_N1, "min")
    don55h = _prior_extremes(high, DON_N2, "max")
    don55l = _prior_extremes(low, DON_N2, "min")
    recth = _prior_extremes(high, RECT_LOOKBACK, "max")
    rectl = _prior_extremes(low, RECT_LOOKBACK, "min")

    ev = {c: np.zeros(n, dtype=np.int8) for c in EVENT_COLS}
    neck = np.full(n, np.nan)

    # ---- vectorized breakouts: donchian / rectangle / SR ----
    for t in range(n):
        a = atr[t]
        if not np.isfinite(a) or a <= 0:
            continue
        tol = BREAK_TOL_ATR * a
        c = close[t]
        pc = close[t - 1] if t > 0 else np.nan
        if np.isfinite(don20h[t]) and np.isfinite(pc):
            if pc <= don20h[t] + tol and c > don20h[t] + tol:
                ev["chp_donchian20_break"][t] = 1
            elif pc >= don20l[t] - tol and c < don20l[t] - tol:
                ev["chp_donchian20_break"][t] = -1
        if np.isfinite(don55h[t]) and np.isfinite(pc):
            if pc <= don55h[t] + tol and c > don55h[t] + tol:
                ev["chp_donchian55_break"][t] = 1
            elif pc >= don55l[t] - tol and c < don55l[t] - tol:
                ev["chp_donchian55_break"][t] = -1
        if np.isfinite(recth[t]) and np.isfinite(rectl[t]) and np.isfinite(pc):
            hgt = (recth[t] - rectl[t]) / a
            if RECT_H_MIN_ATR <= hgt <= RECT_H_MAX_ATR:
                if pc <= recth[t] + tol and c > recth[t] + tol:
                    ev["chp_rectangle_break"][t] = 1
                elif pc >= rectl[t] - tol and c < rectl[t] - tol:
                    ev["chp_rectangle_break"][t] = -1
    # SR levels from last confirmed large pivots (resistance/support known at t-1)
    sr_break_lvl = np.full(n, np.nan)
    sr_break_dir = np.zeros(n, dtype=np.int8)
    for t in range(n):
        a = atr[t]
        if not np.isfinite(a) or a <= 0 or t == 0:
            continue
        tol = BREAK_TOL_ATR * a
        c = close[t]
        pc = close[t - 1]
        if not np.isfinite(pc):
            continue
        res = large["hp"][t - 1]
        sup = large["lp"][t - 1]
        fired = 0
        lvl = np.nan
        if np.isfinite(res) and pc <= res + tol and c > res + tol:
            fired = 1
            lvl = res
        elif np.isfinite(sup) and pc >= sup - tol and c < sup - tol:
            fired = -1
            lvl = sup
        if fired:
            ev["chp_sr_break"][t] = np.int8(fired)
            sr_break_lvl[t] = lvl
            sr_break_dir[t] = np.int8(fired)
    # SR retest: touch of broken level within RETEST_WINDOW, holding -> continuation
    for tb in np.where(sr_break_dir != 0)[0]:
        d = int(sr_break_dir[tb])
        lvl = sr_break_lvl[tb]
        if not np.isfinite(lvl):
            continue
        for t in range(tb + 1, min(n, tb + 1 + RETEST_WINDOW)):
            a = atr[t]
            if not np.isfinite(a) or a <= 0:
                continue
            tol = RETEST_TOL_ATR * a
            if d == 1:
                if abs(low[t] - lvl) <= tol and close[t] > lvl and ev["chp_sr_retest"][t] == 0:
                    # first retest only
                    if not np.any(ev["chp_sr_retest"][tb + 1:t] != 0):
                        ev["chp_sr_retest"][t] = 1
                    break
            else:
                if abs(high[t] - lvl) <= tol and close[t] < lvl and ev["chp_sr_retest"][t] == 0:
                    if not np.any(ev["chp_sr_retest"][tb + 1:t] != 0):
                        ev["chp_sr_retest"][t] = -1
                    break

    # ---- multi-pivot structures: per-bar loop over available pivots ----
    # available pivot lists in confirmation order
    for scale_key, sc in (("large", large), ("small", small)):
        hidx, hpx, hconf = sc["hidx"], sc["hpx"], sc["hconf"]
        lidx, lpx, lconf = sc["lidx"], sc["lpx"], sc["lconf"]
        # merge into confirmation-ordered streams
        order_h = np.argsort(hconf, kind="stable") if len(hconf) else np.zeros(0, dtype=np.int64)
        order_l = np.argsort(lconf, kind="stable") if len(lconf) else np.zeros(0, dtype=np.int64)
        hconf_s = hconf[order_h]
        hidx_s = hidx[order_h]
        hpx_s = hpx[order_h]
        lconf_s = lconf[order_l]
        lidx_s = lidx[order_l]
        lpx_s = lpx[order_l]
        avail_h_i: list[int] = []
        avail_h_p: list[float] = []
        avail_h_c: list[int] = []
        avail_l_i: list[int] = []
        avail_l_p: list[float] = []
        avail_l_c: list[int] = []
        ph = 0
        pl = 0
        for t in range(n):
            while ph < len(hconf_s) and hconf_s[ph] <= t:
                avail_h_i.append(int(hidx_s[ph]))
                avail_h_p.append(float(hpx_s[ph]))
                avail_h_c.append(int(hconf_s[ph]))
                ph += 1
            while pl < len(lconf_s) and lconf_s[pl] <= t:
                avail_l_i.append(int(lidx_s[pl]))
                avail_l_p.append(float(lpx_s[pl]))
                avail_l_c.append(int(lconf_s[pl]))
                pl += 1
            a = atr[t]
            if not np.isfinite(a) or a <= 0 or t == 0:
                continue
            tol_eq = TOL_EQUAL_ATR * a
            tol_br = BREAK_TOL_ATR * a
            c = close[t]
            pc = close[t - 1]
            if len(avail_h_i) >= 2 and len(avail_l_i) >= 1:
                h1i, h1p, h1c = avail_h_i[-2], avail_h_p[-2], avail_h_c[-2]
                h2i, h2p, h2c = avail_h_i[-1], avail_h_p[-1], avail_h_c[-1]
                if (t - h2c <= EXPIRY_BARS and h2i - h1i <= LOOKBACK_STRUCT
                        and h2i - h1i > 0 and abs(h2p - h1p) <= tol_eq):
                    seg = low[h1i + 1:h2i] if h2i - h1i > 1 else np.array([])
                    if len(seg):
                        nck = float(np.min(seg))
                        if scale_key == "large" and np.isnan(neck[t]):
                            neck[t] = nck
                        elif scale_key == "small" and np.isnan(neck[t]):
                            neck[t] = nck
                        if pc >= nck - tol_br and c < nck - tol_br:
                            if ev["chp_double_top"][t] == 0:
                                ev["chp_double_top"][t] = -1
                # double bottom mirror
                if len(avail_l_i) >= 2:
                    l1i, l1p, l1c = avail_l_i[-2], avail_l_p[-2], avail_l_c[-2]
                    l2i, l2p, l2c = avail_l_i[-1], avail_l_p[-1], avail_l_c[-1]
                    if (t - l2c <= EXPIRY_BARS and l2i - l1i <= LOOKBACK_STRUCT
                            and l2i - l1i > 0 and abs(l2p - l1p) <= tol_eq):
                        seg = high[l1i + 1:l2i] if l2i - l1i > 1 else np.array([])
                        if len(seg):
                            nck = float(np.max(seg))
                            if np.isnan(neck[t]):
                                neck[t] = nck
                            if pc <= nck + tol_br and c > nck + tol_br:
                                if ev["chp_double_bottom"][t] == 0:
                                    ev["chp_double_bottom"][t] = 1
            if len(avail_h_i) >= 3:
                h1p, h2p, h3p = avail_h_p[-3], avail_h_p[-2], avail_h_p[-1]
                h1i, h2i, h3i = avail_h_i[-3], avail_h_i[-2], avail_h_i[-1]
                h3c = avail_h_c[-1]
                if (t - h3c <= EXPIRY_BARS and h3i - h1i <= LOOKBACK_STRUCT
                        and max(h1p, h2p, h3p) - min(h1p, h2p, h3p) <= tol_eq):
                    seg = low[h1i + 1:h3i] if h3i - h1i > 1 else np.array([])
                    if len(seg):
                        nck = float(np.min(seg))
                        if np.isnan(neck[t]):
                            neck[t] = nck
                        if pc >= nck - tol_br and c < nck - tol_br:
                            if ev["chp_triple_top"][t] == 0:
                                ev["chp_triple_top"][t] = -1
            if len(avail_l_i) >= 3:
                l1p, l2p, l3p = avail_l_p[-3], avail_l_p[-2], avail_l_p[-1]
                l1i, l2i, l3i = avail_l_i[-3], avail_l_i[-2], avail_l_i[-1]
                l3c = avail_l_c[-1]
                if (t - l3c <= EXPIRY_BARS and l3i - l1i <= LOOKBACK_STRUCT
                        and max(l1p, l2p, l3p) - min(l1p, l2p, l3p) <= tol_eq):
                    seg = high[l1i + 1:l3i] if l3i - l1i > 1 else np.array([])
                    if len(seg):
                        nck = float(np.max(seg))
                        if np.isnan(neck[t]):
                            neck[t] = nck
                        if pc <= nck + tol_br and c > nck + tol_br:
                            if ev["chp_triple_bottom"][t] == 0:
                                ev["chp_triple_bottom"][t] = 1
            if len(avail_h_i) >= 3 and len(avail_l_i) >= 2:
                h1p, h2p, h3p = avail_h_p[-3], avail_h_p[-2], avail_h_p[-1]
                h1i, h2i, h3i = avail_h_i[-3], avail_h_i[-2], avail_h_i[-1]
                h3c = avail_h_c[-1]
                w1 = h2i - h1i
                w2 = h3i - h2i
                if (w1 > 0 and w2 > 0 and t - h3c <= EXPIRY_BARS and h3i - h1i <= LOOKBACK_STRUCT
                        and h2p > h1p and h2p > h3p
                        and (h2p - h1p) >= HEAD_MIN_ATR * a and (h2p - h3p) >= HEAD_MIN_ATR * a
                        and abs(h3p - h1p) <= SHOULDER_TOL_ATR * a
                        and TIME_SYM_LO <= w1 / w2 <= TIME_SYM_HI):
                    s1 = low[h1i + 1:h2i] if w1 > 1 else np.array([])
                    s2 = low[h2i + 1:h3i] if w2 > 1 else np.array([])
                    if len(s1) and len(s2):
                        nck = float(min(np.min(s1), np.min(s2)))
                        if np.isnan(neck[t]):
                            neck[t] = nck
                        if pc >= nck - tol_br and c < nck - tol_br:
                            if ev["chp_head_shoulders"][t] == 0:
                                ev["chp_head_shoulders"][t] = -1
            if len(avail_l_i) >= 3 and len(avail_h_i) >= 2:
                l1p, l2p, l3p = avail_l_p[-3], avail_l_p[-2], avail_l_p[-1]
                l1i, l2i, l3i = avail_l_i[-3], avail_l_i[-2], avail_l_i[-1]
                l3c = avail_l_c[-1]
                w1 = l2i - l1i
                w2 = l3i - l2i
                if (w1 > 0 and w2 > 0 and t - l3c <= EXPIRY_BARS and l3i - l1i <= LOOKBACK_STRUCT
                        and l2p < l1p and l2p < l3p
                        and (l1p - l2p) >= HEAD_MIN_ATR * a and (l3p - l2p) >= HEAD_MIN_ATR * a
                        and abs(l3p - l1p) <= SHOULDER_TOL_ATR * a
                        and TIME_SYM_LO <= w1 / w2 <= TIME_SYM_HI):
                    s1 = high[l1i + 1:l2i] if w1 > 1 else np.array([])
                    s2 = high[l2i + 1:l3i] if w2 > 1 else np.array([])
                    if len(s1) and len(s2):
                        nck = float(max(np.max(s1), np.max(s2)))
                        if np.isnan(neck[t]):
                            neck[t] = nck
                        if pc <= nck + tol_br and c > nck + tol_br:
                            if ev["chp_inv_head_shoulders"][t] == 0:
                                ev["chp_inv_head_shoulders"][t] = 1
            if scale_key == "large" and len(avail_h_i) >= 2 and len(avail_l_i) >= 2:
                # triangles on the large scale: two-touch res/sup + breakout
                h1i, h1p, h1c = avail_h_i[-2], avail_h_p[-2], avail_h_c[-2]
                h2i, h2p, h2c = avail_h_i[-1], avail_h_p[-1], avail_h_c[-1]
                l1i, l1p, l1c = avail_l_i[-2], avail_l_p[-2], avail_l_c[-2]
                l2i, l2p, l2c = avail_l_i[-1], avail_l_p[-1], avail_l_c[-1]
                if (t - max(h2c, l2c) <= EXPIRY_BARS and h2i - h1i <= LOOKBACK_STRUCT
                        and l2i - l1i <= LOOKBACK_STRUCT and h2i < t and l2i < t):
                    res = max(h1p, h2p)
                    sup = min(l1p, l2p)
                    up = pc <= res + tol_br and c > res + tol_br
                    dn = pc >= sup - tol_br and c < sup - tol_br
                    if up or dn:
                        flat_h = abs(h2p - h1p) <= TRI_FLAT_ATR * a
                        flat_l = abs(l2p - l1p) <= TRI_FLAT_ATR * a
                        rising_l = (l2p - l1p) >= TRI_RISE_ATR * a
                        falling_h = (h1p - h2p) >= TRI_RISE_ATR * a
                        if flat_h and rising_l:
                            ev["chp_asc_triangle"][t] = np.int8(1 if up else -1)
                        if flat_l and falling_h:
                            ev["chp_desc_triangle"][t] = np.int8(1 if up else -1)
                        if falling_h and rising_l:
                            ev["chp_sym_triangle"][t] = np.int8(1 if up else -1)
    # ffill neckline across bars (last structure neck held; causal ffill)
    last = np.nan
    for t in range(n):
        if np.isfinite(neck[t]):
            last = neck[t]
        else:
            neck[t] = last

    # ---- flags + wedges evaluated at their own breakout bars ----
    # flags need only pole+consolidation bars; wedges need a full window
    for t in range(FLAG_POLE_LOOKBACK + FLAG_CONSOL + 1, n):
        a = atr[t]
        if not np.isfinite(a) or a <= 0:
            continue
        tol_br = BREAK_TOL_ATR * a
        c = close[t]
        pc = close[t - 1]
        # flags
        ch = float(np.max(high[t - FLAG_CONSOL:t]))
        cl = float(np.min(low[t - FLAG_CONSOL:t]))
        if (ch - cl) / a <= FLAG_RANGE_MAX_ATR and t - FLAG_CONSOL - FLAG_POLE_LOOKBACK >= 0:
            pole = (close[t - FLAG_CONSOL] - close[t - FLAG_CONSOL - FLAG_POLE_LOOKBACK]) / a
            if pole >= FLAG_POLE_MIN_ATR and pc <= ch + tol_br and c > ch + tol_br:
                ev["chp_bull_flag"][t] = 1
            if pole <= -FLAG_POLE_MIN_ATR and pc >= cl - tol_br and c < cl - tol_br:
                ev["chp_bear_flag"][t] = -1
    for t in range(WEDGE_LOOKBACK + 1, n):
        a = atr[t]
        if not np.isfinite(a) or a <= 0:
            continue
        tol_br = BREAK_TOL_ATR * a
        c = close[t]
        pc = close[t - 1]
        # wedges (bar-level slopes over window)
        wh = high[t - WEDGE_LOOKBACK:t]
        wl = low[t - WEDGE_LOOKBACK:t]
        if np.all(np.isfinite(wh)) and np.all(np.isfinite(wl)):
            sh = _slope(wh)
            sl = _slope(wl)
            hgt = (float(np.max(wh)) - float(np.min(wl))) / a
            if 0.5 <= hgt <= 8.0:
                sup10 = float(np.min(low[t - 10:t])) if t >= 10 else np.nan
                res10 = float(np.max(high[t - 10:t])) if t >= 10 else np.nan
                if sh > 0 and sl > sh and np.isfinite(sup10):
                    if pc >= sup10 - tol_br and c < sup10 - tol_br:
                        ev["chp_rising_wedge"][t] = -1
                if sl < 0 and sh < sl and np.isfinite(res10):
                    if pc <= res10 + tol_br and c > res10 + tol_br:
                        ev["chp_falling_wedge"][t] = 1

    events = pd.DataFrame({k: v.astype(np.int8) for k, v in ev.items()}, index=bars.index)
    aux = {
        "atr": atr, "small": small, "large": large,
        "don20h": don20h, "don20l": don20l, "don55h": don55h, "don55l": don55l,
        "recth": recth, "rectl": rectl, "neck": neck,
    }
    return events, aux


def _trend_counts(n: int, conf: np.ndarray, px: np.ndarray, direction: int) -> np.ndarray:
    """Count of directed steps among last 3 comparisons of distinct pivots available at t."""
    out = np.full(n, np.nan)
    if len(conf) == 0:
        return out
    order = np.argsort(conf, kind="stable")
    cs = conf[order]
    vs = px[order]
    p = 0
    buf: list[float] = []
    for t in range(n):
        while p < len(cs) and cs[p] <= t:
            buf.append(float(vs[p]))
            p += 1
        if len(buf) >= 4:
            last4 = buf[-4:]
            cnt = 0
            for i in range(1, 4):
                if direction > 0 and last4[i] > last4[i - 1]:
                    cnt += 1
                if direction < 0 and last4[i] < last4[i - 1]:
                    cnt += 1
            out[t] = float(cnt)
        elif len(buf) >= 2:
            # partial warm-up: count over available comparisons
            cnt = 0
            for i in range(1, len(buf)):
                if direction > 0 and buf[i] > buf[i - 1]:
                    cnt += 1
                if direction < 0 and buf[i] < buf[i - 1]:
                    cnt += 1
            out[t] = float(cnt)
    return out


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    n = len(bars)
    close = bars["close"].to_numpy(float)
    _events, aux = _detect(bars)
    atr = aux["atr"]
    small = aux["small"]
    large = aux["large"]
    don20h, don20l = aux["don20h"], aux["don20l"]
    don55h, don55l = aux["don55h"], aux["don55l"]
    neck = aux["neck"]
    with np.errstate(divide="ignore", invalid="ignore"):
        f = {
            "chp_atr": atr.astype(float),
            "chp_dist_piv_high_small_atr": (close - small["hp"]) / atr,
            "chp_dist_piv_low_small_atr": (close - small["lp"]) / atr,
            "chp_dist_piv_high_large_atr": (close - large["hp"]) / atr,
            "chp_dist_piv_low_large_atr": (close - large["lp"]) / atr,
            "chp_dist_don20_up_atr": (close - don20h) / atr,
            "chp_dist_don20_dn_atr": (close - don20l) / atr,
            "chp_dist_don55_up_atr": (close - don55h) / atr,
            "chp_dist_don55_dn_atr": (close - don55l) / atr,
            "chp_bars_since_piv_high_large": (np.arange(n) - large["hi"]).astype(float),
            "chp_bars_since_piv_low_large": (np.arange(n) - large["li"]).astype(float),
            "chp_range_height_atr": (don55h - don55l) / atr if False else ((pd.Series(don55h) - pd.Series(don55l)).to_numpy() / atr),
            "chp_hh_count_3": _trend_counts(n, large["hconf"], large["hpx"], +1),
            "chp_ll_count_3": _trend_counts(n, large["lconf"], large["lpx"], -1),
            "chp_dist_neckline_atr": (close - neck) / atr,
        }
        # bars since small = min(high, low) recency
        bs = np.minimum(
            np.where(np.isfinite(small["hi"]), np.arange(n) - small["hi"], np.inf),
            np.where(np.isfinite(small["li"]), np.arange(n) - small["li"], np.inf),
        )
        bs = np.where(np.isfinite(bs), bs, np.nan)
        f["chp_bars_since_piv_small"] = bs.astype(float)
        # range height from rect window (fallback to don55 if needed)
        rh = aux["recth"]
        rl = aux["rectl"]
        rng = (pd.Series(rh) - pd.Series(rl)).to_numpy() / atr
        dh = (pd.Series(don55h) - pd.Series(don55l)).to_numpy() / atr
        f["chp_range_height_atr"] = np.where(np.isfinite(rng), rng, dh)
    out = pd.DataFrame({k: np.asarray(v, dtype=float) for k, v in f.items()}, index=bars.index)
    return out[COMPUTE_COLS]


def events(bars: pd.DataFrame) -> pd.DataFrame:
    ev, _aux = _detect(bars)
    return ev[EVENT_COLS]
