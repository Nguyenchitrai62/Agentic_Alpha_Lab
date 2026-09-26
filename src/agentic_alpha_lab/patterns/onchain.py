"""W10 on-chain and stablecoin supply for BTC (vf round).

Fixed definitions (do not change after seeing results; log any change below):

Data: Coin Metrics Community API (free, no key), daily 2019-01-01..2026-09-23.
Files: ``data/raw/onchain_20260924/{btc.csv,stablecoins.csv,
btc_splyexntv_raw.csv,manifest.json}``. Returned BTC metrics: CapMVRVCur,
CapMrktCurUSD, AdrActCnt, TxCnt, HashRate, FeeTotNtv, SplyCur (2823 rows, no
NaNs). FeeTotUSD is HTTP 403 on the community tier, so the fee z-score uses
FeeTotNtv (native units) as a congestion proxy. SplyExNtv was returned but
every row carries ``-status=flash`` (provisional/revisable), so it is stored
raw and EXCLUDED from features. Stablecoins: USDT+USDC CapMrktCurUSD summed
per day (2823 days each, no NaNs).

Availability: a daily on-chain value for date D is known only after D ends;
use D+1 02:00 UTC as the availability time. For a BTC bar with close_time t,
the as-of day is the latest date with date+26h UTC <= t (merge_asof backward
on availability time).

Daily indicators (all causal, rolling on daily values, min_periods = window):
- onc_mvrv: MVRV level (CapMVRVCur).
- onc_mvrv_z365: (mvrv - trailing-365d mean) / trailing-365d population std
  (std==0 -> NaN).
- onc_mvrv_chg30: mvrv / mvrv.shift(30) - 1.
- onc_adr_g30 / onc_tx_g30: AdrActCnt / TxCnt 30d relative growth.
- onc_adr_z365 / onc_tx_z365: level z-score vs trailing 365d (as for MVRV).
- onc_hash_g30: HashRate 30d relative growth.
- onc_fee_z90: (FeeTotNtv - trailing-90d mean) / trailing-90d pop. std.
- onc_stable_g30 / onc_stable_g90: (USDT+USDC) cap 30d / 90d growth.
- onc_stable_g30_z365: z-score of the 30d-growth series vs its trailing 365d
  mean/std (min_periods=365).
- onc_stable_btc_ratio: stable cap / BTC CapMrktCurUSD.
- onc_stable_btc_ratio_chg30: ratio 30d relative change.

Events (int8 {-1,0,1}, rising-edge triggered, causal; the edge fires on the
first bar where the condition holds while the previous bar's condition is
known-False, so persistent regimes yield one event per entry, not one per
bar):
- onc_ev_mvrv_hot: -1 when mvrv z365 crosses above +2.0 (overheated).
- onc_ev_mvrv_cheap: +1 when mvrv crosses below 1.0 (undervalued).
- onc_ev_stable_inflow: +1 when stable 30d-growth z365 crosses above +1.5
  (liquidity inflow).
- onc_ev_hash_drop: -1 when hash-rate 30d growth crosses below -0.10.

Row t uses only information available at bars.close_time[t]; the external
daily history is loaded whole and joined as-of, so truncation only drops rows
(rows <= cut are identical under truncation).

Post-hoc change log: none.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pathlib import Path

PREFIX = "onc_"
ONCHAIN_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "onchain_20260924"

MVRV_Z_WINDOW = 365
MVRV_HOT_Z = 2.0
MVRV_CHEAP = 1.0
GROWTH_WINDOW = 30
LEVEL_Z_WINDOW = 365
FEE_Z_WINDOW = 90
STABLE_LONG_WINDOW = 90
STABLE_GZ_WINDOW = 365
STABLE_INFLOW_Z = 1.5
HASH_DROP = -0.10
AVAIL_HOURS = 26  # date D known at D 00:00 UTC + 26h = D+1 02:00 UTC

_CACHE: pd.DataFrame | None = None
_AVAIL: np.ndarray | None = None


def _load_daily() -> pd.DataFrame:
    """Daily on-chain frame indexed by date (UTC midnight), causal columns."""
    global _CACHE, _AVAIL
    if _CACHE is not None:
        return _CACHE
    btc = pd.read_csv(ONCHAIN_DIR / "btc.csv", parse_dates=["time"])
    btc["date"] = pd.to_datetime(btc["time"], utc=True).dt.normalize()
    btc = btc.sort_values("date").drop_duplicates("date").set_index("date")
    st = pd.read_csv(ONCHAIN_DIR / "stablecoins.csv", parse_dates=["time"])
    st["date"] = pd.to_datetime(st["time"], utc=True).dt.normalize()
    stable = st.groupby("date")["CapMrktCurUSD"].sum().astype(float)
    daily = pd.DataFrame({
        "mvrv": btc["CapMVRVCur"].astype(float),
        "btc_cap": btc["CapMrktCurUSD"].astype(float),
        "adr": btc["AdrActCnt"].astype(float),
        "tx": btc["TxCnt"].astype(float),
        "hash": btc["HashRate"].astype(float),
        "fee": btc["FeeTotNtv"].astype(float),
        "stable": stable,
    }).sort_index()
    _CACHE = daily
    _AVAIL = (daily.index + pd.Timedelta(hours=AVAIL_HOURS)).values.astype(
        "datetime64[ns]").astype("int64")
    return daily


def _z(level: pd.Series, window: int) -> pd.Series:
    m = level.rolling(window, min_periods=window).mean()
    sd = level.rolling(window, min_periods=window).std(ddof=0)
    return (level - m) / sd.replace(0, np.nan)


def _growth(s: pd.Series, k: int) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        return s / s.shift(k) - 1


def _daily_indicators(daily: pd.DataFrame) -> pd.DataFrame:
    ind = pd.DataFrame(index=daily.index)
    ind["onc_mvrv"] = daily["mvrv"]
    ind["onc_mvrv_z365"] = _z(daily["mvrv"], MVRV_Z_WINDOW)
    ind["onc_mvrv_chg30"] = _growth(daily["mvrv"], GROWTH_WINDOW)
    ind["onc_adr_g30"] = _growth(daily["adr"], GROWTH_WINDOW)
    ind["onc_adr_z365"] = _z(daily["adr"], LEVEL_Z_WINDOW)
    ind["onc_tx_g30"] = _growth(daily["tx"], GROWTH_WINDOW)
    ind["onc_tx_z365"] = _z(daily["tx"], LEVEL_Z_WINDOW)
    ind["onc_hash_g30"] = _growth(daily["hash"], GROWTH_WINDOW)
    ind["onc_fee_z90"] = _z(daily["fee"], FEE_Z_WINDOW)
    ind["onc_stable_g30"] = _growth(daily["stable"], GROWTH_WINDOW)
    ind["onc_stable_g90"] = _growth(daily["stable"], STABLE_LONG_WINDOW)
    ind["onc_stable_g30_z365"] = _z(ind["onc_stable_g30"], STABLE_GZ_WINDOW)
    with np.errstate(divide="ignore", invalid="ignore"):
        ind["onc_stable_btc_ratio"] = daily["stable"] / daily["btc_cap"]
    ind["onc_stable_btc_ratio_chg30"] = _growth(
        ind["onc_stable_btc_ratio"], GROWTH_WINDOW)
    return ind


def _i64(s: pd.Series) -> np.ndarray:
    return pd.to_datetime(s, utc=True).values.astype("datetime64[ns]").astype("int64")


def _asof_rows(frame: pd.DataFrame, t_btc: np.ndarray) -> pd.DataFrame:
    assert _AVAIL is not None and len(frame) == len(_AVAIL)
    pos = np.searchsorted(_AVAIL, t_btc, side="right") - 1
    out = pd.DataFrame(index=range(len(t_btc)), columns=frame.columns, dtype=float)
    ok = pos >= 0
    if ok.any():
        out.iloc[np.flatnonzero(ok)] = frame.to_numpy()[pos[ok]]
    out.index = pd.RangeIndex(len(t_btc))
    return out


def _feature_cols() -> list[str]:
    return [c for c in _daily_indicators(_load_daily()).columns
            if c.startswith(PREFIX)]


def compute(bars: pd.DataFrame) -> pd.DataFrame:
    daily = _load_daily()
    ind = _daily_indicators(daily)
    t_btc = _i64(bars["close_time"] if "close_time" in bars else bars["open_time"])
    joined = _asof_rows(ind, t_btc)
    feat = joined[_feature_cols()]
    feat.index = bars.index
    return feat.astype(float)


def _rising_edge(cond: pd.Series) -> np.ndarray:
    c = cond.fillna(False).astype(bool).to_numpy()
    prev_is_false = (cond.shift(1) == False).to_numpy()  # noqa: E712
    return c & prev_is_false


def events(bars: pd.DataFrame) -> pd.DataFrame:
    idx = bars.index
    f = compute(bars)
    hot = f["onc_mvrv_z365"] > MVRV_HOT_Z
    cheap = f["onc_mvrv"] < MVRV_CHEAP
    inflow = f["onc_stable_g30_z365"] > STABLE_INFLOW_Z
    hdrop = f["onc_hash_g30"] < HASH_DROP
    out = pd.DataFrame({
        "onc_ev_mvrv_hot": np.where(_rising_edge(hot), -1, 0),
        "onc_ev_mvrv_cheap": np.where(_rising_edge(cheap), 1, 0),
        "onc_ev_stable_inflow": np.where(_rising_edge(inflow), 1, 0),
        "onc_ev_hash_drop": np.where(_rising_edge(hdrop), -1, 0),
    }, index=idx)
    return out.astype("int8")
