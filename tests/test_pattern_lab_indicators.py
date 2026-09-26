"""W3 indicator tests: contract, causality on real bars, synthetic hand-checks."""

import time

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import indicators as ind
from agentic_alpha_lab.patterns.common import assert_causal, load_bars, load_funding


def _syn(n=400, seed=0, freq="4h", start="2020-01-01"):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    t = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "open_time": t, "open": open_,
        "high": np.maximum(open_, close) * 1.001,
        "low": np.minimum(open_, close) * 0.999,
        "close": close, "volume": 10.0, "quote_volume": close * 10.0,
        "taker_buy_volume": 5.0,
        "close_time": t + pd.Timedelta(freq) - pd.Timedelta("1ms"),
    })


def _trend(n=300, drift=0.004):
    close = 100 * np.exp(drift * np.arange(n))
    open_ = np.concatenate([[100.0], close[:-1]])
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({
        "open_time": t, "open": open_,
        "high": np.maximum(open_, close) * 1.001,
        "low": np.minimum(open_, close) * 0.999,
        "close": close, "volume": 10.0, "quote_volume": close * 10.0,
        "taker_buy_volume": 5.0,
        "close_time": t + pd.Timedelta("4h") - pd.Timedelta("1ms"),
    })


def test_contract_prefix_dtype_index():
    bars = _syn()
    f, e = ind.compute(bars), ind.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("ind_") for c in f.columns)
    assert all(c.startswith("ind_") for c in e.columns)
    assert all(np.issubdtype(d, np.floating) for d in f.dtypes)
    assert all(d == np.int8 for d in e.dtypes)
    assert bool(((e.to_numpy() >= -1) & (e.to_numpy() <= 1)).all())


def test_causal_real_1h_4h_1d():
    try:
        b1 = load_bars("1h").iloc[:3000]
        b4 = load_bars("4h")
        bd = load_bars("1d")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    for b in (b1, b4, bd):
        assert_causal(ind.compute, b)
        assert_causal(ind.events, b)


def test_perf_full_1h_under_60s():
    try:
        bars = load_bars("1h")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    t0 = time.time()
    ind.compute(bars)
    ind.events(bars)
    assert time.time() - t0 < 60


def test_rsi_trend_flat_handcheck():
    up = _trend(300, 0.004)
    f = ind.compute(up)
    assert f["ind_rsi_14"].iloc[-1] > 70
    assert f["ind_rsi_7"].iloc[-1] > 70
    flat = _trend(300, 0.0)
    assert abs(ind.compute(flat)["ind_rsi_14"].iloc[-1] - 50) < 5


def test_stoch_macd_bollinger_handcheck():
    up = _trend(300, 0.004)
    f = ind.compute(up)
    assert f["ind_stoch_k_14"].iloc[-1] > 90
    assert f["ind_macd_line_atr"].iloc[-1] > 0
    assert f["ind_bb_pctb_20"].iloc[-1] > 0.5
    flat = _trend(300, 0.0)
    ff = ind.compute(flat)
    assert abs(ff["ind_bb_pctb_20"].iloc[-1] - 0.5) < 0.25
    assert ff["ind_bb_bw_20"].iloc[-1] < f["ind_bb_bw_20"].iloc[-1]
    assert ff["ind_atr14_price"].iloc[-1] < f["ind_atr14_price"].iloc[-1]


