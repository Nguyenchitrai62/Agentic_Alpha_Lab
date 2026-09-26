import time

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import candles, common


def _mk(rows):
    t = pd.date_range("2020-01-01", periods=len(rows), freq="h", tz="UTC")
    b = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    b.insert(0, "open_time", t)
    b["volume"] = 1.0
    return b


def _trend(n, start, step):
    closes = [start - i * step for i in range(n)]
    return [
        (c + 0.1, c + 0.5, c - 0.5, c) for c in closes
    ]


def _uptrend(n, start, step):
    closes = [start + i * step for i in range(n)]
    return [
        (c - 0.1, c + 0.5, c - 0.5, c) for c in closes
    ]


def test_prefix_index_dtypes():
    bars = common.load_bars("4h").iloc[:500]
    f = candles.compute(bars)
    e = candles.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("cdl_") for c in f.columns)
    assert all(c.startswith("cdl_") for c in e.columns)
    assert set(e.values.ravel()) <= {-1, 0, 1}
    assert (e.dtypes == np.int8).all()
    assert all(str(d) == "float64" for d in f.dtypes)


def test_causal_real_data():
    for tf, n in (("1h", 3000), ("4h", 2000), ("1d", 1500)):
        bars = common.load_bars(tf).iloc[:n]
        common.assert_causal(candles.compute, bars)
        common.assert_causal(candles.events, bars)


def test_perf_full_1h():
    bars = common.load_bars("1h")
    t0 = time.time()
    candles.compute(bars)
    candles.events(bars)
    assert time.time() - t0 < 60


def test_doji_family_and_spinning():
    base = _trend(20, 120, 1.0)
    rows = base + [
        (100.0, 100.5, 99.5, 100.05),  # doji
        (100.0, 100.1, 99.0, 100.05),  # dragonfly
        (100.0, 101.0, 99.95, 100.05),  # gravestone
        (100.0, 101.0, 99.0, 100.05),  # long-legged
        (100.0, 100.6, 99.4, 100.2),  # spinning top
    ]
    bars = _mk(rows)
    p = candles.compute(bars)
    assert p["cdl_doji"].iloc[20] == 1.0
    assert p["cdl_dragonfly_doji"].iloc[21] == 1.0
    assert p["cdl_gravestone_doji"].iloc[22] == 1.0
    assert p["cdl_longlegged_doji"].iloc[23] == 1.0
    assert p["cdl_spinning_top"].iloc[24] == 1.0
    e = candles.events(bars)
    assert e["cdl_dragonfly_doji"].iloc[21] == 1
    assert e["cdl_gravestone_doji"].iloc[22] == -1


def test_hammer_hanging_trend():
    down = _trend(20, 120, 1.0)
    shape = (100.0, 100.2, 99.0, 100.1)
    bars = _mk(down + [shape])
    p = candles.compute(bars)
    assert p["cdl_hammer"].iloc[20] == 1.0
    assert p["cdl_hanging_man"].iloc[20] == 0.0
    up = _uptrend(20, 80, 1.0)
    bars2 = _mk(up + [shape])
    p2 = candles.compute(bars2)
    assert p2["cdl_hanging_man"].iloc[20] == 1.0
    assert p2["cdl_hammer"].iloc[20] == 0.0
    inv = (100.0, 101.0, 99.9, 100.1)
    bars3 = _mk(down + [inv])
    assert candles.compute(bars3)["cdl_inverted_hammer"].iloc[20] == 1.0
    bars4 = _mk(up + [(100.0, 101.0, 99.9, 99.9)])
    assert candles.compute(bars4)["cdl_shooting_star"].iloc[20] == 1.0


def test_marubozu_pinbar():
    base = _trend(20, 120, 1.0)
    bars = _mk(base + [(100.0, 100.52, 99.99, 100.5)])
    assert candles.compute(bars)["cdl_marubozu_bull"].iloc[20] == 1.0
    bars = _mk(base + [(100.5, 100.52, 99.98, 100.0)])
    assert candles.compute(bars)["cdl_marubozu_bear"].iloc[20] == 1.0
    bars = _mk(base + [(100.0, 100.2, 99.0, 100.1)])
    assert candles.compute(bars)["cdl_pinbar_bull"].iloc[20] == 1.0
    bars = _mk(base + [(100.0, 101.0, 99.8, 99.9)])
    assert candles.compute(bars)["cdl_pinbar_bear"].iloc[20] == 1.0


