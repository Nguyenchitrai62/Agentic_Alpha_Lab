"""oc_lit_position tests: causality/truncation + hand-checked synthetics (PLAN-fixed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent.parent / "research/tournament/oc_lit_position"
sys.path.insert(0, str(HERE))
from signals import (h6_d7_z, h6_mults, h8_asof_z, h8_mults, load_mvrv_daily,
                     load_oi)


def test_h6_truncation_causal():
    # Synthetic 5-min OI for 30 days; 4h grid over the last 10 days.
    t0 = pd.Timestamp("2022-01-01", tz="UTC")
    oi_t = (pd.date_range(t0, t0 + pd.Timedelta(days=130), freq="5min").values
            .astype("datetime64[ns]").astype(np.int64))
    rng = np.random.default_rng(7)
    oi_v = 100000 + np.cumsum(rng.normal(0, 200, len(oi_t)))
    oi_v = np.abs(oi_v) + 50000
    bars = pd.date_range(t0 + pd.Timedelta(days=30), t0 + pd.Timedelta(days=130), freq="4h")
    bns = bars.values.astype("datetime64[ns]").astype(np.int64)
    d_full, z_full = h6_d7_z(bns, oi_t, oi_v)
    # Truncate OI to <= last bar (causal truncation must not change z).
    cut = oi_t <= (bns[-1] - pd.Timedelta(minutes=5).value)
    d_tr, z_tr = h6_d7_z(bns, oi_t[cut], oi_v[cut])
    m = np.isfinite(z_full) | np.isfinite(z_tr)
    assert m.any()
    np.testing.assert_allclose(np.nan_to_num(z_full[m]), np.nan_to_num(z_tr[m]), rtol=0, atol=1e-12)
    # Future OI must not leak: truncate one more day earlier changes only tail NaNs, not early z.
    cut2 = oi_t <= (bns[0] - pd.Timedelta(minutes=5).value + pd.Timedelta(days=1).value)
    _, z_tr2 = h6_d7_z(bns[:2], oi_t[cut2], oi_v[cut2])
    np.testing.assert_allclose(np.nan_to_num(z_full[:2]), np.nan_to_num(z_tr2), rtol=0, atol=1e-12)


def test_handchecked_synthetic_h6():
    # Flat OI -> d7 == 0 wherever computable; z == 0 with enough history -> mult 1.
    t0 = pd.Timestamp("2022-03-01", tz="UTC")
    oi_t = (pd.date_range(t0, t0 + pd.Timedelta(days=400), freq="5min").values
            .astype("datetime64[ns]").astype(np.int64))
    oi_v = np.full(len(oi_t), 100000.0)
    bars = pd.date_range(t0 + pd.Timedelta(days=370), t0 + pd.Timedelta(days=400), freq="4h")
    bns = bars.values.astype("datetime64[ns]").astype(np.int64)
    d7, z = h6_d7_z(bns, oi_t, oi_v)
    assert np.all(np.nan_to_num(d7[np.isfinite(d7)]) == 0.0)
    # Flat series: trailing std == 0 -> NaN (no false fires), mults all 1.
    assert not np.isfinite(z).any()
    assert (h6_mults(z, 2.0) == 1.0).all()
    assert (h6_mults(z, 1.5) == 1.0).all()
    # Hand-check: doubling over 7d gives ln2.
    oi_v2 = np.where(oi_t >= (bns[0] - pd.Timedelta(days=7).value), 200000.0, 100000.0)
    d7b, _ = h6_d7_z(bns[:1], oi_t, oi_v2)
    assert np.isfinite(d7b[0]) and abs(d7b[0] - np.log(2.0)) < 1e-9


def test_h8_truncation_and_availability():
    daily = load_mvrv_daily()
    assert daily.index.min() <= pd.Timestamp("2021-09-24", tz="UTC")
    # Availability boundary: T just before/after D+1 02:00 exposes previous/current day.
    d0 = daily.index[daily.index >= pd.Timestamp("2023-01-01", tz="UTC")][300]
    avail = d0 + pd.Timedelta(hours=26)
    T = pd.DatetimeIndex([avail - pd.Timedelta(seconds=1), avail, avail + pd.Timedelta(seconds=1)])
    z = h8_asof_z(daily, T)
    assert np.isfinite(z).all()
    assert z[0] != z[1] or z[1] == z[2]  # boundary moves at most once
    assert z[1] == z[2]
    # Truncation: recompute daily from rows <= d0 must match z(d0).
    sub = daily.loc[:d0]
    # manual rolling on truncated mvrv
    w = sub["mvrv"].iloc[-365:]
    mu, sd = w.mean(), w.std(ddof=1)
    expect = (sub["mvrv"].iloc[-1] - mu) / sd
    assert abs(daily.loc[d0, "z"] - expect) < 1e-9
    # M1/M2 mult hand-check
    assert list(h8_mults(np.array([2.5, 0.0, -0.5]), "M1")) == [0.5, 1.0, 1.0]
    assert list(h8_mults(np.array([2.5, 0.0, -0.5]), "M2")) == [0.5, 1.0, 1.1]


def test_m3_skipped_no_eth_history():
    assert not (Path("data/raw/onchain_20260924") / "eth.csv").exists()
    assert not (Path("data/raw/onchain_20260924") / "eth_mvrv.csv").exists()


def test_real_oi_spans_disclosed():
    t_btc, _ = load_oi("BTCUSDT")
    t_eth, _ = load_oi("ETHUSDT")
    btc0 = pd.Timestamp(t_btc.min(), tz="UTC")
    eth0 = pd.Timestamp(t_eth.min(), tz="UTC")
    assert btc0 <= pd.Timestamp("2020-09-02", tz="UTC")
    assert pd.Timestamp("2021-12-01", tz="UTC") <= eth0 <= pd.Timestamp("2021-12-02", tz="UTC")
