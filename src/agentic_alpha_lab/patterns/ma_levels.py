"""W12 MA support/resistance levels: fixed definitions, causal.

Row t uses only information known at bars.close_time[t].

Fixed definitions (chosen before any event study; do not change):
- MAs per timeframe TF in {15m, 1h, 4h, 1d}: SMA and EMA 20/50/100/200
  (TradingView MA Ribbon defaults). SMA = rolling mean (min_periods=n);
  EMA = ewm(span=n, adjust=False, min_periods=n) on closes.
- Same-TF MAs are computed directly from the input bars' closes.
- Other-TF MAs are computed on full external history (1h/4h/1d from
  data/raw/ma_ribbon_20260924, 15m from data/raw/btc_intraday_20260924)
  and aligned strictly as-of: an MA TF bar counts only if its close_time
  is at or before the input bar close_time (merge_asof backward).
- Touch tests use the MA value as of the previous closed bar of its TF
  (native series shifted by 1; no same-bar MA), so a level tested inside
  the current bar was known at the current bar open.
- ATR14 of the input TF: TR = max(high-low, |high-prev_close|,
  |low-prev_close|), Wilder mean (ewm alpha=1/14, adjust=False,
  min_periods=14).
- compute columns per TF/MA: signed distance of close to the level in
  ATR units; slope = (level - level 5 TF-bars ago) / (5 * ATR) in ATR
  units per TF bar (as-of joined for other TFs); touches = count of the
  last 50 input bars (inclusive) whose [low, high] range covers the level.
- Nearest support = highest level <= close; nearest resistance = lowest
  level >= close; distances in ATR plus TF code (15m=0, 1h=1, 4h=2,
  1d=3), period, kind code (SMA=0, EMA=1).
- Confluence = number of distinct TF/MA levels within 0.5 ATR of the
  nearest (by absolute distance) level.
- Ribbon order score per TF and kind: sign(20-50) + sign(50-100) +
  sign(100-200) + sign(20-200), in {-4..+4} (+4 fully bullish).
- Events are per TF/kind family (8 families); the family level is the
  median of its 4 period as-of levels:
  - bounce_support (+1): prior 10 input closes all above the current
    level value, current low <= level and close >= level.
  - reject_resistance (-1): mirror.
  - break_down (-1): prior close above the level, current close below
    the level by > 0.2 ATR.
  - break_up (+1): mirror.
  - conf_* versions of bounce/reject: same, plus >= 3 of the 32 levels
    within 0.5 ATR of the family level.

Post-hoc change log: none.
"""

from __future__ import annotations

from pathlib import Path

import warnings

import numpy as np
import pandas as pd

PREFIX = "msr_"
TFS = ("15m", "1h", "4h", "1d")
PERIODS = (20, 50, 100, 200)
KINDS = ("sma", "ema")
TF_CODE = {"15m": 0.0, "1h": 1.0, "4h": 2.0, "1d": 3.0}
KIND_CODE = {"sma": 0.0, "ema": 1.0}
ATR_N = 14
TOUCH_W = 50
PRIOR_W = 10
BREAK_K = 0.2
CONF_TOL = 0.5
CONF_MIN = 3

_MA_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "ma_ribbon_20260924"
_INTRA_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "btc_intraday_20260924"

_EXT: dict[str, pd.DataFrame | None] = {}


def _i64(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).values.astype("datetime64[ns]").astype("int64")


def _sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def _ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = ATR_N) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def _infer_input_tf(bars: pd.DataFrame) -> str:
    try:
        if len(bars) >= 3:
            med = pd.to_datetime(bars["open_time"], utc=True).diff().median()
            if pd.notna(med):
                m = med.total_seconds() / 60.0
                if m <= 20:
                    return "15m"
                if m <= 120:
                    return "1h"
                if m <= 720:
                    return "4h"
                return "1d"
    except Exception:
        pass
    return "1h"


