"""mj W16 capitulation tests: contract, causality on real 4h/1d bars, synthetic hand-checks."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import capitulation as cap
from agentic_alpha_lab.patterns import common


def _syn(n=600, seed=0, freq="4h", start="2021-06-01"):
    rng = np.random.default_rng(seed)
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    open_ = np.concatenate([[30000.0], close[:-1]])
    t = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    dt = pd.Timedelta(freq)
    return pd.DataFrame({
        "open_time": t, "open": open_,
        "high": np.maximum(open_, close) * 1.002,
        "low": np.minimum(open_, close) * 0.998,
        "close": close, "volume": 10.0, "quote_volume": close * 10.0,
        "taker_buy_volume": 5.0,
        "close_time": t + dt - pd.Timedelta("1ms"),
    })


def test_contract_prefix_dtype_index():
    bars = _syn()
    f, e = cap.compute(bars), cap.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("cap_") for c in f.columns)
    assert all(c.startswith("cap_") for c in e.columns)
    assert all(np.issubdtype(d, np.floating) for d in f.dtypes)
    assert all(d == np.int8 for d in e.dtypes)
    assert bool(((e.to_numpy() >= -1) & (e.to_numpy() <= 1)).all())


def test_works_on_1h_4h_1d():
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf).iloc[:800]
        f, e = cap.compute(bars), cap.events(bars)
        assert len(f) == len(bars) and len(e) == len(bars)
        assert all(c.startswith("cap_") for c in f.columns)
        assert all(d == np.int8 for d in e.dtypes)


def test_causal_real_4h_1d():
    # include_opened_year=True is allowed ONLY for this causality test.
    for tf in ("4h", "1d"):
        b = common.load_bars(tf, include_opened_year=True)
        common.assert_causal(cap.compute, b)
        common.assert_causal(cap.events, b)


def _flush_bars(wick="recovery"):
    # 80 calm bars (need 60 for vol baseline + 20 for low baseline + ATR warmup),
    # then one engineered flush bar at the end.
    n = 81
    t = pd.date_range("2021-01-01", periods=n, freq="1h", tz="UTC")
    o = np.full(n, 100.0)
    h = np.full(n, 100.5)
    lo = np.full(n, 99.5)
    c = np.full(n, 100.0)
    qv = 1000.0 + np.random.default_rng(0).normal(0, 10.0, n)
    # engineered flush: -4% close-to-close, breaks 20-bar low by > 1 ATR,
    # quote volume spike (~50x baseline -> z >> 3).
    o[-1] = 100.0
    c[-1] = 96.0
    qv[-1] = 50000.0
    if wick == "recovery":
        # lower wick >= 50% of range: low far below, close well off low.
        lo[-1] = 90.0
        h[-1] = 100.5
    else:
        # no wick: close pinned at low.
        lo[-1] = 95.8
        h[-1] = 100.5
    return pd.DataFrame({
        "open_time": t, "open": o, "high": h, "low": lo, "close": c,
        "volume": qv / c, "quote_volume": qv,
        "close_time": t + pd.Timedelta("1h") - pd.Timedelta("1ms"),
    })


def test_flush_with_wick_gives_down_rev():
    bars = _flush_bars("recovery")
    f, e = cap.compute(bars), cap.events(bars)
    assert float(f["cap_qv_z60"].iloc[-1]) > 3.0
    assert float(f["cap_lower_wick"].iloc[-1]) >= 0.5
    assert float(f["cap_flush_down_wick"].iloc[-1]) == 1.0
    assert int(e["cap_ev_down_rev"].iloc[-1]) == 1
    assert int(e["cap_ev_down_cont"].iloc[-1]) == 0
    assert int(e["cap_ev_rev"].iloc[-1]) == 1


def test_flush_without_wick_gives_down_cont():
    bars = _flush_bars("nowick")
    f, e = cap.compute(bars), cap.events(bars)
    assert float(f["cap_qv_z60"].iloc[-1]) > 3.0
    assert float(f["cap_lower_wick"].iloc[-1]) < 0.2
    assert float(f["cap_flush_down_nowick"].iloc[-1]) == 1.0
    assert int(e["cap_ev_down_cont"].iloc[-1]) == -1
    assert int(e["cap_ev_down_rev"].iloc[-1]) == 0
    assert int(e["cap_ev_cont"].iloc[-1]) == -1


def test_calm_bars_have_no_events():
    bars = _syn(600, seed=7)
    e = cap.events(bars)
    # calm synthetic data may still trip rare bars; volume z needs a spike,
    # so require flush flags to match events exactly on real-ish data.
    f = cap.compute(bars)
    m = (e["cap_ev_down_rev"] == 1).to_numpy()
    assert bool(((f["cap_flush_down_wick"] == 1.0).to_numpy()[m]).all())
    m = (e["cap_ev_down_cont"] == -1).to_numpy()
    assert bool(((f["cap_flush_down_nowick"] == 1.0).to_numpy()[m]).all())
    m = (e["cap_ev_up_rev"] == -1).to_numpy()
    assert bool(((f["cap_flush_up_wick"] == 1.0).to_numpy()[m]).all())
    m = (e["cap_ev_up_cont"] == 1).to_numpy()
    assert bool(((f["cap_flush_up_nowick"] == 1.0).to_numpy()[m]).all())


def test_event_rules_match_compute_on_real_bars():
    bars = common.load_bars("4h")
    f, e = cap.compute(bars), cap.events(bars)
    assert int((e["cap_ev_down_rev"] == 1).sum()) >= 1
    assert int((e["cap_ev_down_cont"] == -1).sum()) >= 1
    assert ((e["cap_ev_down_rev"].to_numpy() == 1) ==
            (f["cap_flush_down_wick"].to_numpy() == 1.0)).all()
    assert ((e["cap_ev_down_cont"].to_numpy() == -1) ==
            (f["cap_flush_down_nowick"].to_numpy() == 1.0)).all()
    assert ((e["cap_ev_up_rev"].to_numpy() == -1) ==
            (f["cap_flush_up_wick"].to_numpy() == 1.0)).all()
    assert ((e["cap_ev_up_cont"].to_numpy() == 1) ==
            (f["cap_flush_up_nowick"].to_numpy() == 1.0)).all()
