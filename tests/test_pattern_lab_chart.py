import time

import numpy as np
import pandas as pd
import pytest

from agentic_alpha_lab.patterns import chart
from agentic_alpha_lab.patterns.common import assert_causal, load_bars


def _bars_from_close(close, wick=0.3, start="2021-01-01", freq="h"):
    close = np.asarray(close, float)
    n = len(close)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    t = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open_time": t, "open": open_, "high": high, "low": low,
                         "close": close, "volume": 1.0})


def _ctrl(points, n, start="2021-01-01", freq="h", wick=0.3):
    """Piecewise-linear close through (index, price) control points; no spurious pivots."""
    idx = [p[0] for p in points]
    px = [p[1] for p in points]
    xs = np.arange(n)
    close = np.interp(xs, idx, px).astype(float)
    return _bars_from_close(close, wick=wick, start=start, freq=freq)


def _ramp(n, a, b):
    return np.linspace(a, b, n)


def test_contract_dtypes_prefix():
    bars = _bars_from_close(100 + np.cumsum(np.random.default_rng(0).normal(0, 0.5, 200)))
    f = chart.compute(bars)
    e = chart.events(bars)
    assert list(f.index) == list(bars.index) and list(e.index) == list(bars.index)
    assert all(c.startswith("chp_") for c in list(f.columns) + list(e.columns))
    assert all(str(dt) == "float64" for dt in f.dtypes)
    assert all(str(dt) == "int8" for dt in e.dtypes)
    assert set(e.to_numpy().ravel().tolist()) <= {-1, 0, 1}


def test_causal_real_1h_4h_1d():
    try:
        b1 = load_bars("1h").iloc[:3000]
        b4 = load_bars("4h")
        bd = load_bars("1d")
    except FileNotFoundError:
        pytest.skip("local data not present")
    assert_causal(chart.events, b1)
    assert_causal(chart.compute, b1)
    assert_causal(chart.events, b4)
    assert_causal(chart.compute, b4)
    assert_causal(chart.events, bd)
    assert_causal(chart.compute, bd)


def test_fractal_pivot_hidden_until_confirmation():
    bars = _ctrl([(0, 100.0), (14, 100.0), (20, 110.0), (26, 100.0), (39, 100.0)], 40)
    sm = chart._fractal(bars["high"].to_numpy(), bars["low"].to_numpy(), 2)
    # small pivot at 20 (high bar may shift by wick; find actual max bar)
    assert len(sm["hidx"]) >= 1
    piv = int(sm["hidx"][0])
    conf = int(sm["hconf"][0])
    assert conf == piv + 2
    assert np.isnan(sm["hp"][conf - 1]) or sm["hp"][conf - 1] != bars["high"].iloc[piv]
    assert sm["hp"][conf] == pytest.approx(bars["high"].iloc[piv])
    lg = chart._fractal(bars["high"].to_numpy(), bars["low"].to_numpy(), 5)
    assert len(lg["hidx"]) >= 1
    assert int(lg["hconf"][0]) == int(lg["hidx"][0]) + 5


def test_zigzag_confirms_only_on_reversal():
    n = 60
    c = np.concatenate([_ramp(30, 100, 112), _ramp(30, 112, 98)])
    bars = _bars_from_close(c, wick=0.1)
    zz = chart._zigzag(bars["high"].to_numpy(), bars["low"].to_numpy(),
                       bars["close"].to_numpy(), chart._atr(
                           bars["high"].to_numpy(), bars["low"].to_numpy(),
                           bars["close"].to_numpy()))
    assert len(zz["idx"]) >= 1
    # top pivot index is near 29 but confirmation must be strictly later
    top = zz["idx"][np.argmax(zz["px"])]
    top_conf = zz["conf"][np.argmax(zz["px"])]
    assert top_conf > top


def test_double_top_and_bottom():
    bars = _ctrl([(0, 100.0), (14, 100.0), (20, 110.0), (26, 105.0), (31, 100.0),
                  (37, 105.0), (42, 110.0), (48, 104.0), (53, 99.0), (58, 96.0), (79, 96.0)], 80)
    e = chart.events(bars)
    seg = e["chp_double_top"].to_numpy()
    assert (seg[45:] == -1).any(), "double top must fire after neckline break"
    assert (seg[:44] == -1).sum() == 0, "must not fire before second-peak breakout"
    bars2 = _ctrl([(0, 100.0), (14, 100.0), (20, 90.0), (26, 95.0), (31, 100.0),
                   (37, 95.0), (42, 90.0), (48, 96.0), (53, 101.0), (58, 104.0), (79, 104.0)], 80)
    e2 = chart.events(bars2)
    assert (e2["chp_double_bottom"].to_numpy()[45:] == 1).any()


