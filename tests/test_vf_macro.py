"""W7 macro tests: contract, causality on real 4h/1d bars, synthetic hand-checks."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import macro as mac
from agentic_alpha_lab.patterns.common import assert_causal, load_bars


def _syn(n=600, freq="4h", start="2021-06-01", seed=0):
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
    f, e = mac.compute(bars), mac.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("mac_") for c in f.columns)
    assert all(c.startswith("mac_") for c in e.columns)
    assert all(np.issubdtype(d, np.floating) for d in f.dtypes)
    assert all(d == np.int8 for d in e.dtypes)
    assert bool(((e.to_numpy() >= -1) & (e.to_numpy() <= 1)).all())
    assert list(e.columns) == ["mac_ev_risk_on", "mac_ev_vix_spike", "mac_ev_dxy_breakout"]
    assert "mac_risk_on_score" in f.columns
    assert "mac_btc_qqq_corr_60d" in f.columns
    assert "mac_dxy_chg_20d" in f.columns


def test_works_on_1h_4h_1d():
    for tf in ("1h", "4h", "1d"):
        try:
            bars = load_bars(tf).iloc[:800]
        except FileNotFoundError:
            import pytest
            pytest.skip("local data not present")
        f, e = mac.compute(bars), mac.events(bars)
        assert len(f) == len(bars) and len(e) == len(bars)
        assert all(c.startswith("mac_") for c in f.columns)
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
        assert_causal(mac.compute, b)
        assert_causal(mac.events, b)


def _avail_days(bars: pd.DataFrame) -> pd.DatetimeIndex:
    """As-of trading day per bar under the 22:00 UTC rule (mirrors macro.py)."""
    daily = mac._load_daily()
    t_btc = pd.to_datetime(bars["close_time"], utc=True)
    pos = np.searchsorted(
        (daily.index + pd.Timedelta(hours=22)).values.astype("datetime64[ns]").astype("int64"),
        t_btc.values.astype("datetime64[ns]").astype("int64"),
        side="right",
    ) - 1
    pos = np.clip(pos, 0, len(daily) - 1)
    return pd.DatetimeIndex(daily.index[pos])


def _mk(times):
    t = pd.to_datetime(times, utc=True)
    n = len(t)
    bars = pd.DataFrame({
        "open_time": t,
        "open": np.full(n, 100.0),
        "high": np.full(n, 101.0),
        "low": np.full(n, 99.0),
        "close": np.full(n, 100.0),
        "volume": np.ones(n),
        "close_time": t + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1),
    })
    return bars


def test_availability_22utc_handcheck():
    # 2021-06-02 was a Wednesday (trading day). A bar closing 21:59:59 UTC must
    # see the 2021-06-01 row; a bar closing 22:00:00 UTC must see 2021-06-02.
    before = _mk(["2021-06-02 17:00"])  # closes 20:59:59.999 UTC
    after = _mk(["2021-06-02 18:00"])  # closes 21:59:59.999 UTC
    late = _mk(["2021-06-02 19:00"])  # closes 22:59:59.999 UTC
    fb = mac.compute(before)["mac_spy_dist_50d"].iloc[0]
    fa = mac.compute(after)["mac_spy_dist_50d"].iloc[0]
    fl = mac.compute(late)["mac_spy_dist_50d"].iloc[0]
    assert fb == fa  # both still on the 06-01 row
    assert fl != fa  # 22:00 UTC boundary rolls to the 06-02 row
    # Independent recomputation from the raw CSV.
    spy = pd.read_csv(mac.MACRO_DIR / "spy.csv", parse_dates=["date"]).set_index("date")["close"]
    sma50_0601 = spy.loc["2019-06-03":"2021-06-01"].iloc[-50:].mean()
    sma50_0602 = spy.loc["2019-06-03":"2021-06-02"].iloc[-50:].mean()
    assert abs(fa - (spy.loc["2021-06-01"] / sma50_0601 - 1)) < 1e-12
    assert abs(fl - (spy.loc["2021-06-02"] / sma50_0602 - 1)) < 1e-12


def test_weekend_carries_friday_handcheck():
    # Saturday 2021-06-05 carries the Friday 2021-06-04 row.
    sat = _mk(["2021-06-05 00:00"])
    fri = _mk(["2021-06-04 19:00"])  # closes 22:59:59 UTC Friday
    pd.testing.assert_series_equal(
        mac.compute(sat).iloc[0], mac.compute(fri).iloc[0], check_names=False,
    )


def test_risk_score_handcheck():
    bars = _syn(300, start="2022-01-01")
    f = mac.compute(bars)
    row = f.dropna(subset=["mac_risk_on_score"]).iloc[0]
    ts = bars.loc[row.name, "close_time"]
    daily = mac._load_daily()
    one = pd.DataFrame({"close_time": [bars.loc[row.name, "close_time"]]})
    avail_day = _avail_days(one)[0]
    sma200 = lambda s: daily[s].rolling(200, min_periods=200).mean().loc[avail_day]
    # NOTE: int() each term: numpy.bool_ + numpy.bool_ stays boolean (OR).
    expect = float(
        int(daily["spy"].loc[avail_day] > sma200("spy"))
        + int(daily["qqq"].loc[avail_day] > sma200("qqq"))
        + int(daily["vix"].loc[avail_day]
              < daily["vix"].rolling(20, min_periods=20).median().loc[avail_day])
        + int(daily["dxy"].loc[avail_day] < sma200("dxy"))
    )
    assert row["mac_risk_on_score"] == expect


def test_event_rules_match_compute_handcheck():
    try:
        bars = load_bars("4h")
    except FileNotFoundError:
        import pytest
        pytest.skip("local data not present")
    f, e = mac.compute(bars), mac.events(bars)
    s = f["mac_risk_on_score"]
    m = (e["mac_ev_risk_on"] == 1).to_numpy()
    assert m.sum() >= 10
    assert bool((((s >= 3) & (s.shift(1) < 3)).to_numpy()[m]).all())
    m = (e["mac_ev_risk_on"] == -1).to_numpy()
    assert m.sum() >= 10
    assert bool((((s <= 1) & (s.shift(1) > 1)).to_numpy()[m]).all())
    # VIX spike: fired bar has VIX > 1.2 * trailing-20d mean on its as-of day.
    daily = mac._load_daily()
    avail_day = _avail_days(bars)
    vix = daily["vix"].reindex(avail_day).to_numpy()
    vix_mean = daily["vix"].rolling(20, min_periods=20).mean().reindex(avail_day).to_numpy()
    m = (e["mac_ev_vix_spike"] == -1).to_numpy()
    assert m.sum() >= 10
    assert bool(((vix[m] > 1.2 * vix_mean[m]) & ~np.isnan(vix_mean[m])).all())
    assert (e.loc[e["mac_ev_vix_spike"] != 0, "mac_ev_vix_spike"] == -1).all()
    # DXY breakout: fired bar has DXY above its prior 55-trading-day max.
    dxy = daily["dxy"].reindex(avail_day).to_numpy()
    dmax = daily["dxy"].shift(1).rolling(55, min_periods=55).max().reindex(avail_day).to_numpy()
    m = (e["mac_ev_dxy_breakout"] == -1).to_numpy()
    assert m.sum() >= 10
    assert bool(((dxy[m] > dmax[m]) & ~np.isnan(dmax[m])).all())
    assert (e.loc[e["mac_ev_dxy_breakout"] != 0, "mac_ev_dxy_breakout"] == -1).all()


def test_events_fire_on_real_data():
    for tf in ("4h", "1d"):
        try:
            bars = load_bars(tf)
        except FileNotFoundError:
            import pytest
            pytest.skip("local data not present")
        e = mac.events(bars)
        nz = (e != 0).sum()
        for col in e.columns:
            assert nz[col] >= 10, (tf, col, int(nz[col]))
