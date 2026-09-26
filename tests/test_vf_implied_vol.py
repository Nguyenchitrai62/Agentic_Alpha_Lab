"""W8 implied-vol (DVOL) tests: contract, causality on real 4h/1d bars, synthetic hand-checks."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common
from agentic_alpha_lab.patterns import implied_vol as iv


def _syn(n=600, seed=0, freq="4h", start="2022-06-01"):
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
    f, e = iv.compute(bars), iv.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("dvol_") for c in f.columns)
    assert all(c.startswith("dvol_") for c in e.columns)
    assert all(np.issubdtype(d, np.floating) for d in f.dtypes)
    assert all(d == np.int8 for d in e.dtypes)
    assert bool(((e.to_numpy() >= -1) & (e.to_numpy() <= 1)).all())


def test_works_on_1h_4h_1d():
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf).iloc[:800]
        f, e = iv.compute(bars), iv.events(bars)
        assert len(f) == len(bars) and len(e) == len(bars)
        assert all(c.startswith("dvol_") for c in f.columns)
        assert all(d == np.int8 for d in e.dtypes)


def test_causal_real_4h_1d():
    # include_opened_year=True is allowed ONLY for this causality test.
    for tf in ("4h", "1d"):
        b = common.load_bars(tf, include_opened_year=True)
        common.assert_causal(iv.compute, b)
        common.assert_causal(iv.events, b)


def test_pre_dvol_nan_and_no_events_handcheck():
    # DVOL starts 2021-03-24: mid-2020 synthetic bars see no DVOL features.
    bars = _syn(600, seed=1, start="2020-01-01")
    f = iv.compute(bars)
    assert f[["dvol_level", "dvol_chg_1d", "dvol_chg_7d", "dvol_z_90d",
              "dvol_spread", "dvol_ratio"]].isna().all().all()
    e = iv.events(bars)
    assert (e.to_numpy() == 0).all()


def test_availability_lag_handcheck():
    # A BTC bar closing before a DVOL candle's ts+1h must not see that print.
    bars = common.load_bars("1h").iloc[20000:20005]
    f = iv.compute(bars)
    d = pd.read_parquet(iv.DVOL_DIR / "dvol_hourly.parquet").sort_values("ts")
    dc = d["dvol_close"].astype(float).to_numpy()
    avail = (pd.to_datetime(d["ts_utc"], utc=True) + pd.Timedelta(hours=1))
    ans = avail.values.astype("datetime64[ns]").astype("int64")
    c = bars["close_time"].iloc[0]
    cns = pd.Timestamp(c).value
    i = int(np.searchsorted(ans, cns, side="right") - 1)
    assert avail.iloc[i] <= c, "joined print must be available at bar close"
    assert avail.iloc[i + 1] > c, "must not peek at the next print"
    assert np.isclose(f["dvol_level"].iloc[0], dc[i], atol=1e-12)


def test_z_and_changes_match_hourly_domain_handcheck():
    # z / changes at a fixed bar equal the trailing hourly-domain values as-of.
    bars = common.load_bars("4h").iloc[6000:6005]
    f = iv.compute(bars)
    d = pd.read_parquet(iv.DVOL_DIR / "dvol_hourly.parquet").sort_values("ts")
    dc = d["dvol_close"].astype(float)
    z = (dc - dc.rolling(iv.Z_WINDOW, min_periods=iv.Z_WINDOW).mean()) / \
        dc.rolling(iv.Z_WINDOW, min_periods=iv.Z_WINDOW).std(ddof=0)
    c1 = np.log(dc / dc.shift(iv.CHG_1D))
    c7 = np.log(dc / dc.shift(iv.CHG_7D))
    avail = pd.to_datetime(d["ts_utc"], utc=True) + pd.Timedelta(hours=1)
    c = bars["close_time"].iloc[0]
    row = d.loc[avail <= c].iloc[-1]
    assert np.isclose(f["dvol_z_90d"].iloc[0], z.loc[row.name], atol=1e-9)
    assert np.isclose(f["dvol_chg_1d"].iloc[0], c1.loc[row.name], atol=1e-12)
    assert np.isclose(f["dvol_chg_7d"].iloc[0], c7.loc[row.name], atol=1e-12)
    assert np.isclose(f["dvol_spread"].iloc[0],
                      f["dvol_level"].iloc[0] - f["dvol_rv_30d"].iloc[0], atol=1e-9)
    assert np.isclose(f["dvol_ratio"].iloc[0],
                      f["dvol_level"].iloc[0] / f["dvol_rv_30d"].iloc[0], atol=1e-12)


def test_event_rules_match_compute_handcheck():
    bars = common.load_bars("4h")
    f, e = iv.compute(bars), iv.events(bars)
    z = f["dvol_z_90d"]
    cross = ((z > 2.0) & (z.shift(1) <= 2.0)).to_numpy()
    m = (e["dvol_ev_spike_revert"] == 1).to_numpy()
    assert m.sum() >= 10
    assert bool(cross[m].all())
    assert (e.loc[e["dvol_ev_spike_revert"] != 0, "dvol_ev_spike_revert"] == 1).all()
    m = (e["dvol_ev_spike_panic"] == -1).to_numpy()
    assert m.sum() >= 10
    assert bool(cross[m].all())
    assert (e.loc[e["dvol_ev_spike_panic"] != 0, "dvol_ev_spike_panic"] == -1).all()
    # Same trigger, opposite signs.
    assert (e["dvol_ev_spike_revert"].to_numpy() == -e["dvol_ev_spike_panic"].to_numpy()).all()
    sp = f["dvol_spread"]
    m = (e["dvol_ev_ivrv"] == 1).to_numpy()
    assert m.sum() >= 1
    assert bool((((sp > 25.0) & (sp.shift(1) <= 25.0)).to_numpy()[m]).all())
    m = (e["dvol_ev_ivrv"] == -1).to_numpy()
    assert m.sum() >= 1
    assert bool((((sp < -10.0) & (sp.shift(1) >= -10.0)).to_numpy()[m]).all())
    chg = f["dvol_chg_1d"]
    m = (e["dvol_ev_crush"] == 1).to_numpy()
    assert m.sum() >= 1
    assert bool((chg.to_numpy()[m] < -0.08).all())
    assert (e.loc[e["dvol_ev_crush"] != 0, "dvol_ev_crush"] == 1).all()
    # Crush requires a trailing-7d z > 2 before the bar (checked in hourly domain).
    D = iv._load_dvol()
    t_bar = pd.to_datetime(bars["close_time"], utc=True).values.astype(
        "datetime64[ns]").astype("int64")
    z_hr = pd.Series(D["z"]).rolling(iv.CRUSH_LOOKBACK, min_periods=1).max().shift(1)
    pos = np.searchsorted(D["avail"], t_bar, side="right") - 1
    prior = np.full(len(bars), np.nan)
    ok = pos >= 0
    prior[ok] = z_hr.to_numpy(float)[pos[ok]]
    assert bool((prior[m] > 2.0).all())


def test_events_fire_on_real_data():
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf)
        e = iv.events(bars)
        nz = (e != 0).sum()
        for col in e.columns:
            assert nz[col] >= 10, (tf, col, int(nz[col]))
