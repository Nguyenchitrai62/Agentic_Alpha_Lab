"""W12 ma_levels tests: contract, causality, hand-checked synthetic cases."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common, ma_levels


def _mk_1h_2015(closes, highs=None, lows=None):
    n = len(closes)
    t = pd.date_range("2015-01-01", periods=n, freq="1h", tz="UTC")
    closes = np.asarray(closes, float)
    highs = np.asarray(highs, float) if highs is not None else closes + 1.0
    lows = np.asarray(lows, float) if lows is not None else closes - 1.0
    return pd.DataFrame({
        "open_time": t,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.ones(n),
        "close_time": t + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
    })


def test_prefix_index_dtypes():
    bars = common.load_bars("1h").iloc[:2000]
    f = ma_levels.compute(bars)
    e = ma_levels.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("msr_") for c in f.columns)
    assert all(c.startswith("msr_") for c in e.columns)
    assert set(np.unique(e.to_numpy())) <= {-1, 0, 1}
    assert (e.dtypes == np.int8).all()
    assert all(str(d) == "float64" for d in f.dtypes)
    # spot check: same-TF distance column present and finite late in sample
    assert np.isfinite(f["msr_dist_1h_sma20"].iloc[-1])


def test_causal_real_4h_1d_opened_year():
    # include_opened_year=True allowed ONLY for this causality test
    for tf in ("4h", "1d"):
        bars = common.load_bars(tf, include_opened_year=True)
        common.assert_causal(ma_levels.compute, bars)
        common.assert_causal(ma_levels.events, bars)


def test_flat_series_handchecked():
    # constant 100: previous-bar SMA/EMA = 100, ATR = 2, ribbon flat
    n = 250
    bars = _mk_1h_2015(np.full(n, 100.0),
                       highs=np.full(n, 101.0), lows=np.full(n, 99.0))
    f = ma_levels.compute(bars)
    i = n - 1
    assert f["msr_dist_1h_sma20"].iloc[i] == 0.0
    assert f["msr_dist_1h_ema200"].iloc[i] == 0.0
    assert f["msr_touch50_1h_sma20"].iloc[i] == 50.0
    assert f["msr_ribbon_1h_sma"].iloc[i] == 0.0
    assert f["msr_near_sup_dist_atr"].iloc[i] == 0.0
    assert f["msr_near_res_dist_atr"].iloc[i] == 0.0
    assert f["msr_near_sup_tf"].iloc[i] == 1.0  # 1h code
    # 8 same-TF levels (other TFs pre-date external history -> NaN)
    assert f["msr_confluence"].iloc[i] == 8.0
    # no higher-TF data in 2015: other-TF distances are NaN
    assert f["msr_dist_4h_sma50"].isna().all()
    # flat tape: no directional events on the 1h sma family
    e = ma_levels.events(bars)
    assert (e["msr_ev_1h_sma_bounce_support"] == 0).all()
    assert (e["msr_ev_1h_sma_break_down"] == 0).all()


def test_uptrend_sma_distance_and_ribbon_handchecked():
    # closes rise 1/bar: SMA20prev = close - 10.5, TR = 1.5 -> dist = 7.0
    n = 250
    closes = 100.0 + np.arange(n)
    bars = _mk_1h_2015(closes, highs=closes + 0.5, lows=closes - 0.5)
    f = ma_levels.compute(bars)
    i = n - 1
    assert abs(f["msr_dist_1h_sma20"].iloc[i] - 7.0) < 1e-6
    assert f["msr_ribbon_1h_sma"].iloc[i] == 4.0
    assert f["msr_ribbon_1h_ema"].iloc[i] == 4.0
    assert f["msr_slope_1h_sma20"].iloc[i] > 0
    # price above every same-TF level: no support strictly below? support==some
    # level below, resistance NaN only if no level above (uptrend: levels lag)
    assert f["msr_near_sup_dist_atr"].iloc[i] > 0


def test_bounce_then_break_handchecked():
    # rows 0-19: 100; rows 20-29: 110; row 30 dips to level, closes above;
    # row 31 closes far below -> break_down. SMA20prev[30] = 105 exactly.
    closes = np.array([100.0] * 20 + [110.0] * 10 + [106.0, 90.0])
    highs = np.array([101.0] * 20 + [111.0] * 10 + [112.0, 106.0])
    lows = np.array([99.0] * 20 + [109.0] * 10 + [99.0, 89.0])
    bars = _mk_1h_2015(closes, highs=highs, lows=lows)
    assert len(bars) == 32
    e = ma_levels.events(bars)
    # family level at row 30 = median(105, nan, nan, nan) = 105
    assert e["msr_ev_1h_sma_bounce_support"].iloc[30] == 1
    assert e["msr_ev_1h_sma_reject_resistance"].iloc[30] == 0
    assert e["msr_ev_1h_sma_break_down"].iloc[31] == -1
    assert e["msr_ev_1h_sma_bounce_support"].iloc[31] == 0
    # nothing fires before the setup completes
    assert (e["msr_ev_1h_sma_bounce_support"].iloc[:30] == 0).all()


def test_reject_handchecked():
    # mirror: rows 0-19: 100; rows 20-29: 90; row 30 spikes to level 95,
    # closes below -> reject_resistance -1. SMA20prev[30] = 95 exactly.
    closes = np.array([100.0] * 20 + [90.0] * 10 + [94.0])
    highs = np.array([101.0] * 20 + [91.0] * 10 + [101.0])
    lows = np.array([99.0] * 20 + [89.0] * 10 + [88.0])
    bars = _mk_1h_2015(closes, highs=highs, lows=lows)
    e = ma_levels.events(bars)
    assert e["msr_ev_1h_sma_reject_resistance"].iloc[30] == -1
    assert e["msr_ev_1h_sma_bounce_support"].iloc[30] == 0


def test_no_same_bar_ma():
    # level at row t must not use close[t]: appending a spike changes only
    # later rows, never the level tested inside earlier rows.
    closes = np.full(60, 100.0)
    bars = _mk_1h_2015(closes)
    f1 = ma_levels.compute(bars)
    closes2 = closes.copy()
    closes2[-1] = 200.0
    bars2 = _mk_1h_2015(closes2)
    f2 = ma_levels.compute(bars2)
    pd.testing.assert_frame_equal(
        f1.iloc[:-1].reset_index(drop=True),
        f2.iloc[:-1].reset_index(drop=True),
        check_dtype=False,
    )
