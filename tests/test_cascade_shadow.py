"""Tests for scripts/cascade_shadow.py (pure helpers only, no network)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cascade_shadow as cs


def test_close_returns_hand_checked():
    c = [100.0, 110.0, 99.0]
    r = cs.close_returns(c)
    assert np.isnan(r[0])
    assert abs(r[1] - np.log(1.1)) < 1e-12
    assert abs(r[2] - np.log(0.9)) < 1e-12


def test_trailing_sigma_excludes_tested_bar():
    # constant returns -> trailing window has zero variance -> NaN (var>0 required)
    r = np.full(200, 0.001)
    r[0] = np.nan
    sig = cs.trailing_sigma(r, window=120, min_periods=120)
    # first computable index needs 120 finite priors: sig[121] uses r[1..120]
    assert np.isnan(sig[0])
    # a spike at i must not enter SIG[i] (excluded) but enters SIG[i+1]
    rng = np.random.default_rng(11)
    r2 = rng.normal(0, 0.01, 300)
    r2[150] = 0.5
    s = cs.trailing_sigma(r2, window=120, min_periods=120)
    assert np.isfinite(s[150])  # window before the spike
    assert s[151] > s[150]  # spike now inside the window


def test_triggers_strict_and_nan_never_fires():
    c = [100.0, 100.0, 100.0]
    assert not cs.triggers_of(c).any()  # zero sigma -> never fires
    assert not cs.triggers_of([np.nan, 1.0, 2.0]).any()


def test_boosted_mask_window_edges():
    day = cs.NS_DAY
    tc = np.array([1_000 * day], dtype=np.int64)
    # strictly after tc, up to and including +7d
    assert not cs.boosted_mask(np.array([1_000 * day], dtype=np.int64), tc, 7)[0]
    assert cs.boosted_mask(np.array([1_000 * day + 1], dtype=np.int64), tc, 7)[0]
    assert cs.boosted_mask(np.array([1_007 * day], dtype=np.int64), tc, 7)[0]
    assert not cs.boosted_mask(np.array([1_007 * day + 1], dtype=np.int64), tc, 7)[0]
    assert not cs.boosted_mask(np.array([999 * day], dtype=np.int64), tc, 7)[0]
    # empty triggers -> never boosted
    assert not cs.boosted_mask(np.array([1_001 * day], dtype=np.int64),
                               np.array([], dtype=np.int64), 7)[0]


def test_stack_mult_nonfinite_leg_is_one():
    assert cs.stack_mult(1.5, 1.25) == 1.875
    assert cs.stack_mult(1.5, float("nan")) == 1.5
    assert cs.stack_mult(float("nan"), 0.75) == 0.75
    assert cs.stack_mult(None, None) == 1.0


def test_targets_shift_and_prospective():
    now = pd.Timestamp("2026-09-10 05:00", tz="UTC")
    t = dict(cs.targets_for_window(now, 1))
    # single target: the floored hour itself
    assert len(t) == 1
    s, T = cs.targets_for_window(now, 1)[0]
    assert s == 5 % 4 and T == pd.Timestamp("2026-09-10 05:00", tz="UTC")
    assert cs.is_prospective(pd.Timestamp("2026-09-10 05:20", tz="UTC"),
                             pd.Timestamp("2026-09-10 05:00", tz="UTC"))
    assert not cs.is_prospective(pd.Timestamp("2026-09-10 05:31", tz="UTC"),
                                 pd.Timestamp("2026-09-10 05:00", tz="UTC"))


def test_build_shift_bars_aggregation():
    # 4 closed 1h klines 00..03 shift 0 -> one 4h bar open 00:00
    idx = pd.date_range("2026-09-01 00:00", periods=4, freq="h", tz="UTC")
    h1 = pd.DataFrame({"open_time": idx, "open": [1, 2, 3, 4], "high": [1, 2, 3, 5],
                       "low": [1, 1, 2, 3], "close": [1, 2, 3, 4], "volume": 1.0,
                       "quote_volume": 10.0,
                       "close_time": idx + pd.Timedelta(hours=1) - pd.Timedelta(seconds=1),
                       "closed": True})
    b = cs.build_shift_bars(h1, 0)
    assert len(b) == 1 and b["T"].iloc[0] == pd.Timestamp("2026-09-01 00:00", tz="UTC")
    assert b["close"].iloc[0] == 4 and b["n_h"].iloc[0] == 4
    # forming kline excluded
    h1f = h1.copy()
    h1f.loc[3, "closed"] = False
    b2 = cs.build_shift_bars(h1f, 0)
    assert len(b2) == 1 and b2["n_h"].iloc[0] == 3


def test_union_triggers_market_wide_per_shift():
    # one sym spiking, others flat: union tc boosts every coin at (shift, T)
    base = pd.date_range("2026-01-01", periods=400, freq="4h", tz="UTC")
    flat = pd.DataFrame({"T": base, "open": 100.0, "high": 100.0, "low": 100.0,
                         "close": 100.0, "volume": 1.0, "amount": 1.0, "n_h": 4})
    spike = flat.copy()
    spike.loc[300, "close"] = 130.0  # >4 sigma single-bar jump
    per = {"BTCUSDT": spike, "ETHUSDT": flat, "SOLUSDT": flat,
           "BNBUSDT": flat, "XRPUSDT": flat}
    trig = cs.union_triggers_ns(per, 0)
    assert len(trig) > 0
    tc = pd.to_datetime(trig, utc=True)
    # every sym shares the same window: a T 1 day after a trigger is boosted
    T = tc[0] + pd.Timedelta(days=1)
    assert cs.b7_mult_for(T, trig) == 1.5
    Tfar = tc[0] + pd.Timedelta(days=30)
    # far enough from ALL triggers -> 1.0 (unless a later trigger re-arms)
    m = cs.boosted_mask(np.array([pd.Timestamp(Tfar).value], dtype=np.int64), trig, 7)
    assert cs.b7_mult_for(Tfar, trig) == (1.5 if bool(m[0]) else 1.0)


def test_truncation_identical_on_kept_prefix():
    rng = np.random.default_rng(7)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, 600)))
    full = cs.triggers_of(closes)
    cut = cs.triggers_of(closes[:400])
    assert (full[:400] == cut).all()  # dropping later bars changes nothing kept
