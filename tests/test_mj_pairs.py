"""MJ W15 pairs tests: contract, causality on real 4h/1d bars, synthetic hand-checks."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import pairs as pr
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
    f, e = pr.compute(bars), pr.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("pr_") for c in f.columns)
    assert all(c.startswith("pr_") for c in e.columns)
    assert all(np.issubdtype(d, np.floating) for d in f.dtypes)
    assert all(d == np.int8 for d in e.dtypes)
    assert bool(((e.to_numpy() >= -1) & (e.to_numpy() <= 1)).all())
    # 5 pairs x (3 z + 2 trend + beta + resid + rv + corr) features, 3 events each.
    assert f.shape[1] == 5 * 9
    assert e.shape[1] == 5 * 3


def test_works_on_1h_4h_1d():
    for tf in ("1h", "4h", "1d"):
        try:
            bars = load_bars(tf).iloc[:800]
        except FileNotFoundError:
            import pytest
            pytest.skip("local data not present")
        f, e = pr.compute(bars), pr.events(bars)
        assert len(f) == len(bars) and len(e) == len(bars)
        assert all(c.startswith("pr_") for c in f.columns)
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
        assert_causal(pr.compute, b)
        assert_causal(pr.events, b)


def test_prelisting_nan_handcheck():
    # First BTC 4h bars (2019-09-08) predate every alt listing -> NaN features, 0 events.
    try:
        bars = load_bars("4h").iloc[:10]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f, e = pr.compute(bars), pr.events(bars)
    assert f.filter(like="lrz60").iloc[:5].isna().all().all()
    assert f.filter(like="beta60").iloc[:5].isna().all().all()
    assert (e.to_numpy()[:5] == 0).all()


def test_asof_ratio_handcheck():
    # pr ratio at a fixed BTC bar equals alt close asof BTC close_time over BTC close.
    try:
        bars = load_bars("4h").iloc[3000:3200]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    target = bars.iloc[100]
    d = pd.read_parquet(pr.XASSET_DIR / "ETHUSDT_4h.parquet")
    d = d.sort_values("close_time").reset_index(drop=True)
    prior = d.loc[pd.to_datetime(d["close_time"]) <= target["close_time"]]
    expect = float(prior.iloc[-1]["close"]) / float(target["close"])
    r, _ = pr._ratio(bars.iloc[:101], "ETH", "BTC")
    assert np.isclose(r.iloc[-1], expect)


def test_zscore_formula_handcheck():
    # lrz60 equals (logR - trailing-60 mean)/trailing-60 std recomputed by hand.
    try:
        bars = load_bars("4h").iloc[3000:3300]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f = pr.compute(bars)
    r, _ = pr._ratio(bars, "ETH", "BTC")
    logr = np.log(r.astype(float))
    m = logr.rolling(60, min_periods=60).mean()
    sd = logr.rolling(60, min_periods=60).std(ddof=0)
    expect = ((logr - m) / sd).iloc[-1]
    assert np.isclose(f["pr_ethbtc_lrz60"].iloc[-1], expect, equal_nan=True)


def test_beta_formula_handcheck():
    # beta60 equals trailing-60 cov/var recomputed by hand from as-of returns.
    try:
        bars = load_bars("4h").iloc[3000:3300]
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f = pr.compute(bars)
    legs = pr._ratio_frame(bars.iloc[:299])
    a = legs["ethbtc_a_close"].astype(float)
    b = legs["ethbtc_b_close"].astype(float)
    ra = np.log(a / a.shift(1)).iloc[-60:]
    rb = np.log(b / b.shift(1)).iloc[-60:]
    expect = float(((ra * rb).mean() - ra.mean() * rb.mean())
                   / ((rb * rb).mean() - rb.mean() ** 2))
    assert np.isclose(f["pr_ethbtc_beta60"].iloc[298], expect)


def test_event_rules_match_compute_handcheck():
    # Every fired event must satisfy its fixed definition against compute() output.
    try:
        bars = load_bars("4h")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f, e = pr.compute(bars), pr.events(bars)
    for code in ("ethbtc", "solbtc", "soleth", "bnbbtc", "xrpbtc"):
        z = f[f"pr_{code}_lrz60"].to_numpy()
        m = (e[f"pr_ev_{code}_mr"] == 1).to_numpy()
        assert m.sum() >= 1, code
        assert bool((z[m] < -2.0).all())
        m = (e[f"pr_ev_{code}_mr"] == -1).to_numpy()
        assert m.sum() >= 1, code
        assert bool((z[m] > 2.0).all())
        rz = f[f"pr_{code}_resid_z60"].to_numpy()
        m = (e[f"pr_ev_{code}_resid"] == 1).to_numpy()
        assert m.sum() >= 1, code
        assert bool((rz[m] < -2.0).all())
        m = (e[f"pr_ev_{code}_resid"] == -1).to_numpy()
        assert m.sum() >= 1, code
        assert bool((rz[m] > 2.0).all())
        r, _ = pr._ratio(bars, *pr._legs(code))
        pmax = r.shift(1).rolling(55, min_periods=55).max()
        pmin = r.shift(1).rolling(55, min_periods=55).min()
        m = (e[f"pr_ev_{code}_brk"] == 1).to_numpy()
        assert m.sum() >= 1, code
        assert bool((((r > pmax) & pmax.notna()).to_numpy()[m]).all())
        m = (e[f"pr_ev_{code}_brk"] == -1).to_numpy()
        assert m.sum() >= 1, code
        assert bool((((r < pmin) & pmin.notna()).to_numpy()[m]).all())


def test_events_fire_on_real_data():
    for tf in ("4h", "1d"):
        try:
            bars = load_bars(tf)
        except FileNotFoundError:
            import pytest
            pytest.skip("local data not present")
        e = pr.events(bars)
        nz = (e != 0).sum()
        for col in e.columns:
            assert nz[col] >= 1, (tf, col, int(nz[col]))
