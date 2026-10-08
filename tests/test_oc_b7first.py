"""Tests for oc_b7first: hand-checked synthetics + causality on pre-sample data."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PST = ROOT / "research/tournament/oc_presampletilt"
MINE = ROOT / "research/tournament/oc_b7first"
CBP = ROOT / "research/tournament/oc_cboostpre"
sys.path.insert(0, str(MINE))

from b7first_rule import (  # noqa: E402
    BOOST,
    BOOST_DAYS,
    MIN_PERIODS,
    N7,
    N14,
    THRESH,
    WINDOW,
    boosted_mask,
    close_returns,
    cooled_mask,
    qualifying_triggers,
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


def test_qualifying_triggers_hand_checked():
    t0 = 1000 * DAY
    # isolated trigger qualifies under both N
    tq = np.array([t0], dtype=np.int64)
    assert list(qualifying_triggers(tq, 14)) == [True]
    assert list(qualifying_triggers(tq, 7)) == [True]
    # re-fire 3d later: suppressed under both (prior cascade within N days)
    t2 = np.array([t0, t0 + 3 * DAY], dtype=np.int64)
    assert list(qualifying_triggers(t2, 14)) == [True, False]
    assert list(qualifying_triggers(t2, 7)) == [True, False]
    # re-fire 10d later: suppressed under N=14, qualifies under N=7
    t3 = np.array([t0, t0 + 10 * DAY], dtype=np.int64)
    assert list(qualifying_triggers(t3, 14)) == [True, False]
    assert list(qualifying_triggers(t3, 7)) == [True, True]
    # re-fire exactly at the N-day boundary counts as within (<= span)
    t4 = np.array([t0, t0 + 7 * DAY], dtype=np.int64)
    assert list(qualifying_triggers(t4, 7)) == [True, False]
    t5 = np.array([t0, t0 + 7 * DAY + 1], dtype=np.int64)
    assert list(qualifying_triggers(t5, 7)) == [True, True]
    # chain: daily triggers -> only the first qualifies
    tc = np.array([t0 + i * DAY for i in range(5)], dtype=np.int64)
    assert list(qualifying_triggers(tc, 14)) == [True, False, False, False, False]
    # empty + unsorted input
    assert qualifying_triggers(np.array([], dtype=np.int64), 14).size == 0
    uns = np.array([t0 + 3 * DAY, t0], dtype=np.int64)
    assert list(qualifying_triggers(uns, 14)) == [False, True]
    assert N14 == 14 and N7 == 7 and BOOST == 1.5 and BOOST_DAYS == 7
    assert THRESH == 4.0 and WINDOW == 540


def test_first_cascade_no_stack_no_extend():
    """Re-fires inside the window neither stack nor extend: with N=14 and two
    triggers 3d apart, the boosted set equals the 7d window of the first only."""
    t0 = 1000 * DAY
    h = 3_600_000_000_000
    trig = np.array([t0, t0 + 3 * DAY], dtype=np.int64)
    q = trig[qualifying_triggers(trig, 14)]
    assert list(q) == [t0]
    grid = np.array([t0 + h, t0 + 3 * DAY + h, t0 + 7 * DAY,
                     t0 + 7 * DAY + h, t0 + 10 * DAY, t0 + 10 * DAY + h],
                    dtype=np.int64)
    got = boosted_mask(grid, q, 7)
    # 7d after FIRST trigger only: +7d+h (4d after the dropped re-fire) is out
    assert list(got) == [True, True, True, False, False, False]
    # plain (stacking) mask on both triggers extends through +7d+h
    stacked = boosted_mask(grid, trig, 7)
    assert list(stacked) == [True, True, True, True, True, False]
    assert cooled_mask is boosted_mask


def test_boosted_mask_boundaries():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = boosted_mask(grid, trig, 7)
    assert list(got) == [False, False, True, True, True, False]
    assert boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0


def test_truncation_causality_presample_bars():
    """Dropping later pre-sample bars cannot change triggers (or the
    first-cascade filter) at kept times."""
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
    # truncated trigger set = full triggers strictly before the cut close
    cut_close_ns = (t.iloc[cut] + pd.Timedelta(hours=4)).value
    assert set(tc_tr) == set(x for x in tc_full if x < cut_close_ns)
    for n in (7, 14):
        q_full = qualifying_triggers(tc_full, n)
        q_tr = qualifying_triggers(tc_tr, n)
        # kept-prefix qualifying flags are identical (filter is causal:
        # only strictly-earlier triggers suppress)
        full_kept = tc_full < cut_close_ns
        assert list(tc_full[full_kept]) == list(tc_tr)
        assert list(q_full[full_kept]) == list(q_tr)


def test_first_parquet_invariants():
    """Built first-cascade grid: mults in {1.0, 1.5}, F14 subset of F7, 4 shifts."""
    d = pd.read_parquet(MINE / "boost_mult_presample_first.parquet")
    assert set(d["mult_F14"].unique()) <= {1.0, 1.5}
    assert set(d["mult_F7"].unique()) <= {1.0, 1.5}
    assert ((d["mult_F14"] == 1.5) <= (d["mult_F7"] == 1.5)).all()
    assert set(d["shift"].unique()) == {0, 1, 2, 3}
    tmin = pd.to_datetime(d["T"], utc=True).min()
    assert tmin <= pd.Timestamp("2017-10-16", tz="UTC")


def test_first_subset_of_b7():
    """First-cascade filtering can only un-boost: every F-boosted bar is B7-boosted."""
    f = pd.read_parquet(MINE / "boost_mult_presample_first.parquet")
    b = pd.read_parquet(CBP / "boost_mult_presample.parquet")
    m = f.merge(b, on=["shift", "T"], suffixes=("", "_b7"))
    assert len(m) == len(f)
    assert ((m["mult_F14"] == 1.5) <= (m["mult_B7"] == 1.5)).all()
    assert ((m["mult_F7"] == 1.5) <= (m["mult_B7"] == 1.5)).all()


def test_replica_reproduction_gate():
    """Reused ledger reproduces the frozen presample base sums; B7 reference
    matches the frozen oc_cboostpre B7 norms."""
    res = json.loads((MINE / "tmp/boost_presample_first.json").read_text())
    assert res["reproduction"]["n_fills"] == 9731
    assert res["reproduction"]["base_sums"] == [2.313362, 2.67887, 0.577643, 0.297538]
    ref = json.loads((CBP / "results.json").read_text())
    for y in range(4):
        assert abs(res["reproduction"]["b7_norms"][y]
                   - ref["B7"]["per_year"][y]["norm"]) < 5e-6
    for v in ("F14", "F7"):
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
