"""Tests for oc_optflow (research/tournament/oc_optflow). Causality + hand-checked synthetic."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_optflow"))
import compute_optflow as C


def _syn_rows():
    # hour H0, index 100. Rows: OTM put K=90 (m=-0.10, DTE 5d) buy 2 / sell 0.5, blk 1
    # OTM call K=110 (m=+0.10) sell-heavy; ITM put K=105 excluded; far OTM K=50 excluded;
    # DTE 0.5d excluded; DTE 20d excluded.
    H0 = pd.Timestamp("2021-03-01 00:00", tz="UTC")
    E5 = pd.Timestamp("2021-03-06 00:00", tz="UTC")
    E0 = pd.Timestamp("2021-03-01 12:00", tz="UTC")
    E20 = pd.Timestamp("2021-03-21 00:00", tz="UTC")
    return pd.DataFrame([
        {"hour": H0, "instrument_name": "a", "expiry": E5, "strike": 90.0, "cp": "P",
         "n": 1, "sum_amount": 1.0, "vwap_price": 0.1, "vwap_price_usd": 10.0, "vwap_iv": 50.0,
         "min_price": 0.1, "max_price": 0.1, "vwap_index": 100.0,
         "taker_buy_amount": 2.0, "taker_sell_amount": 0.5, "block_amount": 1.0},
        {"hour": H0, "instrument_name": "b", "expiry": E5, "strike": 110.0, "cp": "C",
         "n": 1, "sum_amount": 1.0, "vwap_price": 0.1, "vwap_price_usd": 10.0, "vwap_iv": 50.0,
         "min_price": 0.1, "max_price": 0.1, "vwap_index": 100.0,
         "taker_buy_amount": 1.0, "taker_sell_amount": 4.0, "block_amount": 0.5},
        {"hour": H0, "instrument_name": "c", "expiry": E5, "strike": 105.0, "cp": "P",  # ITM put
         "n": 1, "sum_amount": 1.0, "vwap_price": 0.1, "vwap_price_usd": 10.0, "vwap_iv": 50.0,
         "min_price": 0.1, "max_price": 0.1, "vwap_index": 100.0,
         "taker_buy_amount": 9.0, "taker_sell_amount": 0.0, "block_amount": 9.0},
        {"hour": H0, "instrument_name": "d", "expiry": E5, "strike": 50.0, "cp": "P",  # too far
         "n": 1, "sum_amount": 1.0, "vwap_price": 0.1, "vwap_price_usd": 10.0, "vwap_iv": 50.0,
         "min_price": 0.1, "max_price": 0.1, "vwap_index": 100.0,
         "taker_buy_amount": 9.0, "taker_sell_amount": 0.0, "block_amount": 9.0},
        {"hour": H0, "instrument_name": "e", "expiry": E0, "strike": 90.0, "cp": "P",  # DTE<1
         "n": 1, "sum_amount": 1.0, "vwap_price": 0.1, "vwap_price_usd": 10.0, "vwap_iv": 50.0,
         "min_price": 0.1, "max_price": 0.1, "vwap_index": 100.0,
         "taker_buy_amount": 9.0, "taker_sell_amount": 0.0, "block_amount": 9.0},
        {"hour": H0, "instrument_name": "f", "expiry": E20, "strike": 90.0, "cp": "P",  # DTE>9
         "n": 1, "sum_amount": 1.0, "vwap_price": 0.1, "vwap_price_usd": 10.0, "vwap_iv": 50.0,
         "min_price": 0.1, "max_price": 0.1, "vwap_index": 100.0,
         "taker_buy_amount": 9.0, "taker_sell_amount": 0.0, "block_amount": 9.0},
    ])


def test_handchecked_filter_and_notional():
    sel = C.select_informed(_syn_rows())
    # only rows a (OTM put) and b (OTM call) kept
    assert sel["keep"].tolist() == [True, True, False, False, False, False]
    agg = C.aggregate_hourly(sel)
    H0 = pd.Timestamp("2021-03-01 00:00", tz="UTC")
    # NPB = (2.0-0.5)*100 = 150; NCB = (1.0-4.0)*100 = -300
    assert abs(agg.loc[H0, "NPB"] - 150.0) < 1e-9
    assert abs(agg.loc[H0, "NCB"] - (-300.0)) < 1e-9
    # BLK = puts 1.0*100 - calls 0.5*100 = 50
    assert abs(agg.loc[H0, "BLK"] - 50.0) < 1e-9


def test_handchecked_signals_math():
    # 800h of constant flow: net = NCB-NPB = 5-(-5) = 10, blk = 2, |NCB|+|NPB| = 10/h.
    idx = pd.date_range("2021-01-01", periods=800, freq="h", tz="UTC")
    hourly = pd.DataFrame({"NPB": -5.0, "NCB": 5.0, "BLK": 2.0}, index=idx)
    roll = C.signals_from_hourly(hourly)
    T = pd.DatetimeIndex([idx[-1] + pd.Timedelta(hours=1)])
    F = C.signals_at(roll, T)
    # R24 = 24*10 = 240, R4 = 40, Rblk = 48, D = 10
    assert abs(F["F1"].iloc[0] - 24.0) < 1e-9
    assert abs(F["F3"].iloc[0] - 4.0) < 1e-9
    assert abs(F["F2"].iloc[0] - 4.8) < 1e-9


def test_causality_future_hours_do_not_leak():
    # F(T) must not change when hours at/after T change.
    idx = pd.date_range("2021-02-01", periods=800, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    base = pd.DataFrame({"NPB": rng.normal(0, 1, 800), "NCB": rng.normal(0, 1, 800),
                         "BLK": rng.normal(0, 1, 800)}, index=idx)
    T = pd.DatetimeIndex([idx[700]])
    F0 = C.signals_at(C.signals_from_hourly(base), T)
    mod = base.copy()
    mod.iloc[700:] = 999.0  # hours at/after T-1h+1 ... (index 700 = T-1h? T=idx[700], key=T-1h=idx[699])
    mod.iloc[699:] = 999.0  # also nuke the key hour boundary: key must stay -> restore below
    mod.iloc[699] = base.iloc[699]  # restore: eligible set is idx[699-719..699]; keep it
    # nuke only strictly-future hours (> T-1h)
    mod2 = base.copy()
    mod2.iloc[700:] = 999.0
    F2 = C.signals_at(C.signals_from_hourly(mod2), T)
    for c in ("F1", "F2", "F3"):
        assert abs(float(F0[c].iloc[0]) - float(F2[c].iloc[0])) < 1e-9, c
    # truncation: T before warmup -> NaN (D needs 360h)
    Tearly = pd.DatetimeIndex([idx[100]])
    Fe = C.signals_at(C.signals_from_hourly(base), Tearly)
    assert not np.isfinite(float(Fe["F1"].iloc[0]))
