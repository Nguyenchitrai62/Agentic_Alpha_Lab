"""Tests for oc_b7taper: hand-checked synthetics + causality on pre-sample data."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PST = ROOT / "research/tournament/oc_presampletilt"
MINE = ROOT / "research/tournament/oc_b7taper"
CBP = ROOT / "research/tournament/oc_cboostpre"
sys.path.insert(0, str(MINE))

from taper_rule import (  # noqa: E402
    BOOST_DAYS,
    MIN_PERIODS,
    THRESH,
    V1_HI,
    V1_LO,
    V1_MID,
    WINDOW,
    boosted_mask,
    close_returns,
    cooled_mask,
    mults_on_grid,
    taper_mult,
    trailing_sigma,
    triggers_of,
)

DAY = 86_400_000_000_000


def test_close_returns_hand_checked():
    c = np.array([100.0, 110.0, 99.0])
    r = close_returns(c)
    assert np.isnan(r[0])
    assert r[1] == np.log(1.1)
    assert r[2] == np.log(0.9)
    r2 = close_returns(np.array([100.0, 100.0, 0.0, -5.0]))
    assert r2[1] == 0.0
    assert np.isnan(r2[2]) and np.isnan(r2[3])


def test_trailing_sigma_excludes_tested_bar():
    base = 100 * 1.01 ** np.arange(600)
    r_base = close_returns(base)
    s_base = trailing_sigma(r_base)
    spiked = np.append(base, base[-1] * 1.50)
    s_spiked = trailing_sigma(close_returns(spiked))
    assert np.isnan(s_base[0])
    np.testing.assert_array_equal(np.isfinite(s_base), np.isfinite(s_spiked[:600]))
    fin = np.isfinite(s_base)
    np.testing.assert_allclose(s_base[fin], s_spiked[:600][fin], rtol=1e-9)
    assert int(np.where(np.isfinite(trailing_sigma(
        np.random.default_rng(1).normal(0.0, 0.02, size=700))))[0][0]) == MIN_PERIODS


def test_triggers_hand_checked_spike():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0001, 0.01, size=600)
    r = np.append(r, [np.log(1.25)])
    c = 100 * np.exp(np.cumsum(r))
    fire = triggers_of(c)
    assert fire.sum() == 1 and bool(fire[-1])
    c2 = 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.01, size=700)))
    assert triggers_of(c2).sum() == 0
    assert not fire[: MIN_PERIODS + 1].any()


def test_taper_mult_hand_checked():
    # V1 step bins: floor(d) 0-2 -> 1.6, 3-5 -> 1.3, 6-7 -> 1.0
    assert taper_mult(0.0, "V1") == 1.6
    assert taper_mult(0.5, "V1") == 1.6
    assert taper_mult(2.99, "V1") == 1.6
    assert taper_mult(3.0, "V1") == 1.3
    assert taper_mult(5.99, "V1") == 1.3
    assert taper_mult(6.0, "V1") == 1.0
    assert taper_mult(6.9, "V1") == 1.0
    assert taper_mult(7.0, "V1") == 1.0
    # V2 exp: 1 + 0.5 * 2^(-d/3)
    assert taper_mult(0.0, "V2") == 1.5
    assert abs(taper_mult(3.0, "V2") - 1.25) < 1e-12
    assert abs(taper_mult(6.0, "V2") - (1 + 0.5 * 2 ** (-2.0))) < 1e-12
    assert taper_mult(1.0, "V2") > taper_mult(3.0, "V2") > taper_mult(7.0, "V2") > 1.0
    assert V1_HI == 1.6 and V1_MID == 1.3 and V1_LO == 1.0
    assert THRESH == 4.0 and WINDOW == 540 and BOOST_DAYS == 7


def test_mults_on_grid_hand_checked():
    t0 = 1000 * DAY
    h = 4 * 3_600_000_000_000  # one 4h bar
    trig = np.array([t0], dtype=np.int64)
    # grid: before/at trigger -> 1.0; 4h after -> d~0.167 -> V1 1.6, V2 ~1.48
    grid = np.array([t0 - h, t0, t0 + h, t0 + 3 * DAY, t0 + 6 * DAY + h,
                     t0 + 7 * DAY, t0 + 7 * DAY + h], dtype=np.int64)
    m1, m2, dd = mults_on_grid(grid, trig)
    assert list(m1[:2]) == [1.0, 1.0]
    assert list(m2[:2]) == [1.0, 1.0]
    assert np.isnan(dd[0]) and np.isnan(dd[1])
    assert m1[2] == 1.6 and m1[3] == 1.3 and m1[4] == 1.0 and m1[5] == 1.0
    assert m1[6] == 1.0 and np.isnan(dd[6])  # past the 7d window
    assert abs(m2[2] - (1 + 0.5 * 2 ** (-(h / DAY) / 3))) < 1e-12
    assert m2[2] > m2[3] > m2[4] > m2[5] > 1.0
    # refresh: a re-fire 3d later restarts the taper (latest trigger wins)
    trig2 = np.array([t0, t0 + 3 * DAY], dtype=np.int64)
    g2 = np.array([t0 + 3 * DAY + h], dtype=np.int64)
    a1, a2, _ = mults_on_grid(g2, trig2)
    assert a1[0] == 1.6  # d~0.167 after the re-fire, not decayed from t0
    assert abs(a2[0] - (1 + 0.5 * 2 ** (-((h / DAY)) / 3))) < 1e-9
    # empty triggers -> all 1.0
    e1, e2, ed = mults_on_grid(grid, np.array([], dtype=np.int64))
    assert (e1 == 1.0).all() and (e2 == 1.0).all() and np.isnan(ed).all()


def test_boosted_mask_boundaries():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = boosted_mask(grid, trig, 7)
    assert list(got) == [False, False, True, True, True, False]
    assert boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0
    assert cooled_mask is boosted_mask


def test_truncation_causality_presample_bars():
    """Dropping later pre-sample bars cannot change triggers (or the taper)
    at kept times."""
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet",
                           columns=["T", "close", "sym", "shift"])
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    closes = sub["close"].to_numpy(dtype=float)
    t = pd.to_datetime(sub["T"], utc=True)
    fire_full = triggers_of(closes)
    cut = len(closes) - 500
    fire_tr = triggers_of(closes[:cut])
    assert (fire_tr == fire_full[:cut]).all()
    tc_full = np.array([(tt + pd.Timedelta(hours=4)).value for tt, f in
                        zip(t, fire_full) if f], dtype=np.int64)
    tc_tr = np.array([(tt + pd.Timedelta(hours=4)).value for tt, f in
                      zip(t[:cut], fire_tr) if f], dtype=np.int64)
    cut_close_ns = (t.iloc[cut] + pd.Timedelta(hours=4)).value
    assert set(tc_tr) == set(x for x in tc_full if x < cut_close_ns)
    grid_full = t.values.astype("datetime64[ns]").astype(np.int64)
    m1_full, m2_full, _ = mults_on_grid(grid_full, tc_full)
    m1_tr, m2_tr, _ = mults_on_grid(grid_full[:cut], tc_tr)
    np.testing.assert_array_equal(m1_tr, m1_full[:cut])
    np.testing.assert_array_equal(m2_tr, m2_full[:cut])


def test_taper_parquet_invariants():
    """Built taper grid: V1 in {1.6,1.3,1.0}, 1<=V2<=1.5, 4 shifts,
    boosted flags consistent with mults."""
    d = pd.read_parquet(MINE / "boost_mult_presample_taper.parquet")
    assert set(d["mult_V1"].round(6).unique()) <= {1.6, 1.3, 1.0}
    assert bool(((d["mult_V2"] >= 1.0 - 1e-9) & (d["mult_V2"] <= 1.5 + 1e-9)).all())
    assert set(d["shift"].unique()) == {0, 1, 2, 3}
    assert ((d["mult_V1"] > 1.0 + 1e-12) == d["boosted_V1"]).all()
    assert ((d["mult_V2"] > 1.0 + 1e-12) == d["boosted_V2"]).all()
    # V1 day-6/7 bars at 1.0 are a strict subset of the flat-B7 window
    b = pd.read_parquet(CBP / "boost_mult_presample.parquet")
    m = d.merge(b, on=["shift", "T"], suffixes=("", "_b7"))
    assert len(m) == len(d)
    assert ((m["boosted_V1"]) <= (m["mult_B7"] == 1.5)).all()
    assert ((m["boosted_V2"]) <= (m["mult_B7"] == 1.5)).all()
    tmin = pd.to_datetime(d["T"], utc=True).min()
    assert tmin <= pd.Timestamp("2017-10-16", tz="UTC")


def test_replica_reproduction_gate():
    """Reused ledger reproduces the frozen presample base sums; B7 reference
    matches the frozen oc_cboostpre B7 norms."""
    res = json.loads((MINE / "tmp/taper_presample.json").read_text())
    assert res["reproduction"]["n_fills"] == 9731
    assert res["reproduction"]["base_sums"] == [2.313362, 2.67887, 0.577643, 0.297538]
    ref = json.loads((CBP / "results.json").read_text())
    for y in range(4):
        assert abs(res["reproduction"]["b7_norms"][y]
                   - ref["B7"]["per_year"][y]["norm"]) < 5e-6
    for v in ("V1", "V2"):
        assert len(res[v]["per_year"]) == 4
        for row, trow, brow in zip(res[v]["per_year"], res[v]["timing_placebo"],
                                   res[v]["block_placebo"]):
            assert 0.0 <= trow["percentile"] <= 100.0
            assert 0.0 <= brow["percentile"] <= 100.0
            assert abs(row["norm"] - row["base"] - row["gain_vs_base"]) < 5e-6
        assert abs(res[v]["sum4_norm"] - sum(r["norm"] for r in res[v]["per_year"])) < 5e-3


def test_placebo_percentile_handchecked():
    """Percentile formula on a synthetic case: actual above all perms -> 100."""
    rng = np.random.default_rng(20261007)
    actual = 10.0
    perms = rng.normal(0, 1, size=1000)
    pct = 100.0 * (1 + int((perms <= actual).sum())) / 1001
    assert pct == 100.0
    actual2 = -10.0
    pct2 = 100.0 * (1 + int((perms <= actual2).sum())) / 1001
    assert pct2 < 5.0
