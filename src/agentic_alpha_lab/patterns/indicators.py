"""W3 technical-indicator features (pattern_lab_r1).

Textbook definitions, fixed first, causal (row t uses only bars[:t+1]).
Scale-free: oscillators kept in native units, trending distances divided by ATR
(or price for ATR itself). Recursive indicators are forward-only (Wilder/EMA,
no backfill).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PREFIX = "ind_"
_FUND_CACHE: pd.DataFrame | None = None


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _rma(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    g = d.clip(lower=0)
    l = (-d).clip(lower=0)
    ag = _rma(g, n)
    al = _rma(l, n)
    rs = ag / al
    rsi = 100 - 100 / (1 + rs)
    # flat history -> RSI 50 (ag==al==0); pure gains -> 100
    flat = (ag == 0) & (al == 0)
    rsi = rsi.mask(flat, 50.0)
    return rsi


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return _rma(tr, n)


def _load_funding_cached() -> pd.DataFrame | None:
    global _FUND_CACHE
    if _FUND_CACHE is not None:
        return _FUND_CACHE
    try:
        from .common import load_funding

        # Full history: rows are joined as-of each bar close, so later funding
        # never reaches earlier bars; hiding it would starve opened-year features.
        f = load_funding(include_opened_year=True)
    except Exception:
        return None
    f = f.sort_values("fundingTime").reset_index(drop=True)
    f["m7d"] = f["fundingRate"].rolling(21, min_periods=1).mean()
    _FUND_CACHE = f
    return f


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 10, mult: float = 3.0):
    h = high.to_numpy(float)
    lo = low.to_numpy(float)
    c = close.to_numpy(float)
    hl2 = (h + lo) / 2.0
    atr = _atr(high, low, close, n).to_numpy(float)
    bu = hl2 + mult * atr
    bl = hl2 - mult * atr
    N = len(c)
    fu = np.full(N, np.nan)
    fl = np.full(N, np.nan)
    up = np.full(N, True)
    st = np.full(N, np.nan)
    start = int(np.where(~np.isnan(bu))[0][0]) if np.any(~np.isnan(bu)) else N
    if start >= N:
        return pd.Series(np.nan, index=close.index), pd.Series(np.nan, index=close.index)
    fu[start] = bu[start]
    fl[start] = bl[start]
    up[start] = True
    st[start] = fl[start]
    for t in range(start + 1, N):
        prev_fu, prev_fl = fu[t - 1], fl[t - 1]
        fu[t] = bu[t] if (bu[t] < prev_fu or c[t - 1] > prev_fu) else prev_fu
        fl[t] = bl[t] if (bl[t] > prev_fl or c[t - 1] < prev_fl) else prev_fl
        if up[t - 1]:
            if c[t] <= fl[t]:
                up[t] = False
                st[t] = fu[t]
            else:
                up[t] = True
                st[t] = fl[t]
        else:
            if c[t] >= fu[t]:
                up[t] = True
                st[t] = fl[t]
            else:
                up[t] = False
                st[t] = fu[t]
    state = pd.Series(np.where(np.isnan(st), np.nan, np.where(up, 1.0, -1.0)), index=close.index)
    line = pd.Series(st, index=close.index)
    return state, line


def _psar(high: pd.Series, low: pd.Series, close: pd.Series, step: float = 0.02, maxaf: float = 0.2):
    h = high.to_numpy(float)
    lo = low.to_numpy(float)
    N = len(close)
    sar = np.full(N, np.nan)
    bull = np.full(N, True)
    if N < 2:
        return pd.Series(sar, index=close.index), pd.Series(True, index=close.index)
    b = bool(close.iloc[1] >= close.iloc[0])
    bull[:] = b
    s = lo[0] if b else h[0]
    ep = h[0] if b else lo[0]
    af = step
    sar[0] = s
    for t in range(1, N):
        s = s + af * (ep - s)
        if bull[t - 1]:
            cap = lo[t - 1] if t < 2 else min(lo[t - 1], lo[t - 2])
            s = min(s, cap)
            if lo[t] < s:
                bull[t] = False
                s = ep
                ep = lo[t]
                af = step
            else:
                bull[t] = True
                if h[t] > ep:
                    ep = h[t]
                    af = min(af + step, maxaf)
        else:
            cap = h[t - 1] if t < 2 else max(h[t - 1], h[t - 2])
            s = max(s, cap)
            if h[t] > s:
                bull[t] = True
                s = ep
                ep = h[t]
                af = step
            else:
                bull[t] = False
                if lo[t] < ep:
                    ep = lo[t]
                    af = min(af + step, maxaf)
        sar[t] = s
    return (
        pd.Series(np.where(bull, 1.0, -1.0), index=close.index),
        pd.Series(sar, index=close.index),
    )


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    o = bars["open"].astype(float)
    h = bars["high"].astype(float)
    lo = bars["low"].astype(float)
    c = bars["close"].astype(float)
    v = bars["volume"].astype(float) if "volume" in bars else pd.Series(np.nan, index=idx)
    tb = bars["taker_buy_volume"].astype(float) if "taker_buy_volume" in bars else pd.Series(np.nan, index=idx)

    out: dict[str, pd.Series] = {}
    atr14 = _atr(h, lo, c, 14)
    out["ind_atr14_price"] = atr14 / c

    rsi14 = _rsi(c, 14)
    rsi7 = _rsi(c, 7)
    out["ind_rsi_14"] = rsi14
    out["ind_rsi_7"] = rsi7

    ll14 = lo.rolling(14, min_periods=14).min()
    hh14 = h.rolling(14, min_periods=14).max()
    rng14 = (hh14 - ll14).replace(0, np.nan)
    k14 = (c - ll14) / rng14 * 100
    out["ind_stoch_k_14"] = k14
    out["ind_stoch_d_3"] = k14.rolling(3, min_periods=3).mean()

    rmin = rsi14.rolling(14, min_periods=14).min()
    rmax = rsi14.rolling(14, min_periods=14).max()
    rrng = (rmax - rmin).replace(0, np.nan)
    srsi = (rsi14 - rmin) / rrng
    out["ind_stochrsi_14"] = srsi
    out["ind_stochrsi_d_3"] = srsi.rolling(3, min_periods=3).mean()

    e12 = _ema(c, 12)
    e26 = _ema(c, 26)
    macd = e12 - e26
    sig = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    hist = macd - sig
    out["ind_macd_line_atr"] = macd / atr14
    out["ind_macd_signal_atr"] = sig / atr14
    out["ind_macd_hist_atr"] = hist / atr14

    sma20 = c.rolling(20, min_periods=20).mean()
    std20 = c.rolling(20, min_periods=20).std(ddof=0)
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    bw = (upper - lower)
    pctb = (c - lower) / bw.replace(0, np.nan)
    pctb = pctb.mask(bw == 0, 0.5)  # flat line: price sits mid-band
    out["ind_bb_pctb_20"] = pctb
    out["ind_bb_bw_20"] = (upper - lower) / sma20

    ema20 = _ema(c, 20)
    atr10 = _atr(h, lo, c, 10)
    ku = ema20 + 2 * atr10
    kl = ema20 - 2 * atr10
    out["ind_kelt_pos_20_10"] = (c - kl) / (ku - kl).replace(0, np.nan)
    out["ind_atr10"] = atr10  # internal-ish; kept prefixed below via rename
    out["ind_kelt_pos_20_10"] = out.pop("ind_kelt_pos_20_10")

    # ADX / +DI / -DI (Wilder 14)
    pc = c.shift(1)
    tr = pd.concat([(h - lo), (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    atr_w = _rma(tr, 14)
    ph, pl = h.shift(1), lo.shift(1)
    upm = h - ph
    dnm = pl - lo
    plus_dm = pd.Series(np.where((upm > dnm) & (upm > 0), upm, 0.0), index=idx)
    minus_dm = pd.Series(np.where((dnm > upm) & (dnm > 0), dnm, 0.0), index=idx)
    s_plus = _rma(plus_dm, 14)
    s_minus = _rma(minus_dm, 14)
    plus_di = 100 * s_plus / atr_w
    minus_di = 100 * s_minus / atr_w
    dx = 100 * (s_plus - s_minus).abs() / (s_plus + s_minus).replace(0, np.nan)
    out["ind_plus_di_14"] = plus_di
    out["ind_minus_di_14"] = minus_di
    out["ind_adx_14"] = _rma(dx, 14)

    typ = (h + lo + c) / 3.0
    sma_typ = typ.rolling(20, min_periods=20).mean()
    md = typ.rolling(20, min_periods=20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    out["ind_cci_20"] = (typ - sma_typ) / (0.015 * md.replace(0, np.nan))

    hh14b = h.rolling(14, min_periods=14).max()
    ll14b = lo.rolling(14, min_periods=14).min()
    out["ind_willr_14"] = (hh14b - c) / (hh14b - ll14b).replace(0, np.nan) * -100

    prev_typ = typ.shift(1)
    rmf = typ * v
    pos_flow = pd.Series(np.where(typ > prev_typ, rmf, 0.0), index=idx).rolling(14, min_periods=14).sum()
    neg_flow = pd.Series(np.where(typ < prev_typ, rmf, 0.0), index=idx).rolling(14, min_periods=14).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        mr = pos_flow / neg_flow.replace(0, np.nan)
        mfi = 100 - 100 / (1 + mr)
    mfi = mfi.mask((neg_flow == 0) & (pos_flow > 0), 100.0)
    mfi = mfi.mask((neg_flow == 0) & (pos_flow == 0), 50.0)
    out["ind_mfi_14"] = mfi

    direction = pd.Series(np.sign(c.diff().to_numpy()), index=idx)
    obv = (direction * v.fillna(0)).cumsum()
    slope20 = (obv - obv.shift(20)) / 20.0
    sm = slope20.rolling(60, min_periods=60).mean()
    ss = slope20.rolling(60, min_periods=60).std(ddof=0)
    out["ind_obv_slope_z_20_60"] = (slope20 - sm) / ss.replace(0, np.nan)

    hl_rng = (h - lo).replace(0, np.nan)
    mfm = ((c - lo) - (h - c)) / hl_rng
    mfm = mfm.fillna(0.0)
    mfv = mfm * v.fillna(0)
    out["ind_cmf_20"] = mfv.rolling(20, min_periods=20).sum() / v.rolling(20, min_periods=20).sum().replace(0, np.nan)

    out["ind_roc_12"] = c / c.shift(12) - 1

    win = 25
    up_pos = h.rolling(win, min_periods=win).apply(lambda x: x.argmax(), raw=True)
    dn_pos = lo.rolling(win, min_periods=win).apply(lambda x: x.argmin(), raw=True)
    a_up = (up_pos + 1) / win * 100
    a_dn = (dn_pos + 1) / win * 100
    out["ind_aroon_up_25"] = a_up
    out["ind_aroon_down_25"] = a_dn
    out["ind_aroon_osc_25"] = a_up - a_dn

    hh9 = h.rolling(9, min_periods=9).max()
    ll9 = lo.rolling(9, min_periods=9).min()
    tenkan = (hh9 + ll9) / 2
    hh26 = h.rolling(26, min_periods=26).max()
    ll26 = lo.rolling(26, min_periods=26).min()
    kijun = (hh26 + ll26) / 2
    sa = (tenkan + kijun) / 2
    hh52 = h.rolling(52, min_periods=52).max()
    ll52 = lo.rolling(52, min_periods=52).min()
    sb = (hh52 + ll52) / 2
    out["ind_ichi_tenkan_dist"] = (c - tenkan) / atr14
    out["ind_ichi_kijun_dist"] = (c - kijun) / atr14
    out["ind_ichi_senkou_a_dist"] = (c - sa) / atr14
    out["ind_ichi_senkou_b_dist"] = (c - sb) / atr14

    st_state, st_line = _supertrend(h, lo, c, 10, 3.0)
    out["ind_supertrend_state"] = st_state
    out["ind_supertrend_dist"] = (c - st_line) / atr10.replace(0, np.nan)

    ps_state, ps_sar = _psar(h, lo, c)
    out["ind_psar_state"] = ps_state
    out["ind_psar_dist"] = (c - ps_sar) / atr14

    for n in (20, 50, 100, 200):
        sma = c.rolling(n, min_periods=n).mean()
        ema = _ema(c, n)
        out[f"ind_sma{n}_dist"] = (c - sma) / atr14
        out[f"ind_sma{n}_slope"] = (sma - sma.shift(5)) / atr14
        out[f"ind_ema{n}_dist"] = (c - ema) / atr14
        out[f"ind_ema{n}_slope"] = (ema - ema.shift(5)) / atr14

    sma20b = c.rolling(20, min_periods=20).mean()
    sma50b = c.rolling(50, min_periods=50).mean()
    sma100b = c.rolling(100, min_periods=100).mean()
    sma200b = c.rolling(200, min_periods=200).mean()
    pairs = [(sma20b, sma50b), (sma20b, sma100b), (sma20b, sma200b),
             (sma50b, sma100b), (sma50b, sma200b), (sma100b, sma200b)]
    stack = pd.concat([pd.Series(np.sign((a - b).to_numpy()), index=idx) for a, b in pairs], axis=1)
    out["ind_ribbon_score"] = stack.mean(axis=1, skipna=True)

    tpv = typ * v.fillna(0)
    sv = v.rolling(24, min_periods=24).sum()
    vwap24 = tpv.rolling(24, min_periods=24).sum() / sv.replace(0, np.nan)
    out["ind_vwap24_dev"] = (c - vwap24) / atr14

    vm = v.rolling(60, min_periods=60).mean()
    vs = v.rolling(60, min_periods=60).std(ddof=0)
    out["ind_vol_z_60"] = (v - vm) / vs.replace(0, np.nan)
    out["ind_taker_buy_ratio"] = (tb / v.replace(0, np.nan)).clip(0, 1)

    # funding (known at or before bar close)
    fl = pd.Series(np.nan, index=idx)
    fm = pd.Series(np.nan, index=idx)
    f = _load_funding_cached()
    if f is not None and len(f):
        tcol = "close_time" if "close_time" in bars else "open_time"
        bt = pd.to_datetime(bars[tcol])
        ft = pd.to_datetime(f["fundingTime"])
        order = np.argsort(bt.to_numpy())
        pos = ft.searchsorted(bt.to_numpy()[order], side="right") - 1
        lv = np.full(len(bars), np.nan)
        mv = np.full(len(bars), np.nan)
        fr = f["fundingRate"].to_numpy(float)
        m7 = f["m7d"].to_numpy(float)
        ok = pos >= 0
        lv[order[ok]] = fr[pos[ok]]
        mv[order[ok]] = m7[pos[ok]]
        fl = pd.Series(lv, index=idx)
        fm = pd.Series(mv, index=idx)
    out["ind_funding_level"] = fl
    out["ind_funding_7d_mean"] = fm

    out.pop("ind_atr10", None)
    df = pd.DataFrame(out, index=idx)
    # guarantee prefix
    df = df.rename(columns={k: (k if k.startswith(PREFIX) else PREFIX + k) for k in df.columns})
    return df


def _cross_up(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def _cross_dn(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    c = bars["close"].astype(float)
    h = bars["high"].astype(float)
    lo = bars["low"].astype(float)
    f = compute(bars)
    ev: dict[str, pd.Series] = {}

    r14, r7 = f["ind_rsi_14"], f["ind_rsi_7"]
    e = pd.Series(0, index=idx)
    e = e.mask((r14.shift(1) < 30) & (r14 >= 30), 1).fillna(0)
    e = e.mask((r14.shift(1) > 70) & (r14 <= 70), -1).fillna(0)
    ev["ind_ev_rsi14_recross"] = e.astype("int8")
    e7 = pd.Series(0, index=idx)
    e7 = e7.mask((r7.shift(1) < 30) & (r7 >= 30), 1).fillna(0)
    e7 = e7.mask((r7.shift(1) > 70) & (r7 <= 70), -1).fillna(0)
    ev["ind_ev_rsi7_recross"] = e7.astype("int8")

    k, d = f["ind_stoch_k_14"], f["ind_stoch_d_3"]
    e = pd.Series(0, index=idx)
    bull = _cross_up(k, d) & (k < 20) & (d < 20)
    bear = _cross_dn(k, d) & (k > 80) & (d > 80)
    e = e.mask(bull.fillna(False), 1).mask(bear.fillna(False), -1).fillna(0)
    ev["ind_ev_stoch_cross"] = e.astype("int8")

    ml, ms = f["ind_macd_line_atr"], f["ind_macd_signal_atr"]
    e = pd.Series(0, index=idx)
    e = e.mask(_cross_up(ml, ms).fillna(False), 1).mask(_cross_dn(ml, ms).fillna(False), -1).fillna(0)
    ev["ind_ev_macd_sig_cross"] = e.astype("int8")
    e = pd.Series(0, index=idx)
    e = e.mask(_cross_up(ml, pd.Series(0.0, index=idx)).fillna(False), 1).mask(
        _cross_dn(ml, pd.Series(0.0, index=idx)).fillna(False), -1).fillna(0)
    ev["ind_ev_macd_zero_cross"] = e.astype("int8")

    sma20 = c.rolling(20, min_periods=20).mean()
    std20 = c.rolling(20, min_periods=20).std(ddof=0)
    bu, bl = sma20 + 2 * std20, sma20 - 2 * std20
    e = pd.Series(0, index=idx)
    e = e.mask(((c.shift(1) < bl.shift(1)) & (c >= bl)).fillna(False), 1)
    e = e.mask(((c.shift(1) > bu.shift(1)) & (c <= bu)).fillna(False), -1).fillna(0)
    ev["ind_ev_bb_reentry"] = e.astype("int8")
    e = pd.Series(0, index=idx)
    e = e.mask(((c.shift(1) <= bu.shift(1)) & (c > bu)).fillna(False), 1)
    e = e.mask(((c.shift(1) >= bl.shift(1)) & (c < bl)).fillna(False), -1).fillna(0)
    ev["ind_ev_bb_breakout"] = e.astype("int8")

    st = f["ind_supertrend_state"]
    e = pd.Series(0, index=idx)
    e = e.mask(((st == 1) & (st.shift(1) == -1)).fillna(False), 1)
    e = e.mask(((st == -1) & (st.shift(1) == 1)).fillna(False), -1).fillna(0)
    ev["ind_ev_supertrend_flip"] = e.astype("int8")

    ps = f["ind_psar_state"]
    e = pd.Series(0, index=idx)
    e = e.mask(((ps == 1) & (ps.shift(1) == -1)).fillna(False), 1)
    e = e.mask(((ps == -1) & (ps.shift(1) == 1)).fillna(False), -1).fillna(0)
    ev["ind_ev_psar_flip"] = e.astype("int8")

    s50 = c.rolling(50, min_periods=50).mean()
    s200 = c.rolling(200, min_periods=200).mean()
    e = pd.Series(0, index=idx)
    e = e.mask(_cross_up(s50, s200).fillna(False), 1).mask(_cross_dn(s50, s200).fillna(False), -1).fillna(0)
    ev["ind_ev_golden_death"] = e.astype("int8")

    adx = f["ind_adx_14"]
    pd14, md14 = f["ind_plus_di_14"], f["ind_minus_di_14"]
    e = pd.Series(0, index=idx)
    bull = _cross_up(pd14, md14) & (adx > 25)
    bear = _cross_dn(pd14, md14) & (adx > 25)
    e = e.mask(bull.fillna(False), 1).mask(bear.fillna(False), -1).fillna(0)
    ev["ind_ev_adx_di_cross"] = e.astype("int8")

    hh9 = h.rolling(9, min_periods=9).max()
    ll9 = lo.rolling(9, min_periods=9).min()
    tenkan = (hh9 + ll9) / 2
    hh26 = h.rolling(26, min_periods=26).max()
    ll26 = lo.rolling(26, min_periods=26).min()
    kijun = (hh26 + ll26) / 2
    sa = (tenkan + kijun) / 2
    hh52 = h.rolling(52, min_periods=52).max()
    ll52 = lo.rolling(52, min_periods=52).min()
    sb = (hh52 + ll52) / 2
    e = pd.Series(0, index=idx)
    e = e.mask(_cross_up(tenkan, kijun).fillna(False), 1).mask(_cross_dn(tenkan, kijun).fillna(False), -1).fillna(0)
    ev["ind_ev_ichi_tk_cross"] = e.astype("int8")
    cu, cl = pd.concat([sa, sb], axis=1).max(axis=1), pd.concat([sa, sb], axis=1).min(axis=1)
    e = pd.Series(0, index=idx)
    e = e.mask(((c.shift(1) <= cu.shift(1)) & (c > cu)).fillna(False), 1)
    e = e.mask(((c.shift(1) >= cl.shift(1)) & (c < cl)).fillna(False), -1).fillna(0)
    ev["ind_ev_ichi_cloud_break"] = e.astype("int8")

    ev["ind_ev_rsi_divergence"] = _rsi_divergence(lo, h, r14)

    return pd.DataFrame(ev, index=idx).astype("int8")


def _rsi_divergence(low: pd.Series, high: pd.Series, rsi: pd.Series, k: int = 3, lookback: int = 60) -> pd.Series:
    """Causal pivot divergence: pivots confirmed k bars later; signal at confirmation bar."""
    lo = low.to_numpy(float)
    hi = high.to_numpy(float)
    r = rsi.to_numpy(float)
    N = len(lo)
    sig = np.zeros(N, dtype=np.int8)
    # confirmed pivot prices/RSI keyed by confirmation index
    low_piv: list[tuple[int, float, float]] = []   # (confirm_idx, price, rsi)
    high_piv: list[tuple[int, float, float]] = []
    for p in range(k, N - k):
        wl = lo[p - k: p + k + 1]
        wh = hi[p - k: p + k + 1]
        c = p + k
        if np.isnan(wl).any() or np.isnan(r[p]):
            pass
        else:
            if lo[p] == wl.min():
                # bullish check vs previous low pivot
                prev = [q for q in low_piv if c - q[0] <= lookback + k]
                if prev:
                    _, p0, r0 = prev[-1]
                    if lo[p] < p0 and r[p] > r0:
                        sig[c] = 1
                low_piv.append((c, float(lo[p]), float(r[p])))
            if hi[p] == wh.max():
                prev = [q for q in high_piv if c - q[0] <= lookback + k]
                if prev:
                    _, p0, r0 = prev[-1]
                    if hi[p] > p0 and r[p] < r0:
                        sig[c] = -1
                high_piv.append((c, float(hi[p]), float(r[p])))
    return pd.Series(sig, index=low.index, dtype="int8")
