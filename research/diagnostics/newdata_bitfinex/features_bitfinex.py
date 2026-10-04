"""Causal Bitfinex margin-positioning features (new-data round A, tag bitfinex).

PRE-REGISTERED FEATURE SET (fixed 2026-10-04 before looking at any result):
own-coin features (computed on the fill's own coin series; NaN for BNB which
has no Bitfinex margin market):
  bfx_logls          = log(long / short)
  bfx_dlog_long_4h   = log(L_t / L_{t-4h})
  bfx_dlog_short_4h  = log(S_t / S_{t-4h})
  bfx_dlog_ls_4h     = dlog_long_4h - dlog_short_4h
  bfx_dlog_long_24h  = log(L_t / L_{t-24h})
  bfx_dlog_short_24h = log(S_t / S_{t-24h})
  bfx_dlog_ls_24h    = dlog_long_24h - dlog_short_24h
  bfx_z_logls_30d    = (logls - trailing-720h mean) / trailing-720h std
                       (min_periods 168; ddof 0)
market-wide features (BTC values, available for every coin incl. BNB):
  bfx_btc_logls, bfx_btc_dlog_ls_24h, bfx_btc_z_logls_30d
market-wide USD-funding features (credits.size:1h:fUSD total funding-credit
size, a leverage-demand proxy; history from 2021-04-07; same for every coin):
  bfx_fusd_log, bfx_fusd_dlog_24h, bfx_fusd_z_30d

CAUSALITY: every feature at stamp t uses only snapshots with stamp <= t
(rolling windows are trailing; hourly grid is forward-filled, which is
causal). PUBLICATION LAG: a snapshot stamped h has availability time h + 1h;
joins use availability strictly before the fill minute (fills) or <= the 4h
close (bar study). Truncating the raw panel at T leaves all features at
stamps <= T unchanged (asserted in tests).

Coin mapping: BTCUSDT->BTC, ETHUSDT->ETH, SOLUSDT->SOL, BNBUSDT->(BTC-wide
only), XRPUSDT->XRP.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PANEL_PATH = Path(__file__).resolve().parents[3] / "data" / "raw" / "bitfinex_20261004" / "bitfinex_margin_1h.parquet"

PUB_LAG = pd.Timedelta("1h")
COINS = ("BTC", "ETH", "XRP", "SOL")
SYM_TO_COIN = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
    "BNBUSDT": None,  # no Bitfinex margin market -> BTC-wide features only
    "XRPUSDT": "XRP",
}
OWN_FEATURES = [
    "bfx_logls",
    "bfx_dlog_long_4h",
    "bfx_dlog_short_4h",
    "bfx_dlog_ls_4h",
    "bfx_dlog_long_24h",
    "bfx_dlog_short_24h",
    "bfx_dlog_ls_24h",
    "bfx_z_logls_30d",
]
BTC_FEATURES = ["bfx_btc_logls", "bfx_btc_dlog_ls_24h", "bfx_btc_z_logls_30d"]
FUND_FEATURES = ["bfx_fusd_log", "bfx_fusd_dlog_24h", "bfx_fusd_z_30d"]
MARKET_FEATURES = BTC_FEATURES + FUND_FEATURES
ALL_FEATURES = OWN_FEATURES + MARKET_FEATURES


def load_panel(path: str | Path = PANEL_PATH) -> pd.DataFrame:
    panel = pd.read_parquet(path)
    panel.index = pd.to_datetime(panel.index, utc=True)
    return panel.sort_index()


def _coin_frame(panel: pd.DataFrame, coin: str) -> pd.DataFrame:
    """Causal per-coin features indexed by stamp ts (hourly)."""
    g = panel[[f"{coin}_long", f"{coin}_short"]].copy()
    g.columns = ["long", "short"]
    # causal hourly grid: reindex + forward-fill (past only)
    full = pd.date_range(g.index.min().floor("h"), g.index.max().ceil("h"), freq="h", tz="UTC")
    g = g.reindex(full).ffill()
    long = g["long"].astype(float)
    short = g["short"].astype(float)
    logls = np.log(long / short)
    out = pd.DataFrame(index=g.index)
    out["bfx_logls"] = logls
    out["bfx_dlog_long_4h"] = np.log(long / long.shift(4))
    out["bfx_dlog_short_4h"] = np.log(short / short.shift(4))
    out["bfx_dlog_ls_4h"] = out["bfx_dlog_long_4h"] - out["bfx_dlog_short_4h"]
    out["bfx_dlog_long_24h"] = np.log(long / long.shift(24))
    out["bfx_dlog_short_24h"] = np.log(short / short.shift(24))
    out["bfx_dlog_ls_24h"] = out["bfx_dlog_long_24h"] - out["bfx_dlog_short_24h"]
    mu = logls.rolling(720, min_periods=168).mean()
    sd = logls.rolling(720, min_periods=168).std(ddof=0)
    out["bfx_z_logls_30d"] = (logls - mu) / sd.replace(0.0, np.nan)
    out.index.name = "ts"
    return out


def _fund_frame(panel: pd.DataFrame) -> pd.DataFrame:
    """Causal market-wide USD-funding features indexed by stamp ts (hourly)."""
    g = panel[["FUSD"]].copy() if "FUSD" in panel.columns else pd.DataFrame(
        {"FUSD": np.nan}, index=panel.index)
    full = pd.date_range(g.index.min().floor("h"), g.index.max().ceil("h"), freq="h", tz="UTC")
    f = g.reindex(full)["FUSD"].ffill().astype(float)
    logf = np.log(f)
    out = pd.DataFrame(index=full)
    out["bfx_fusd_log"] = logf
    out["bfx_fusd_dlog_24h"] = logf - logf.shift(24)
    mu = logf.rolling(720, min_periods=168).mean()
    sd = logf.rolling(720, min_periods=168).std(ddof=0)
    out["bfx_fusd_z_30d"] = (logf - mu) / sd.replace(0.0, np.nan)
    out.index.name = "ts"
    return out


def compute_all_features(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    feats = {coin: _coin_frame(panel, coin) for coin in COINS}
    feats["FUSD"] = _fund_frame(panel)
    return feats


def _market_frame(feats: dict[str, pd.DataFrame]) -> pd.DataFrame:
    btc = feats["BTC"][["bfx_logls", "bfx_dlog_ls_24h", "bfx_z_logls_30d"]].copy()
    btc.columns = BTC_FEATURES
    fund = feats["FUSD"][FUND_FEATURES] if "FUSD" in feats else pd.DataFrame(
        np.nan, index=btc.index, columns=FUND_FEATURES)
    return pd.concat([btc, fund], axis=1)


def _asof(
    times: pd.Series, feats: pd.DataFrame, cols: list[str], exact: bool
) -> pd.DataFrame:
    right = feats[cols].copy()
    right["_avail"] = right.index + PUB_LAG
    right = right.sort_values("_avail")
    left = pd.DataFrame({"_t": pd.to_datetime(times, utc=True)}).sort_values("_t")
    m = pd.merge_asof(
        left, right, left_on="_t", right_on="_avail",
        direction="backward", allow_exact_matches=exact,
    ).set_index(left.index)
    m = m.drop(columns=["_t", "_avail"])
    return m


def asof_for_fills(
    fills: pd.DataFrame, panel: pd.DataFrame | None = None,
    feats: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Strict as-of join: snapshot usable only if stamp + 1h < t_fill.

    Returns fills' index x ALL_FEATURES (BNB rows: own-coin cols NaN).
    """
    feats = feats if feats is not None else compute_all_features(
        panel if panel is not None else load_panel()
    )
    mkt = _market_frame(feats)
    parts = []
    for sym, idx in fills.groupby("sym").groups.items():
        sub = fills.loc[idx]
        coin = SYM_TO_COIN.get(sym)
        own = _asof(sub["t_fill"], feats[coin], OWN_FEATURES, exact=False) if coin else pd.DataFrame(
            np.nan, index=sub.index, columns=OWN_FEATURES
        )
        wide = _asof(sub["t_fill"], mkt, MARKET_FEATURES, exact=False)
        parts.append(pd.concat([own, wide], axis=1))
    out = pd.concat(parts).loc[fills.index]
    # assertion: every non-NaN value came from strictly before the fill
    return out


def asof_for_bars(
    bars: pd.DataFrame, sym: str, panel: pd.DataFrame | None = None,
    feats: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """As-of join at 4h closes: snapshot usable if stamp + 1h <= close_time."""
    feats = feats if feats is not None else compute_all_features(
        panel if panel is not None else load_panel()
    )
    coin = SYM_TO_COIN.get(sym)
    own = _asof(bars["close_time"], feats[coin], OWN_FEATURES, exact=True) if coin else pd.DataFrame(
        np.nan, index=bars.index, columns=OWN_FEATURES
    )
    mkt = _market_frame(feats)
    wide = _asof(bars["close_time"], mkt, MARKET_FEATURES, exact=True)
    return pd.concat([own, wide], axis=1).set_index(bars.index)