def _load_ext(tf: str) -> pd.DataFrame | None:
    """Full external history for TF with previous-bar MAs (shifted by 1)."""
    if tf in _EXT:
        return _EXT[tf]
    try:
        if tf == "15m":
            p = _INTRA_DIR / "klines_15m.parquet"
            if not p.exists():
                _EXT[tf] = None
                return None
            d = pd.read_parquet(p)
        else:
            d = pd.read_parquet(_MA_DIR / f"klines_{tf}.parquet")
    except Exception:
        _EXT[tf] = None
        return None
    d = d.sort_values("close_time").reset_index(drop=True)
    close = d["close"].astype(float)
    out = pd.DataFrame({"close_time": pd.to_datetime(d["close_time"], utc=True)})
    for p_ in PERIODS:
        out[f"sma{p_}"] = _sma(close, p_).shift(1).to_numpy()
        out[f"ema{p_}"] = _ema(close, p_).shift(1).to_numpy()
    out["_ct"] = _i64(out["close_time"])
    _EXT[tf] = out
    return out


def _asof(vals: np.ndarray, t_alt: np.ndarray, t_btc: np.ndarray) -> np.ndarray:
    pos = np.searchsorted(t_alt, t_btc, side="right") - 1
    out = np.full(len(t_btc), np.nan)
    ok = pos >= 0
    out[ok] = vals[pos[ok]]
    return out


def _asof_frame(ext: pd.DataFrame, cols: list[str], t_btc: np.ndarray) -> dict[str, np.ndarray]:
    t_alt = ext["_ct"].to_numpy()
    return {c: _asof(ext[c].to_numpy(float), t_alt, t_btc) for c in cols}


def _core(bars: pd.DataFrame) -> dict:
    """Causal building blocks: atr, per-(tf,kind,period) level and slope."""
    n = len(bars)
    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    atr = _atr(high, low, close).to_numpy(float)
    in_tf = _infer_input_tf(bars)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    lvl: dict[tuple[str, str, int], np.ndarray] = {}
    slope: dict[tuple[str, str, int], np.ndarray] = {}
    for tf in TFS:
        if tf == in_tf:
            for kind in KINDS:
                for p_ in PERIODS:
                    ma = (_sma(close, p_) if kind == "sma" else _ema(close, p_)).shift(1)
                    lv = ma.to_numpy(float)
                    lvl[(tf, kind, p_)] = lv
                    with np.errstate(divide="ignore", invalid="ignore"):
                        slope[(tf, kind, p_)] = (lv - pd.Series(lv).shift(5).to_numpy()) / (5.0 * atr)
        else:
            ext = _load_ext(tf)
            if ext is None:
                for kind in KINDS:
                    for p_ in PERIODS:
                        lvl[(tf, kind, p_)] = np.full(n, np.nan)
                        slope[(tf, kind, p_)] = np.full(n, np.nan)
                continue
            t_alt = ext["_ct"].to_numpy()
            for kind in KINDS:
                for p_ in PERIODS:
                    col = f"{kind}{p_}"
                    nat = ext[col].to_numpy(float)  # already previous-bar values
                    lv = _asof(nat, t_alt, t_btc)
                    lvl[(tf, kind, p_)] = lv
                    # slope on the native TF index: level[i] - level[i-5],
                    # then as-of joined to the input bars.
                    sl5 = nat - pd.Series(nat).shift(5).to_numpy()
                    slv = _asof(sl5, t_alt, t_btc)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        slope[(tf, kind, p_)] = slv / (5.0 * atr)
    return {
        "atr": atr,
        "lvl": lvl,
        "slope": slope,
        "close": close.to_numpy(float),
        "high": high.to_numpy(float),
        "low": low.to_numpy(float),
        "in_tf": in_tf,
    }


