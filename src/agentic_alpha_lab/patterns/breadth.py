"""W6 alt-market breadth and cross-asset lead/lag for BTC (vf round).

Fixed definitions (do not change after seeing results; log any change below):
- Universe: ETH, BNB, SOL, XRP, ADA, DOGE, LINK, LTC, BCH, TRX (Binance USD-M).
- Alt timeframe matches the BTC bar timeframe: 1d BTC bars use alt 1d bars,
  4h/1h BTC bars use alt 4h bars. An alt bar counts only if its close_time is
  at or before the BTC bar close_time (merge_asof backward). Alts not yet
  listed are excluded from denominators.
- brd_above_ema50_frac / brd_above_ema200_frac: fraction of listed alts with
  close above their own causal EMA50 / EMA200 (ewm span, adjust=False).
- brd_ribbon_up_frac / brd_ribbon_down_frac: fraction with EMA20 > EMA200 /
  EMA20 < EMA200 (on the matched alt timeframe).
- brd_rs_med_{1,6,42}: median over listed alts of (alt k-bar log return minus
  BTC k-bar log return), closes, k in (1, 6, 42).
- brd_ethbtc_dist: ETH_asof/BTC ratio distance to its causal EMA50
  (ratio/EMA50 - 1).
- brd_dispersion_6: cross-sectional population std (ddof=0) of alt 6-bar log
  returns.
- brd_funding_z_mean: mean across listed alts of the per-alt funding z-score,
  z = (rate - trailing-30-print mean) / trailing-30-print std (min_periods=30,
  std==0 -> NaN), funding print counts only if fundingTime <= BTC close_time.
- brd_high55_cnt / brd_low55_cnt (+ fracs): alts whose close is the trailing
  55-bar maximum / minimum of close; fracs divide by n_listed.
- brd_n_listed: number of alts listed at the BTC bar close.

Events (int8 {-1,0,1}, causal):
- brd_ev_thrust: +1 when above-EMA50 fraction crosses up through 0.70,
  -1 when it crosses down through 0.30.
- brd_ev_ethbtc_break: +1 when the ETH/BTC ratio exceeds its prior 55-bar
  maximum, -1 when below its prior 55-bar minimum.
- brd_ev_fund_crowd: -1 when mean funding z crosses up through +2.0.
- brd_ev_divergence: -1 on bars where BTC close is a trailing 55-bar high
  while fewer than 30% of listed alts are at 55-bar highs.

Post-hoc change log: none.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

PREFIX = "brd_"
SYMBOLS = ("ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "LINK", "LTC", "BCH", "TRX")
XASSET_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "xasset_20260924"

THRUST_UP = 0.70
THRUST_DN = 0.30
FUND_CROWD_Z = 2.0
DIV_ALT_FRAC = 0.30
N_HIGHLOW = 55
FUND_Z_WINDOW = 30

_ALT_CACHE: dict[str, dict] = {}
_FUND_CACHE: dict[str, pd.DataFrame] = {}


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _i64(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).values.astype("datetime64[ns]").astype("int64")


def _load_alt(alt_tf: str) -> dict:
    if alt_tf in _ALT_CACHE:
        return _ALT_CACHE[alt_tf]
    per: dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS:
        d = pd.read_parquet(XASSET_DIR / f"{sym}USDT_{alt_tf}.parquet")
        d = d.sort_values("close_time").reset_index(drop=True)
        close = d["close"].astype(float)
        d["ema20"] = _ema(close, 20)
        d["ema50"] = _ema(close, 50)
        d["ema200"] = _ema(close, 200)
        mx = close.rolling(N_HIGHLOW, min_periods=N_HIGHLOW).max()
        mn = close.rolling(N_HIGHLOW, min_periods=N_HIGHLOW).min()
        d["is_high55"] = (close >= mx) & mx.notna()
        d["is_low55"] = (close <= mn) & mn.notna()
        d["_ct"] = _i64(d["close_time"])
        per[sym] = d
    bundle = {"per": per}
    _ALT_CACHE[alt_tf] = bundle
    return bundle


def _load_fund(sym: str) -> pd.DataFrame:
    if sym in _FUND_CACHE:
        return _FUND_CACHE[sym]
    f = pd.read_parquet(XASSET_DIR / f"{sym}USDT_funding.parquet")
    f = f.sort_values("fundingTime").reset_index(drop=True)
    fr = f["fundingRate"].astype(float)
    m = fr.rolling(FUND_Z_WINDOW, min_periods=FUND_Z_WINDOW).mean()
    sd = fr.rolling(FUND_Z_WINDOW, min_periods=FUND_Z_WINDOW).std(ddof=0)
    z = (fr - m) / sd.replace(0, np.nan)
    f = f.assign(z=z, _ft=_i64(f["fundingTime"]))
    _FUND_CACHE[sym] = f
    return f


def _infer_alt_tf(bars: pd.DataFrame) -> str:
    try:
        if len(bars) >= 3:
            med = pd.to_datetime(bars["open_time"]).diff().median()
            if pd.notna(med) and med >= pd.Timedelta(hours=20):
                return "1d"
    except Exception:
        pass
    return "4h"


def _asof(vals: np.ndarray, t_alt: np.ndarray, t_btc: np.ndarray) -> np.ndarray:
    pos = np.searchsorted(t_alt, t_btc, side="right") - 1
    out = np.full(len(t_btc), np.nan)
    ok = pos >= 0
    if vals.dtype == bool:
        v = vals.astype(float)
        out[ok] = v[pos[ok]]
    else:
        out[ok] = vals[pos[ok]]
    return out


def _joined(bars: pd.DataFrame, alt_tf: str) -> dict[str, np.ndarray]:
    bundle = _load_alt(alt_tf)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    cols: dict[str, list] = {"close": [], "ema20": [], "ema50": [], "ema200": [],
                             "hi": [], "lo": []}
    for sym in SYMBOLS:
        d = bundle["per"][sym]
        t_alt = d["_ct"].to_numpy()
        cols["close"].append(_asof(d["close"].to_numpy(float), t_alt, t_btc))
        cols["ema20"].append(_asof(d["ema20"].to_numpy(float), t_alt, t_btc))
        cols["ema50"].append(_asof(d["ema50"].to_numpy(float), t_alt, t_btc))
        cols["ema200"].append(_asof(d["ema200"].to_numpy(float), t_alt, t_btc))
        cols["hi"].append(_asof(d["is_high55"].to_numpy(bool), t_alt, t_btc))
        cols["lo"].append(_asof(d["is_low55"].to_numpy(bool), t_alt, t_btc))
    return {k: np.column_stack(v) for k, v in cols.items()}


def _kret(mat: np.ndarray, k: int) -> np.ndarray:
    n = mat.shape[0]
    base = np.full_like(mat, np.nan)
    if n > k:
        base[k:] = mat[:-k]
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(mat / base)


def _bret(bc: np.ndarray, k: int) -> np.ndarray:
    n = len(bc)
    base = np.full(n, np.nan)
    if n > k:
        base[k:] = bc[: n - k]
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.log(bc / base)


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    n = len(bars)
    alt_tf = _infer_alt_tf(bars)
    J = _joined(bars, alt_tf)
    C, E20, E50, E200 = J["close"], J["ema20"], J["ema50"], J["ema200"]
    listed = ~np.isnan(C)
    n_listed = listed.sum(axis=1).astype(float)

    def _frac(mask: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore"):
            num = np.where(listed, mask, False).sum(axis=1).astype(float)
            out = num / n_listed
        out[n_listed == 0] = np.nan
        return out

    above50 = (C > E50) & listed
    above200 = (C > E200) & listed
    rib_up = (E20 > E200) & listed & ~np.isnan(E20) & ~np.isnan(E200)
    rib_dn = (E20 < E200) & listed & ~np.isnan(E20) & ~np.isnan(E200)

    bc = bars["close"].astype(float).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out: dict[str, np.ndarray] = {}
        out["brd_above_ema50_frac"] = _frac(above50)
        out["brd_above_ema200_frac"] = _frac(above200)
        out["brd_ribbon_up_frac"] = _frac(rib_up)
        out["brd_ribbon_down_frac"] = _frac(rib_dn)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for k in (1, 6, 42):
                bret = _bret(bc, k)
                aret = _kret(C, k)
                diff = aret - bret[:, None]
                diff[~listed] = np.nan
                out[f"brd_rs_med_{k}"] = np.nanmedian(diff, axis=1)
            out["brd_dispersion_6"] = np.nanstd(_kret(C, 6), axis=1, ddof=0)

        eth = C[:, 0]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ratio = eth / bc
            rema = pd.Series(ratio).ewm(span=50, adjust=False, min_periods=50).mean().to_numpy()
            out["brd_ethbtc_dist"] = ratio / rema - 1

        t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
        zmat = np.column_stack([
            _asof(_load_fund(s)["z"].to_numpy(float),
                  _load_fund(s)["_ft"].to_numpy(), t_btc) for s in SYMBOLS
        ])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mz = np.nanmean(zmat, axis=1)
        mz[n_listed == 0] = np.nan
        out["brd_funding_z_mean"] = mz

        hi = np.where(np.isnan(J["hi"]), 0.0, J["hi"])
        lo = np.where(np.isnan(J["lo"]), 0.0, J["lo"])
        hi_cnt = (hi == 1.0).sum(axis=1).astype(float)
        lo_cnt = (lo == 1.0).sum(axis=1).astype(float)
        hi_cnt[n_listed == 0] = np.nan
        lo_cnt[n_listed == 0] = np.nan
        out["brd_high55_cnt"] = hi_cnt
        out["brd_low55_cnt"] = lo_cnt
        with np.errstate(invalid="ignore"):
            out["brd_high55_frac"] = hi_cnt / n_listed
            out["brd_low55_frac"] = lo_cnt / n_listed
        out["brd_n_listed"] = n_listed

    df = pd.DataFrame(out, index=idx)
    return df.astype(float)


def _eth_ratio(bars: pd.DataFrame, alt_tf: str) -> pd.Series:
    bundle = _load_alt(alt_tf)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    d = bundle["per"]["ETH"]
    eth = _asof(d["close"].to_numpy(float), d["_ct"].to_numpy(), t_btc)
    bc = bars["close"].astype(float).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return pd.Series(eth / bc, index=bars.index)


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    alt_tf = _infer_alt_tf(bars)
    f = compute(bars)
    ev: dict[str, pd.Series] = {}

    a = f["brd_above_ema50_frac"]
    sig = pd.Series(0, index=idx)
    sig = sig.mask((a > THRUST_UP) & (a.shift(1) <= THRUST_UP), 1)
    sig = sig.mask((a < THRUST_DN) & (a.shift(1) >= THRUST_DN), -1).fillna(0)
    ev["brd_ev_thrust"] = sig.astype("int8")

    r = _eth_ratio(bars, alt_tf)
    pmax = r.shift(1).rolling(N_HIGHLOW, min_periods=N_HIGHLOW).max()
    pmin = r.shift(1).rolling(N_HIGHLOW, min_periods=N_HIGHLOW).min()
    sig = pd.Series(0, index=idx)
    sig = sig.mask((r > pmax) & pmax.notna(), 1)
    sig = sig.mask((r < pmin) & pmin.notna(), -1).fillna(0)
    ev["brd_ev_ethbtc_break"] = sig.astype("int8")

    z = f["brd_funding_z_mean"]
    sig = pd.Series(0, index=idx)
    sig = sig.mask((z > FUND_CROWD_Z) & (z.shift(1) <= FUND_CROWD_Z), -1).fillna(0)
    ev["brd_ev_fund_crowd"] = sig.astype("int8")

    c = bars["close"].astype(float)
    cmax = c.rolling(N_HIGHLOW, min_periods=N_HIGHLOW).max()
    btc_high = (c >= cmax) & cmax.notna()
    weak = f["brd_high55_frac"] < DIV_ALT_FRAC
    sig = pd.Series(0, index=idx)
    sig = sig.mask((btc_high & weak.fillna(False)).fillna(False), -1).fillna(0)
    ev["brd_ev_divergence"] = sig.astype("int8")

    return pd.DataFrame(ev, index=idx).astype("int8")
