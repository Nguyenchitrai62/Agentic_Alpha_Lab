"""W5 positioning tests: contract, causality on real 4h/1d bars, synthetic hand-checks."""

import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common
from agentic_alpha_lab.patterns import positioning as pos


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
    f, e = pos.compute(bars), pos.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("pos_") for c in f.columns)
    assert all(c.startswith("pos_") for c in e.columns)
    assert all(np.issubdtype(d, np.floating) for d in f.dtypes)
    assert all(d == np.int8 for d in e.dtypes)
    assert bool(((e.to_numpy() >= -1) & (e.to_numpy() <= 1)).all())


def test_works_on_1h_4h_1d():
    for tf in ("1h", "4h", "1d"):
        bars = common.load_bars(tf).iloc[:800]
        f, e = pos.compute(bars), pos.events(bars)
        assert len(f) == len(bars) and len(e) == len(bars)
        assert all(c.startswith("pos_") for c in f.columns)
        assert all(d == np.int8 for d in e.dtypes)


def test_causal_real_4h_1d():
    # include_opened_year=True is allowed ONLY for this causality test.
    for tf in ("4h", "1d"):
        b = common.load_bars(tf, include_opened_year=True)
        common.assert_causal(pos.compute, b)
        common.assert_causal(pos.events, b)


def test_pre2022_oi_nan_and_no_events_handcheck():
    # Metrics start 2022-01-01: mid-2021 synthetic bars see no OI/ratios.
    bars = _syn(600, seed=1)
    f = pos.compute(bars)
    oi_cols = [c for c in f.columns if "oi_chg" in c or c in
               ("pos_oi_z_30d", "pos_oi_price_div_24")]
    assert f[oi_cols].isna().all().all()
    for c in ("pos_top_count_lvl", "pos_top_sum_lvl",
              "pos_ls_global_lvl", "pos_taker_lvl"):
        assert f[c].isna().all(), c
    e = pos.events(bars)
    assert (e.to_numpy() == 0).all()


def test_availability_lag_handcheck():
    # Recompute one bar's OI change independently with the 5-minute lag rule.
    bars = common.load_bars("4h")
    f = pos.compute(bars)
    m = pd.read_parquet(pos.BASE_METRICS)
    if pos.EXT_METRICS.exists():
        m = pd.concat([m, pd.read_parquet(pos.EXT_METRICS)], ignore_index=True)
    m["create_time"] = pd.to_datetime(m["create_time"], utc=True)
    m = m.sort_values("create_time").reset_index(drop=True)
    avail = m["create_time"] + pd.Timedelta(minutes=5)
    oi = m["sum_open_interest"].astype(float).to_numpy()
    tgt = bars.iloc[6000]
    c = tgt["close_time"]
    cns = pd.Timestamp(c).value
    ans = avail.values.astype("datetime64[ns]").astype("int64")
    i_now = int(np.searchsorted(ans, cns, side="right") - 1)
    i_then = int(np.searchsorted(ans, cns - 4 * 3600 * 1_000_000_000, side="right") - 1)
    expect = float(np.log(oi[i_now] / oi[i_then]))
    assert avail.iloc[i_now] <= c, "joined row must be available at bar close"
    assert (avail.iloc[i_now + 1] > c), "must not peek at the next row"
    assert np.isclose(f["pos_oi_chg_1"].iloc[6000], expect, atol=1e-12)


def test_event_rules_match_compute_handcheck():
    bars = common.load_bars("4h")
    f, e = pos.compute(bars), pos.events(bars)
    m = (e["pos_ev_crowd"] == -1).to_numpy()
    assert m.sum() >= 1
    assert bool((((f["pos_funding_z"] > 2.0) & (f["pos_ls_global_z"] > 2.0)).to_numpy()[m]).all())
    m = (e["pos_ev_crowd"] == 1).to_numpy()
    assert m.sum() >= 1
    assert bool((((f["pos_funding_z"] < -2.0) & (f["pos_ls_global_z"] < -2.0)).to_numpy()[m]).all())
    assert int((e["pos_ev_crowd"] != 0).sum()) >= 10
    m = (e["pos_ev_crowd_top"] == -1).to_numpy()
    assert m.sum() >= 10
    assert bool((((f["pos_funding_z"] > 2.0) & (f["pos_top_sum_z"] > 2.0)).to_numpy()[m]).all())
    c = bars["close"].astype(float).to_numpy(float)
    ret6 = np.full(len(c), np.nan)
    ret6[6:] = np.log(c[6:] / c[:-6])
    m = (e["pos_ev_oi_cont"] == 1).to_numpy()
    assert m.sum() >= 100
    assert bool((f["pos_oi_chg_6"].to_numpy()[m] > 0.02).all())
    assert bool((ret6[m] > 0).all())
    m = (e["pos_ev_oi_cont"] == -1).to_numpy()
    assert m.sum() >= 100
    assert bool((f["pos_oi_chg_6"].to_numpy()[m] > 0.02).all())
    assert bool((ret6[m] < 0).all())
    m = (e["pos_ev_oi_flush"] == 1).to_numpy()
    assert m.sum() >= 100
    assert bool((f["pos_oi_chg_6"].to_numpy()[m] < -0.03).all())
    assert (e.loc[e["pos_ev_oi_flush"] != 0, "pos_ev_oi_flush"] == 1).all()


def test_funding_z_uses_90_print_window_handcheck():
    # Funding z at a fixed bar equals the trailing-90-print z as-of that close.
    bars = common.load_bars("4h").iloc[5000:5005]
    f = pos.compute(bars)
    fund = common.load_funding(include_opened_year=True).sort_values("fundingTime")
    fr = fund["fundingRate"].astype(float)
    z = ((fr - fr.rolling(90, min_periods=90).mean())
         / fr.rolling(90, min_periods=90).std(ddof=0).replace(0, np.nan))
    c = bars["close_time"].iloc[0]
    expect = z[fund["fundingTime"] <= c].iloc[-1]
    assert np.isclose(f["pos_funding_z"].iloc[0], expect, atol=1e-12)