def family_levels(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Family (median-of-periods) levels, ATR, and full 32-level matrix.

    Public helper for Study B. All causal (see module docstring).
    """
    c = _core(bars)
    fam: dict[str, np.ndarray] = {}
    mats = []
    names = []
    for tf in TFS:
        for kind in KINDS:
            stack = np.column_stack([c["lvl"][(tf, kind, p_)] for p_ in PERIODS])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                med = np.nanmedian(stack, axis=1)
            med[np.isnan(med)] = np.nan
            fam[f"msr_fam_{tf}_{kind}"] = med
            for j, p_ in enumerate(PERIODS):
                mats.append(stack[:, j])
                names.append(f"msr_lvl_{tf}_{kind}{p_}")
    fam_df = pd.DataFrame(fam, index=bars.index)
    atr = pd.Series(c["atr"], index=bars.index)
    mat = pd.DataFrame(np.column_stack(mats), columns=names, index=bars.index)
    return fam_df, atr, mat


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    c = _core(bars)
    n = len(bars)
    idx = bars.index
    close, high, low, atr = c["close"], c["high"], c["low"], c["atr"]
    lvl, slope = c["lvl"], c["slope"]
    out: dict[str, np.ndarray] = {}
    keys = [(tf, kind, p_) for tf in TFS for kind in KINDS for p_ in PERIODS]
    with np.errstate(divide="ignore", invalid="ignore"):
        for tf, kind, p_ in keys:
            lv = lvl[(tf, kind, p_)]
            out[f"msr_dist_{tf}_{kind}{p_}"] = (close - lv) / atr
            out[f"msr_slope_{tf}_{kind}{p_}"] = slope[(tf, kind, p_)]
            touch = (low <= lv) & (high >= lv) & ~np.isnan(lv)
            out[f"msr_touch50_{tf}_{kind}{p_}"] = (
                pd.Series(touch, index=idx).rolling(TOUCH_W, min_periods=1).sum().to_numpy(float)
            )
    mat = np.column_stack([lvl[k] for k in keys])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with np.errstate(invalid="ignore"):
            below = np.where(np.isnan(mat), np.nan, np.where(mat <= close[:, None], mat, np.nan))
            above = np.where(np.isnan(mat), np.nan, np.where(mat >= close[:, None], mat, np.nan))
            sup = np.nanmax(below, axis=1)
            res = np.nanmin(above, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["msr_near_sup_dist_atr"] = (close - sup) / atr
        out["msr_near_res_dist_atr"] = (res - close) / atr
    sup_tf = np.full(n, np.nan)
    sup_per = np.full(n, np.nan)
    sup_kind = np.full(n, np.nan)
    res_tf = np.full(n, np.nan)
    res_per = np.full(n, np.nan)
    res_kind = np.full(n, np.nan)
    for j, (tf, kind, p_) in enumerate(keys):
        col = mat[:, j]
        is_sup = ~np.isnan(col) & (col == sup)
        is_res = ~np.isnan(col) & (col == res)
        take_sup = is_sup & np.isnan(sup_tf)
        take_res = is_res & np.isnan(res_tf)
        sup_tf[take_sup] = TF_CODE[tf]
        sup_per[take_sup] = float(p_)
        sup_kind[take_sup] = KIND_CODE[kind]
        res_tf[take_res] = TF_CODE[tf]
        res_per[take_res] = float(p_)
        res_kind[take_res] = KIND_CODE[kind]
    out["msr_near_sup_tf"] = sup_tf
    out["msr_near_sup_period"] = sup_per
    out["msr_near_sup_kind"] = sup_kind
    out["msr_near_res_tf"] = res_tf
    out["msr_near_res_period"] = res_per
    out["msr_near_res_kind"] = res_kind
    with np.errstate(invalid="ignore", divide="ignore"):
        absdiff = np.abs(mat - close[:, None])
        absdiff[np.isnan(mat)] = np.inf
        j_best = np.argmin(absdiff, axis=1)
        any_valid = np.isfinite(absdiff[np.arange(n), j_best])
        nearest_val = np.full(n, np.nan)
        nearest_val[any_valid] = mat[np.arange(n)[any_valid], j_best[any_valid]]
        within = (~np.isnan(mat)) & (
            np.abs(mat - nearest_val[:, None]) <= CONF_TOL * atr[:, None]
        )
        out["msr_confluence"] = np.where(
            np.isnan(nearest_val), np.nan, within.sum(axis=1).astype(float)
        )
        out["msr_nearest_dist_atr"] = np.where(
            np.isnan(nearest_val), np.nan, (close - nearest_val) / atr
        )
    for tf in TFS:
        for kind in KINDS:
            a = lvl[(tf, kind, 20)]
            b = lvl[(tf, kind, 50)]
            d = lvl[(tf, kind, 100)]
            e = lvl[(tf, kind, 200)]
            with np.errstate(invalid="ignore"):
                s = np.nan_to_num(np.sign(a - b)) + np.nan_to_num(np.sign(b - d))
                s = s + np.nan_to_num(np.sign(d - e)) + np.nan_to_num(np.sign(a - e))
            has = ~(np.isnan(a) | np.isnan(b) | np.isnan(d) | np.isnan(e))
            out[f"msr_ribbon_{tf}_{kind}"] = np.where(has, s, np.nan)
    df = pd.DataFrame(out, index=idx)
    return df.astype(float)


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    n = len(bars)
    c = _core(bars)
    close, high, low, atr = c["close"], c["high"], c["low"], c["atr"]
    lvl = c["lvl"]
    keys = [(tf, kind, p_) for tf in TFS for kind in KINDS for p_ in PERIODS]
    mat = np.column_stack([lvl[k] for k in keys])
    close_s = pd.Series(close, index=idx)
    ev: dict[str, np.ndarray] = {}
    for tf in TFS:
        for kind in KINDS:
            stack = np.column_stack([lvl[(tf, kind, p_)] for p_ in PERIODS])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                with np.errstate(invalid="ignore"):
                    lv = np.nanmedian(stack, axis=1)
            valid = ~np.isnan(lv) & ~np.isnan(atr) & (atr > 0)
            shifted = close_s.shift(1)
            prior = shifted.rolling(PRIOR_W, min_periods=PRIOR_W).min().to_numpy(float)
            prior_max = shifted.rolling(PRIOR_W, min_periods=PRIOR_W).max().to_numpy(float)
            prev_close = shifted.to_numpy(float)
            above10 = valid & ~np.isnan(prior) & (prior > lv)
            below10 = valid & ~np.isnan(prior_max) & (prior_max < lv)
            bounce = above10 & (low <= lv) & (close >= lv)
            reject = below10 & (high >= lv) & (close <= lv)
            with np.errstate(invalid="ignore"):
                brk_dn = valid & ~np.isnan(prev_close) & (prev_close > lv) & ((lv - close) > BREAK_K * atr)
                brk_up = valid & ~np.isnan(prev_close) & (prev_close < lv) & ((close - lv) > BREAK_K * atr)
            within = (~np.isnan(mat)) & valid[:, None] & (
                np.abs(mat - lv[:, None]) <= CONF_TOL * atr[:, None]
            )
            nconf = within.sum(axis=1)
            conf_ok = valid & (nconf >= CONF_MIN)
            base = f"msr_ev_{tf}_{kind}"
            ev[f"{base}_bounce_support"] = np.where(bounce, np.int8(1), np.int8(0))
            ev[f"{base}_reject_resistance"] = np.where(reject, np.int8(-1), np.int8(0))
            ev[f"{base}_break_down"] = np.where(brk_dn, np.int8(-1), np.int8(0))
            ev[f"{base}_break_up"] = np.where(brk_up, np.int8(1), np.int8(0))
            ev[f"{base}_conf_bounce_support"] = np.where(bounce & conf_ok, np.int8(1), np.int8(0))
            ev[f"{base}_conf_reject_resistance"] = np.where(reject & conf_ok, np.int8(-1), np.int8(0))
    return pd.DataFrame(ev, index=idx).astype("int8")
