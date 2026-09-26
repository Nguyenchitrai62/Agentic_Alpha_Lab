"""W6 breadth tests: contract, causality on real 4h/1d bars, synthetic hand-checks."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import breadth as brd
from agentic_alpha_lab.patterns.common import assert_causal, load_bars


def _syn(n=600, seed=0, freq="4h", start="2021-06-01"):
    rng = np.random.default_rng(seed)
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
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
    f, e = brd.compute(bars), brd.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("brd_") for c in f.columns)
    assert all(c.startswith("brd_") for c in e.columns)
    assert all(np.issubdtype(d, np.floating) for d in f.dtypes)
    assert all(d == np.int8 for d in e.dtypes)
    assert bool(((e.to_numpy() >= -1) & (e.to_numpy() <= 1)).all())


def test_works_on_1h_4h_1d():
    for tf in ("1h", "4h", "1d"):
        try:
            bars = load_bars(tf).iloc[:800]
        except FileNotFoundError:
            import pytest
            pytest.skip("local data not present")
        f, e = brd.compute(bars), brd.events(bars)
        assert len(f) == len(bars) and len(e) == len(bars)
        assert all(c.startswith("brd_") for c in f.columns)
        assert all(d == np.int8 for d in e.dtypes)


def test_causal_real_4h_1d():
    # include_opened_year=True is allowed ONLY for this causality test.
    try:
        b4 = load_bars("4h", include_opened_year=True)
        bd = load_bars("1d", include_opened_year=True)
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    for b in (b4, bd):
        assert_causal(brd.compute, b)
        assert_causal(brd.events, b)


def test_unlisted_alts_excluded_handcheck():
    # First BTC 4h bar (2019-09-08) predates every alt listing -> n_listed 0, fracs NaN.
    try:
        bars = load_bars("4h").iloc[:10]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f = brd.compute(bars)
    assert (f["brd_n_listed"].iloc[:5] == 0).all()
    assert f["brd_above_ema50_frac"].iloc[:5].isna().all()
    assert f["brd_high55_frac"].iloc[:5].isna().all()
    # By 2021 all 10 alts are listed.
    bars = load_bars("4h")
    idx2021 = bars.loc[bars["open_time"] >= pd.Timestamp("2021-06-01", tz="UTC")].index[0]
    pos = bars.index.get_loc(idx2021)
    assert brd.compute(bars.iloc[pos:pos + 1])["brd_n_listed"].iloc[0] == 10


def test_asof_join_handcheck():
    # brd_n_listed at a fixed BTC bar equals the number of alts whose first
    # close_time is at or before that BTC bar close_time.
    try:
        bars = load_bars("4h").iloc[900:1100]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f = brd.compute(bars)
    target = bars.iloc[100]
    expect = 0
    for sym in brd.SYMBOLS:
        d = pd.read_parquet(brd.XASSET_DIR / f"{sym}USDT_4h.parquet")
        if pd.to_datetime(d["close_time"]).min() <= target["close_time"]:
            expect += 1
    assert f["brd_n_listed"].iloc[100] == expect


def test_frac_bounds_and_counts_handcheck():
    bars = _syn(800, seed=3)
    f = brd.compute(bars)
    warm = f.dropna(subset=["brd_above_ema50_frac"]).iloc[1:]
    assert len(warm) > 100
    assert bool(((warm["brd_above_ema50_frac"] >= 0) & (warm["brd_above_ema50_frac"] <= 1)).all())
    assert bool(((warm["brd_ribbon_up_frac"] + warm["brd_ribbon_down_frac"] <= 1 + 1e-12)).all())
    assert bool(((warm["brd_high55_cnt"] + warm["brd_low55_cnt"] <= warm["brd_n_listed"] + 1e-9)).all())
    assert (warm["brd_n_listed"] == 10).all()  # mid-2021 window: all listed
    assert np.isfinite(warm["brd_rs_med_1"]).all()
    assert np.isfinite(warm["brd_funding_z_mean"]).all()


def test_event_rules_match_compute_handcheck():
    # Every fired event must satisfy its fixed definition against compute() output.
    try:
        bars = load_bars("4h")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f, e = brd.compute(bars), brd.events(bars)
    a = f["brd_above_ema50_frac"]
    m = (e["brd_ev_thrust"] == 1).to_numpy()
    assert m.sum() >= 10
    assert bool((((a > 0.70) & (a.shift(1) <= 0.70)).to_numpy()[m]).all())
    m = (e["brd_ev_thrust"] == -1).to_numpy()
    assert m.sum() >= 10
    assert bool((((a < 0.30) & (a.shift(1) >= 0.30)).to_numpy()[m]).all())
    z = f["brd_funding_z_mean"]
    m = (e["brd_ev_fund_crowd"] == -1).to_numpy()
    assert m.sum() >= 1
    assert bool((((z > 2.0) & (z.shift(1) <= 2.0)).to_numpy()[m]).all())
    assert (e.loc[e["brd_ev_fund_crowd"] != 0, "brd_ev_fund_crowd"] == -1).all()
    c = bars["close"].astype(float)
    cmax = c.rolling(55, min_periods=55).max()
    m = (e["brd_ev_divergence"] == -1).to_numpy()
    assert m.sum() >= 1
    btc_high = ((c >= cmax) & cmax.notna()).to_numpy()
    weak = (f["brd_high55_frac"] < 0.30).fillna(False).to_numpy()
    assert bool((btc_high[m]).all()) and bool((weak[m]).all())
    assert (e.loc[e["brd_ev_divergence"] != 0, "brd_ev_divergence"] == -1).all()
    # ETH/BTC breakout: recompute ratio independently and check the breach.
    r = brd._eth_ratio(bars, "4h")
    pmax = r.shift(1).rolling(55, min_periods=55).max()
    pmin = r.shift(1).rolling(55, min_periods=55).min()
    m = (e["brd_ev_ethbtc_break"] == 1).to_numpy()
    assert m.sum() >= 1
    assert bool((((r > pmax) & pmax.notna()).to_numpy()[m]).all())
    m = (e["brd_ev_ethbtc_break"] == -1).to_numpy()
    assert bool((((r < pmin) & pmin.notna()).to_numpy()[m]).all())


def test_events_fire_on_real_data():
    for tf in ("4h", "1d"):
        try:
            bars = load_bars(tf)
        except FileNotFoundError:
            import pytest
            pytest.skip("local data not present")
        e = brd.events(bars)
        nz = (e != 0).sum()
        for col in e.columns:
            assert nz[col] >= 10, (tf, col, int(nz[col]))