def test_triple_top_and_bottom():
    bars = _ctrl([(0, 100.0), (10, 100.0), (15, 110.0), (20, 105.0), (24, 100.0),
                  (28, 105.0), (32, 110.0), (37, 105.0), (41, 100.0), (45, 105.0),
                  (49, 110.0), (55, 104.0), (60, 99.0), (65, 96.0), (89, 96.0)], 90)
    e = chart.events(bars)
    assert (e["chp_triple_top"].to_numpy()[55:] == -1).any()
    bars2 = _ctrl([(0, 100.0), (10, 100.0), (15, 90.0), (20, 95.0), (24, 100.0),
                   (28, 95.0), (32, 90.0), (37, 95.0), (41, 100.0), (45, 95.0),
                   (49, 90.0), (55, 96.0), (60, 101.0), (65, 104.0), (89, 104.0)], 90)
    e2 = chart.events(bars2)
    assert (e2["chp_triple_bottom"].to_numpy()[55:] == 1).any()


def test_head_shoulders_and_inverse():
    bars = _ctrl([(0, 100.0), (10, 100.0), (15, 110.0), (20, 105.0), (24, 100.0),
                  (28, 106.0), (32, 113.0), (37, 106.0), (41, 100.0), (45, 105.0),
                  (49, 110.0), (55, 104.0), (60, 99.0), (65, 96.0), (89, 96.0)], 90)
    e = chart.events(bars)
    assert (e["chp_head_shoulders"].to_numpy()[55:] == -1).any()
    bars2 = _ctrl([(0, 100.0), (10, 100.0), (15, 90.0), (20, 95.0), (24, 100.0),
                   (28, 94.0), (32, 87.0), (37, 94.0), (41, 100.0), (45, 95.0),
                   (49, 90.0), (55, 96.0), (60, 101.0), (65, 104.0), (89, 104.0)], 90)
    e2 = chart.events(bars2)
    assert (e2["chp_inv_head_shoulders"].to_numpy()[55:] == 1).any()


def test_triangles():
    # ascending: flat highs 110, rising lows 100 -> 104, break up
    bars = _ctrl([(0, 100.0), (10, 100.0), (20, 110.0), (25, 100.0), (32, 106.0),
                  (40, 110.0), (45, 104.0), (50, 107.0), (56, 112.5), (79, 112.5)], 80)
    e = chart.events(bars)
    assert (e["chp_asc_triangle"].to_numpy()[54:] == 1).any()
    # descending mirror
    bars2 = _ctrl([(0, 110.0), (10, 110.0), (20, 100.0), (25, 110.0), (32, 104.0),
                   (40, 100.0), (45, 106.0), (50, 103.0), (56, 97.0), (79, 97.0)], 80)
    e2 = chart.events(bars2)
    assert (e2["chp_desc_triangle"].to_numpy()[54:] == -1).any()
    # symmetric: falling highs, rising lows, break up
    bars3 = _ctrl([(0, 100.0), (10, 100.0), (20, 112.0), (25, 100.0), (32, 107.0),
                   (40, 110.0), (45, 103.0), (50, 107.0), (56, 112.5), (79, 112.5)], 80)
    e3 = chart.events(bars3)
    assert (e3["chp_sym_triangle"].to_numpy()[54:] != 0).any()


def test_rectangle_break():
    rng = np.random.default_rng(3)
    base = 102 + rng.normal(0, 0.4, 60)
    base = np.clip(base, 100.5, 103.5)
    c = np.concatenate([100 + np.linspace(0, 2, 10), base, np.linspace(102, 107, 10)])
    e = chart.events(_bars_from_close(c, wick=0.2))
    assert (e["chp_rectangle_break"].to_numpy()[-12:] != 0).any()


