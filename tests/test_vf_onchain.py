"""W10 on-chain tests: contract, causality on real 4h/1d bars, synthetic hand-checks."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import onchain as onc
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
    f, e = onc.compute(bars), onc.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("onc_") for c in f.columns)
    assert all(c.startswith("onc_") for c in e.columns)
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
        f, e = onc.compute(bars), onc.events(bars)
        assert len(f) == len(bars) and len(e) == len(bars)
        assert all(c.startswith("onc_") for c in f.columns)
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
        assert_causal(onc.compute, b)
        assert_causal(onc.events, b)


def test_availability_asof_handcheck():
    # A BTC bar's MVRV level must equal the CoinMetrics daily value for the
    # latest date D with D+1 02:00 UTC <= bar close_time.
    try:
        bars = load_bars("4h").iloc[2000:2100]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f = onc.compute(bars)
    daily = onc._load_daily()
    target = bars.iloc[50]
    ct = pd.to_datetime(target["close_time"], utc=True)
    avail = daily.index + pd.Timedelta(hours=onc.AVAIL_HOURS)
    expect_date = daily.index[avail <= ct][-1]
    assert f["onc_mvrv"].iloc[50] == daily.loc[expect_date, "mvrv"]
    # The next day's value must NOT be visible yet if its availability is later.
    nxt = expect_date + pd.Timedelta(days=1)
    if nxt in daily.index and not (nxt + pd.Timedelta(hours=onc.AVAIL_HOURS) <= ct):
        assert f["onc_mvrv"].iloc[50] != daily.loc[nxt, "mvrv"] or \
            daily.loc[nxt, "mvrv"] == daily.loc[expect_date, "mvrv"]


def test_zscore_math_handcheck():
    # z365 at a fixed bar matches a hand-rolled trailing-365d computation.
    try:
        bars = load_bars("1d").iloc[700:750]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f = onc.compute(bars)
    daily = onc._load_daily()
    ct = pd.to_datetime(bars.iloc[-1]["close_time"], utc=True)
    avail = daily.index + pd.Timedelta(hours=onc.AVAIL_HOURS)
    d = daily.index[avail <= ct][-1]
    w = daily["mvrv"].loc[:d].iloc[-365:]
    expect = (w.iloc[-1] - w.mean()) / w.std(ddof=0)
    assert np.isclose(f["onc_mvrv_z365"].iloc[-1], expect)


def test_event_rules_match_compute_handcheck():
    # Every fired event must satisfy its fixed definition against compute().
    try:
        bars = load_bars("1d")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f, e = onc.compute(bars), onc.events(bars)
    z = f["onc_mvrv_z365"]
    m = (e["onc_ev_mvrv_hot"] == -1).to_numpy()
    assert m.sum() >= 1
    assert bool(((z > 2.0).to_numpy()[m]).all())
    prev_hot = (z.shift(1) > 2.0).fillna(False).to_numpy(bool)
    assert bool((~prev_hot[m]).all())  # rising edge only
    assert (e.loc[e["onc_ev_mvrv_hot"] != 0, "onc_ev_mvrv_hot"] == -1).all()
    m = (e["onc_ev_mvrv_cheap"] == 1).to_numpy()
    assert m.sum() >= 1
    assert bool(((f["onc_mvrv"] < 1.0).to_numpy()[m]).all())
    gz = f["onc_stable_g30_z365"]
    m = (e["onc_ev_stable_inflow"] == 1).to_numpy()
    assert m.sum() >= 1
    assert bool(((gz > 1.5).to_numpy()[m]).all())
    hg = f["onc_hash_g30"]
    m = (e["onc_ev_hash_drop"] == -1).to_numpy()
    assert m.sum() >= 1
    assert bool(((hg < -0.10).to_numpy()[m]).all())


def test_events_bounded_and_single_sided():
    try:
        bars = load_bars("4h")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    e = onc.events(bars)
    assert set(np.unique(e["onc_ev_mvrv_hot"].to_numpy())) <= {-1, 0}
    assert set(np.unique(e["onc_ev_mvrv_cheap"].to_numpy())) <= {0, 1}
    assert set(np.unique(e["onc_ev_stable_inflow"].to_numpy())) <= {0, 1}
    assert set(np.unique(e["onc_ev_hash_drop"].to_numpy())) <= {-1, 0}