def test_engulfing_harami():
    base = _trend(20, 120, 1.0)
    bars = _mk(base + [(101.0, 101.5, 99.5, 100.0), (99.9, 101.6, 99.8, 101.1)])
    p = candles.compute(bars)
    assert p["cdl_engulfing_bull"].iloc[21] == 1.0
    bars = _mk(_uptrend(20, 80, 1.0) + [(100.0, 101.5, 99.5, 101.0), (101.1, 101.6, 99.4, 99.9)])
    assert candles.compute(bars)["cdl_engulfing_bear"].iloc[21] == 1.0
    bars = _mk(base + [(102.0, 102.5, 99.5, 100.0), (100.2, 101.0, 100.1, 100.8)])
    assert candles.compute(bars)["cdl_harami_bull"].iloc[21] == 1.0
    bars = _mk(_uptrend(20, 80, 1.0) + [(100.0, 102.5, 99.5, 102.0), (101.2, 101.5, 100.5, 100.8)])
    assert candles.compute(bars)["cdl_harami_bear"].iloc[21] == 1.0


def test_piercing_dark_cloud():
    base = _trend(20, 120, 1.0)
    bars = _mk(base + [(102.0, 102.5, 99.5, 100.0), (99.5, 101.5, 99.0, 101.2)])
    assert candles.compute(bars)["cdl_piercing_line"].iloc[21] == 1.0
    bars = _mk(_uptrend(20, 80, 1.0) + [(100.0, 102.5, 99.5, 102.0), (102.5, 103.0, 100.0, 100.8)])
    assert candles.compute(bars)["cdl_dark_cloud"].iloc[21] == 1.0


def test_stars_and_soldiers_crows():
    base = _trend(20, 120, 1.0)
    rows = base + [(102.0, 102.5, 99.5, 100.0), (99.7, 100.0, 99.4, 99.8), (99.7, 102.0, 99.6, 101.5)]
    assert candles.compute(_mk(rows))["cdl_morning_star"].iloc[22] == 1.0
    up = _uptrend(20, 80, 1.0)
    rows = up + [(100.0, 102.5, 99.5, 101.0), (101.2, 101.8, 101.0, 101.4), (101.5, 102.0, 99.0, 100.0)]
    assert candles.compute(_mk(rows))["cdl_evening_star"].iloc[22] == 1.0
    rows = base + [(100.0, 100.8, 99.9, 100.7), (100.2, 101.3, 100.1, 101.2), (100.7, 101.8, 100.6, 101.7)]
    assert candles.compute(_mk(rows))["cdl_three_white_soldiers"].iloc[22] == 1.0
    rows = up + [(102.0, 102.1, 101.2, 101.3), (101.8, 101.9, 100.7, 100.8), (101.3, 101.4, 100.2, 100.3)]
    assert candles.compute(_mk(rows))["cdl_three_black_crows"].iloc[22] == 1.0


def test_tweezer_inside_outside():
    up = _uptrend(20, 80, 1.0)
    rows = up + [(100.0, 102.0, 99.5, 101.5), (101.4, 102.0, 100.0, 100.5)]
    assert candles.compute(_mk(rows))["cdl_tweezer_top"].iloc[21] == 1.0
    down = _trend(20, 120, 1.0)
    rows = down + [(101.0, 102.0, 100.0, 100.5), (100.6, 101.5, 100.0, 101.2)]
    assert candles.compute(_mk(rows))["cdl_tweezer_bottom"].iloc[21] == 1.0
    rows = down + [(100.0, 102.0, 99.0, 101.0), (100.5, 101.5, 99.5, 101.0)]
    assert candles.compute(_mk(rows))["cdl_inside_bar"].iloc[21] == 1.0
    rows = down + [(100.0, 101.0, 99.5, 100.5), (100.0, 102.0, 99.0, 101.0)]
    assert candles.compute(_mk(rows))["cdl_outside_bar"].iloc[21] == 1.0


def test_events_direction_and_continuous():
    bars = common.load_bars("1d")
    e = candles.events(bars)
    f = candles.compute(bars)
    # bullish events only +1, bearish only -1
    assert set(e["cdl_hammer"].unique()) <= {0, 1}
    assert set(e["cdl_hanging_man"].unique()) <= {0, -1}
    assert set(e["cdl_engulfing_bull"].unique()) <= {0, 1}
    assert set(e["cdl_engulfing_bear"].unique()) <= {0, -1}
    for c in ["cdl_body_range", "cdl_clv", "cdl_gap_atr", "cdl_body_sum_3_atr"]:
        assert c in f.columns
    assert ((f["cdl_clv"].dropna() >= 0) & (f["cdl_clv"].dropna() <= 1)).all()