def test_bull_bear_flag():
    pole = np.linspace(100, 112, 21)
    consol = 112.0 + np.random.default_rng(4).normal(0, 0.08, 10)
    c = np.concatenate([pole, consol, [114.5, 115.0, 115.5, 116.0]])
    e = chart.events(_bars_from_close(c, wick=0.15))
    assert (e["chp_bull_flag"].to_numpy() == 1).any()
    pole2 = np.linspace(112, 100, 21)
    consol2 = 100.0 + np.random.default_rng(5).normal(0, 0.08, 10)
    c2 = np.concatenate([pole2, consol2, [97.5, 97.0, 96.5, 96.0]])
    e2 = chart.events(_bars_from_close(c2, wick=0.15))
    assert (e2["chp_bear_flag"].to_numpy() == -1).any()


def test_wedges():
    n = 70
    i = np.arange(n)
    low = 100 + 0.20 * i
    high = low + (6 - 0.05 * i)
    close = (high + low) / 2
    c = close.copy()
    c[-6:] = np.linspace(c[-6], low[-6] - 1.5, 6)  # breakdown
    bars = _bars_from_close(c, wick=0.1)
    # overwrite to keep the wedge geometry exact
    bars["low"] = np.minimum(bars["low"].to_numpy(), np.concatenate([low[:-6], c[-6:] - 0.1]))
    bars["high"] = np.maximum(bars["high"].to_numpy(), np.concatenate([high[:-6], c[-6:] + 0.1]))
    e = chart.events(bars)
    assert (e["chp_rising_wedge"].to_numpy()[-10:] == -1).any()
    # falling wedge: both falling, upper (resistance) steeper -> converging down
    high2 = 114 - 0.20 * i
    low2 = 106 - 0.10 * i
    close2 = (high2 + low2) / 2
    c2 = close2.copy()
    c2[-6:] = np.linspace(c2[-6], high2[-6] + 1.5, 6)
    bars2 = _bars_from_close(c2, wick=0.1)
    bars2["low"] = np.minimum(bars2["low"].to_numpy(), np.concatenate([low2[:-6], c2[-6:] - 0.1]))
    bars2["high"] = np.maximum(bars2["high"].to_numpy(), np.concatenate([high2[:-6], c2[-6:] + 0.1]))
    e2 = chart.events(bars2)
    assert (e2["chp_falling_wedge"].to_numpy()[-10:] == 1).any()


def test_sr_break_and_retest():
    bars = _ctrl([(0, 100.0), (10, 100.0), (18, 106.0), (25, 110.0), (30, 107.0),
                  (35, 106.0), (40, 111.5), (44, 110.1), (46, 109.9), (48, 110.4),
                  (52, 111.5), (69, 111.5)], 70)
    e = chart.events(bars)
    br = e["chp_sr_break"].to_numpy()
    assert (br[34:46] == 1).any()
    tb = int(np.where(br == 1)[0][0])
    assert (e["chp_sr_retest"].to_numpy()[tb + 1:tb + 11] == 1).any()


def test_donchian_breaks():
    c = np.concatenate([100 + np.random.default_rng(6).normal(0, 0.3, 60),
                        np.linspace(100, 106, 8)])
    e = chart.events(_bars_from_close(c, wick=0.15))
    assert (e["chp_donchian20_break"].to_numpy()[-10:] == 1).any()
    assert (e["chp_donchian55_break"].to_numpy()[-10:] == 1).any()


def test_compute_features_sane():
    bars = _ctrl([(0, 100.0), (14, 100.0), (20, 110.0), (26, 105.0), (31, 100.0),
                  (37, 105.0), (42, 110.0), (48, 104.0), (53, 99.0), (58, 96.0), (79, 96.0)], 80)
    f = chart.compute(bars)
    assert np.isfinite(f["chp_atr"].to_numpy()[30:]).all()
    # distance to large pivot high negative after breakdown region sampled sanely
    assert np.isfinite(f["chp_dist_piv_high_large_atr"].to_numpy()[60:]).all()
    assert (f["chp_bars_since_piv_high_large"].to_numpy()[60:] >= 0).all()
    assert np.nanmax(f["chp_hh_count_3"].to_numpy()) <= 3
    assert np.nanmax(f["chp_ll_count_3"].to_numpy()) <= 3


def test_full_1h_under_60s():
    try:
        bars = load_bars("1h")
    except FileNotFoundError:
        pytest.skip("local data not present")
    t0 = time.time()
    chart.events(bars)
    assert time.time() - t0 < 60
    t0 = time.time()
    chart.compute(bars)
    assert time.time() - t0 < 60