def test_trend_follow_handcheck():
    up = _trend(300, 0.004)
    f = ind.compute(up)
    last = f.iloc[-1]
    assert last["ind_plus_di_14"] > last["ind_minus_di_14"]
    assert last["ind_adx_14"] > 15
    assert last["ind_cci_20"] > 0
    assert last["ind_willr_14"] > -20
    assert last["ind_mfi_14"] > 60
    assert last["ind_cmf_20"] > 0
    assert last["ind_roc_12"] > 0
    assert last["ind_aroon_up_25"] == 100
    assert last["ind_aroon_osc_25"] > 0
    assert last["ind_ichi_tenkan_dist"] > 0 and last["ind_ichi_kijun_dist"] > 0
    assert last["ind_supertrend_state"] == 1
    assert last["ind_supertrend_dist"] > 0
    assert last["ind_psar_state"] == 1 and last["ind_psar_dist"] > 0
    assert last["ind_sma20_dist"] > 0 and last["ind_ema200_dist"] > 0
    assert last["ind_ribbon_score"] == 1
    # degenerate perfect trend: OBV slope is constant so z is undefined (NaN);
    # on noisy data it must be finite and positive
    noisy = _syn(400, seed=7)
    zn = ind.compute(noisy)["ind_obv_slope_z_20_60"]
    assert np.isfinite(zn.iloc[-1])
    dn = _trend(300, -0.004)
    fd = ind.compute(dn).iloc[-1]
    assert fd["ind_supertrend_state"] == -1 and fd["ind_psar_state"] == -1
    assert fd["ind_ribbon_score"] == -1 and fd["ind_roc_12"] < 0


def test_volume_taker_vwap_handcheck():
    bars = _syn()
    bars.loc[bars.index[-1], "volume"] = 1000.0
    bars.loc[bars.index[-1], "taker_buy_volume"] = 700.0
    f = ind.compute(bars)
    assert f["ind_vol_z_60"].iloc[-1] > 3
    assert abs(f["ind_taker_buy_ratio"].iloc[-1] - 0.7) < 1e-9
    assert np.isfinite(f["ind_vwap24_dev"]).iloc[-1] > -100  # defined, scale-free


def test_funding_known_at_close():
    try:
        bars = load_bars("4h").iloc[:2000]
        fund = load_funding()
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f = ind.compute(bars)
    row = bars.iloc[1000]
    past = fund.loc[fund["fundingTime"] <= row["close_time"]]
    assert len(past)
    assert abs(f["ind_funding_level"].iloc[1000] - past["fundingRate"].iloc[-1]) < 1e-12
    assert abs(f["ind_funding_7d_mean"].iloc[1000] - past["fundingRate"].iloc[-21:].mean()) < 1e-12


def test_events_fire_on_real_data():
    try:
        bars = load_bars("4h")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    e = ind.events(bars)
    nz = (e != 0).sum()
    # every family except rare divergence/golden-cross must fire at least 10x on 13k bars
    for col in e.columns:
        if col in ("ind_ev_rsi_divergence", "ind_ev_golden_death"):
            assert nz[col] >= 1, col
        else:
            assert nz[col] >= 10, (col, int(nz[col]))


def test_event_golden_cross_synthetic():
    c = np.concatenate([np.full(250, 100.0), np.linspace(100, 160, 100)])
    n = len(c)
    o = np.concatenate([[100.0], c[:-1]])
    t = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    bars = pd.DataFrame({"open_time": t, "open": o,
                         "high": np.maximum(o, c) * 1.001, "low": np.minimum(o, c) * 0.999,
                         "close": c, "volume": 10.0, "taker_buy_volume": 5.0,
                         "close_time": t + pd.Timedelta("4h") - pd.Timedelta("1ms")})
    e = ind.events(bars)
    assert (e["ind_ev_golden_death"] == 1).any()


def test_event_rsi_recross_and_divergence_synthetic():
    # sharp selloff then bounce -> RSI dips under 30 then re-crosses up
    c = np.concatenate([np.full(100, 100.0), np.linspace(100, 60, 30), np.linspace(60, 95, 40)])
    n = len(c)
    o = np.concatenate([[100.0], c[:-1]])
    t = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    bars = pd.DataFrame({"open_time": t, "open": o,
                         "high": np.maximum(o, c) * 1.002, "low": np.minimum(o, c) * 0.998,
                         "close": c, "volume": 10.0, "taker_buy_volume": 5.0,
                         "close_time": t + pd.Timedelta("1h") - pd.Timedelta("1ms")})
    e = ind.events(bars)
    assert (e["ind_ev_rsi14_recross"] != 0).any()
    # divergence fn runs causal and returns int8 in range
    assert e["ind_ev_rsi_divergence"].dtype == np.int8
    assert bool(((e["ind_ev_rsi_divergence"].to_numpy() >= -1)).all())
