import numpy as np
import pandas as pd

from agentic_alpha_lab.patterns import common, seasonality


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
        "close_time": t + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
    })
    return bars


def test_prefix_index_dtypes():
    bars = common.load_bars("1h").iloc[:500]
    f = seasonality.compute(bars)
    e = seasonality.events(bars)
    assert len(f) == len(bars) and f.index.equals(bars.index)
    assert len(e) == len(bars) and e.index.equals(bars.index)
    assert all(c.startswith("sea_") for c in f.columns)
    assert all(c.startswith("sea_") for c in e.columns)
    assert set(np.unique(e.to_numpy())) <= {0, 1}
    assert (e.dtypes == np.int8).all()
    assert all(str(d) == "float64" for d in f.dtypes)


def test_causal_real_4h_1d_opened_year():
    # include_opened_year=True allowed ONLY for this causality test
    for tf in ("4h", "1d"):
        bars = common.load_bars(tf, include_opened_year=True)
        common.assert_causal(seasonality.compute, bars)
        common.assert_causal(seasonality.events, bars)


def test_hod_dow_weekend_handchecked():
    bars = _mk(["2021-01-04 00:00", "2021-01-04 06:00", "2021-01-09 12:00"])
    f = seasonality.compute(bars)
    assert f["sea_hod"].tolist() == [0.0, 6.0, 12.0]
    assert np.isclose(f["sea_hod_sin"].iloc[0], 0.0, atol=1e-12)
    assert np.isclose(f["sea_hod_cos"].iloc[0], 1.0, atol=1e-12)
    assert np.isclose(f["sea_hod_sin"].iloc[1], 1.0, atol=1e-12)
    assert np.isclose(f["sea_hod_cos"].iloc[1], 0.0, atol=1e-12)
    assert f["sea_dow"].tolist() == [0.0, 0.0, 5.0]
    assert f["sea_is_weekend"].tolist() == [0.0, 0.0, 1.0]


def test_month_windows_handchecked():
    bars = _mk(["2021-01-01 00:00", "2021-01-31 00:00", "2021-02-15 00:00"])
    f = seasonality.compute(bars)
    assert f["sea_is_month_start"].tolist() == [1.0, 0.0, 0.0]
    assert f["sea_is_month_end"].tolist() == [0.0, 1.0, 0.0]
    assert f["sea_days_from_month_start"].tolist() == [0.0, 30.0, 14.0]
    assert f["sea_days_to_month_end"].tolist() == [30.0, 0.0, 13.0]


def test_sessions_handchecked():
    bars = _mk([
        "2021-01-04 02:00", "2021-01-04 09:00", "2021-01-04 14:00",
        "2021-01-04 20:00", "2021-01-04 22:00",
    ])
    f = seasonality.compute(bars)
    assert f[["sea_sess_asia", "sea_sess_eu", "sea_sess_us"]].iloc[0].tolist() == [1.0, 0.0, 0.0]
    assert f[["sea_sess_asia", "sea_sess_eu", "sea_sess_us"]].iloc[1].tolist() == [0.0, 1.0, 0.0]
    assert f[["sea_sess_asia", "sea_sess_eu", "sea_sess_us"]].iloc[2].tolist() == [0.0, 1.0, 1.0]
    assert f[["sea_sess_asia", "sea_sess_eu", "sea_sess_us"]].iloc[3].tolist() == [0.0, 0.0, 1.0]
    assert f[["sea_sess_asia", "sea_sess_eu", "sea_sess_us"]].iloc[4].tolist() == [0.0, 0.0, 0.0]


def test_cme_gap_handchecked():
    bars = _mk([
        "2021-01-08 20:00", "2021-01-08 21:00", "2021-01-09 12:00",
        "2021-01-10 21:00", "2021-01-10 22:00", "2021-01-11 00:00",
    ])
    f = seasonality.compute(bars)
    assert f["sea_cme_gap_window"].tolist() == [0.0, 1.0, 1.0, 1.0, 0.0, 0.0]


def test_qexpiry_handchecked():
    # Mar 2021 expiry: last Friday = 26th 08:00 UTC
    bars = _mk(["2021-03-25 00:00", "2021-03-26 08:00"])
    f = seasonality.compute(bars)
    # first bar closes 2021-03-25 00:59 -> ~1.29 days to expiry
    assert abs(f["sea_days_to_qexpiry"].iloc[0] - 1.292) < 0.02
    assert f["sea_is_qexpiry_week"].iloc[0] == 1.0
    # bar opening at expiry hour closes after 08:00 -> rolls to Jun expiry (~91d)
    assert f["sea_days_to_qexpiry"].iloc[1] > 80.0
    assert f["sea_is_qexpiry_week"].iloc[1] == 0.0
    assert (f["sea_days_since_qexpiry"] >= 0).all()


def test_events_buckets_handchecked():
    bars = _mk(["2021-01-04 14:00", "2021-01-09 02:00"])  # Mon 14h, Sat 02h
    e = seasonality.events(bars)
    assert e["sea_ev_hod_14"].tolist() == [1, 0]
    assert e["sea_ev_hod_02"].tolist() == [0, 1]
    assert e["sea_ev_dow_mon"].tolist() == [1, 0]
    assert e["sea_ev_dow_sat"].tolist() == [0, 1]
    assert e["sea_ev_sess_us"].tolist() == [1, 0]
    assert e["sea_ev_sess_asia"].tolist() == [0, 1]
    # each row fires exactly one hod and one dow bucket
    assert e[[c for c in e.columns if "hod" in c]].sum(axis=1).tolist() == [1, 1]
    assert e[[c for c in e.columns if "dow" in c]].sum(axis=1).tolist() == [1, 1]
