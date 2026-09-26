"""MJ W15 relative value between majors (vf round).

Fixed definitions (do not change after seeing results; log any change below):
- Assets: BTC (bars passed in, via common.load_bars) plus ETH, SOL, BNB, XRP
  from data/raw/xasset_20260924/{SYM}USDT_{4h,1d}.parquet.
- Alt timeframe matches the BTC bar timeframe: 1d BTC bars use alt 1d bars,
  4h/1h BTC bars use alt 4h bars. An alt print counts only if its close_time
  is at or before the BTC bar close_time (merge_asof backward via
  searchsorted side="right"). Alts not yet listed give NaN (feature) / 0 (event).
- Pairs (R = close_A / close_B, as-of aligned): ETH/BTC, SOL/BTC, SOL/ETH,
  BNB/BTC, XRP/BTC. Codes: ethbtc, solbtc, soleth, bnbbtc, xrpbtc.
- pr_{code}_lrz{20,60,120}: z = (logR - trailing-w mean) / trailing-w std
  (population, ddof=0, min_periods=w).
- pr_{code}_trend: +1.0 when ratio EMA20 >= EMA100 else -1.0, NaN until both
  defined (ewm span, adjust=False, min_periods=span, on R).
- pr_{code}_trend_dist: R / EMA100 - 1.
- pr_{code}_beta60: trailing-60 OLS beta of A log returns on B log returns
  (cov/var, min_periods=60, var==0 -> NaN). Returns are log close-to-close on
  the as-of aligned series.
- pr_{code}_resid_z60: res[t] = rA[t] - beta60[t-1]*rB[t] (prior beta, causal);
  cumres = trailing-60 sum of res; z = cumres / (trailing-60 std of res *
  sqrt(60)) (population std, min_periods=60, std==0 -> NaN).
- pr_{code}_rv60: trailing-60 population std of ratio log returns
  (logR.diff, min_periods=60).
- pr_{code}_corr60: trailing-60 correlation of rA vs rB (min_periods=60).

Events (int8 {-1,0,1}, causal, level/breach evaluated at row t):
- pr_ev_{code}_mr: +1 when lrz60 < -2 (A cheap vs B -> long A/short B),
  -1 when lrz60 > +2.
- pr_ev_{code}_brk: +1 when R exceeds its prior 55-bar maximum
  (shift(1).rolling(55).max), -1 when below its prior 55-bar minimum.
- pr_ev_{code}_resid: +1 when resid_z60 < -2, -1 when resid_z60 > +2.

Post-hoc change log: none.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PREFIX = "pr_"
ALT_SYMBOLS = ("ETH", "SOL", "BNB", "XRP")
XASSET_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "xasset_20260924"
# (code, legA, legB); "BTC" means the bars passed in.
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("ethbtc", "ETH", "BTC"),
    ("solbtc", "SOL", "BTC"),
    ("soleth", "SOL", "ETH"),
    ("bnbbtc", "BNB", "BTC"),
    ("xrpbtc", "XRP", "BTC"),
)

Z_WINDOWS = (20, 60, 120)
BETA_WINDOW = 60
RESID_WINDOW = 60
RV_WINDOW = 60
CORR_WINDOW = 60
BREAK_WINDOW = 55
MR_Z = 2.0
RESID_Z = 2.0

_ALT_CACHE: dict[str, dict[str, pd.DataFrame]] = {}


def _i64(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).values.astype("datetime64[ns]").astype("int64")


def _load_alt(alt_tf: str) -> dict[str, pd.DataFrame]:
    if alt_tf in _ALT_CACHE:
        return _ALT_CACHE[alt_tf]
    per: dict[str, pd.DataFrame] = {}
    for sym in ALT_SYMBOLS:
        d = pd.read_parquet(XASSET_DIR / f"{sym}USDT_{alt_tf}.parquet")
        d = d.sort_values("close_time").reset_index(drop=True)
        d["_ct"] = _i64(d["close_time"])
        per[sym] = d
    _ALT_CACHE[alt_tf] = per
    return per


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
    out[ok] = vals[pos[ok]]
    return out


def _leg_series(bars: pd.DataFrame, leg: str, col: str, alt_tf: str,
                per: dict[str, pd.DataFrame], t_btc: np.ndarray) -> np.ndarray:
    if leg == "BTC":
        return bars[col].astype(float).to_numpy(float)
    d = per[leg]
    return _asof(d[col].to_numpy(float), d["_ct"].to_numpy(), t_btc)


def _legs(code: str) -> tuple[str, str]:
    for c, a, b in PAIRS:
        if c == code:
            return a, b
    raise KeyError(code)


def _ratio(bars: pd.DataFrame, leg_a: str, leg_b: str) -> tuple[pd.Series, str]:
    """As-of aligned close_A / close_B as a Series on bars.index."""
    alt_tf = _infer_alt_tf(bars)
    per = _load_alt(alt_tf)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    with np.errstate(divide="ignore", invalid="ignore"):
        r = _leg_series(bars, leg_a, "close", alt_tf, per, t_btc) / _leg_series(
            bars, leg_b, "close", alt_tf, per, t_btc)
    return pd.Series(r, index=bars.index), alt_tf


def _ratio_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """As-of aligned opens and closes for every pair leg (causal)."""
    alt_tf = _infer_alt_tf(bars)
    per = _load_alt(alt_tf)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    out: dict[str, np.ndarray] = {}
    for code, leg_a, leg_b in PAIRS:
        out[f"{code}_a_close"] = _leg_series(bars, leg_a, "close", alt_tf, per, t_btc)
        out[f"{code}_b_close"] = _leg_series(bars, leg_b, "close", alt_tf, per, t_btc)
        out[f"{code}_a_open"] = _leg_series(bars, leg_a, "open", alt_tf, per, t_btc)
        out[f"{code}_b_open"] = _leg_series(bars, leg_b, "open", alt_tf, per, t_btc)
    return pd.DataFrame(out, index=bars.index)


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    legs = _ratio_frame(bars)
    out: dict[str, np.ndarray] = {}
    for code, _, _ in PAIRS:
        a = pd.Series(legs[f"{code}_a_close"].to_numpy(float), index=idx)
        b = pd.Series(legs[f"{code}_b_close"].to_numpy(float), index=idx)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = a / b
            logr = np.log(r)
        for w in Z_WINDOWS:
            m = logr.rolling(w, min_periods=w).mean()
            sd = logr.rolling(w, min_periods=w).std(ddof=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                out[f"pr_{code}_lrz{w}"] = ((logr - m) / sd.replace(0, np.nan)).to_numpy(float)
        ema20 = r.ewm(span=20, adjust=False, min_periods=20).mean()
        ema100 = r.ewm(span=100, adjust=False, min_periods=100).mean()
        valid = ema20.notna() & ema100.notna()
        trend = pd.Series(np.nan, index=idx)
        trend[valid] = np.where(ema20[valid] >= ema100[valid], 1.0, -1.0)
        out[f"pr_{code}_trend"] = trend.to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"pr_{code}_trend_dist"] = (r / ema100 - 1).to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            ra = np.log(a / a.shift(1))
            rb = np.log(b / b.shift(1))
        xy = (ra * rb).rolling(BETA_WINDOW, min_periods=BETA_WINDOW).mean()
        mx = ra.rolling(BETA_WINDOW, min_periods=BETA_WINDOW).mean()
        my = rb.rolling(BETA_WINDOW, min_periods=BETA_WINDOW).mean()
        var = (rb * rb).rolling(BETA_WINDOW, min_periods=BETA_WINDOW).mean() - my * my
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = (xy - mx * my) / var.replace(0, np.nan)
        out[f"pr_{code}_beta60"] = beta.to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            res = ra - beta.shift(1) * rb
        cumres = res.rolling(RESID_WINDOW, min_periods=RESID_WINDOW).sum()
        res_std = res.rolling(RESID_WINDOW, min_periods=RESID_WINDOW).std(ddof=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"pr_{code}_resid_z60"] = (
                cumres / (res_std * np.sqrt(RESID_WINDOW)).replace(0, np.nan)
            ).to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"pr_{code}_rv60"] = logr.diff().rolling(
                RV_WINDOW, min_periods=RV_WINDOW).std(ddof=0).to_numpy(float)
        out[f"pr_{code}_corr60"] = ra.rolling(
            CORR_WINDOW, min_periods=CORR_WINDOW).corr(rb).to_numpy(float)
    return pd.DataFrame(out, index=idx).astype(float)


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    f = compute(bars)
    ev: dict[str, pd.Series] = {}
    for code, leg_a, leg_b in PAIRS:
        z = f[f"pr_{code}_lrz60"]
        sig = pd.Series(0, index=idx)
        sig = sig.mask(z < -MR_Z, 1)
        sig = sig.mask(z > MR_Z, -1).fillna(0)
        ev[f"pr_ev_{code}_mr"] = sig.astype("int8")

        r, _ = _ratio(bars, leg_a, leg_b)
        pmax = r.shift(1).rolling(BREAK_WINDOW, min_periods=BREAK_WINDOW).max()
        pmin = r.shift(1).rolling(BREAK_WINDOW, min_periods=BREAK_WINDOW).min()
        sig = pd.Series(0, index=idx)
        sig = sig.mask((r > pmax) & pmax.notna(), 1)
        sig = sig.mask((r < pmin) & pmin.notna(), -1).fillna(0)
        ev[f"pr_ev_{code}_brk"] = sig.astype("int8")

        rz = f[f"pr_{code}_resid_z60"]
        sig = pd.Series(0, index=idx)
        sig = sig.mask(rz < -RESID_Z, 1)
        sig = sig.mask(rz > RESID_Z, -1).fillna(0)
        ev[f"pr_ev_{code}_resid"] = sig.astype("int8")
    return pd.DataFrame(ev, index=idx).astype("int8")
