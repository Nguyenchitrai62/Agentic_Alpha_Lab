"""Tests for oc_cboostpre: hand-checked synthetics + causality on pre-sample data."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PST = ROOT / "research/tournament/oc_presampletilt"
MINE = ROOT / "research/tournament/oc_cboostpre"
sys.path.insert(0, str(MINE))

from cboostpre_rule import (  # noqa: E402
    B3_DAYS,
    B7_DAYS,
    BOOST,
    MIN_PERIODS,
    THRESH,
    WINDOW,
    boosted_mask,
    close_returns,
    compute_sigma,
    cooled_mask,
    find_fill,
    outcome_kind,
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
    rng = np.random.default_rng(1)
    rn = rng.normal(0.0, 0.02, size=700)
    sn = trailing_sigma(rn)
    assert int(np.where(np.isfinite(sn))[0][0]) == MIN_PERIODS
    i = 600
    np.testing.assert_allclose(sn[i], np.std(rn[i - WINDOW:i], ddof=1), rtol=1e-12)


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


def test_boosted_mask_boundaries():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = boosted_mask(grid, trig, 7)
    assert list(got) == [False, False, True, True, True, False]
    got3 = boosted_mask(grid, trig, 3)
    assert list(got3) == [False, False, True, False, False, False]
    assert boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0
    trig2 = np.array([t0, t0 + 6 * DAY], dtype=np.int64)
    g2 = np.array([t0 + 7 * DAY + h], dtype=np.int64)
    assert bool(boosted_mask(g2, trig2, 7)[0])
    assert cooled_mask is boosted_mask
    assert BOOST == 1.5 and B7_DAYS == 7 and B3_DAYS == 3
    assert THRESH == 4.0 and WINDOW == 540


def test_outcome_kind_hand_checked():
    # flat market at lv: never hits stop/backstop/tp -> time
    lv, sg = 100.0, 0.01
    Ha = np.full(240, 100.0)
    La = np.full(240, 100.0)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    assert outcome_kind(Ha, La, Ca, Oa, 16, lv, sg) == "time"
    # immediate TP spike after fill -> tp
    Ha2 = Ha.copy()
    Ha2[20] = lv * (1 + 2 * sg)
    assert outcome_kind(Ha2, La, Ca, Oa, 16, lv, sg) == "tp"
    # backstop first (low <= bl at same bar as tp) -> backstop wins
    La3 = La.copy()
    La3[20] = lv * (1 - 9 * sg)
    Ha3 = Ha2.copy()
    assert outcome_kind(Ha3, La3, Ca, Oa, 16, lv, sg) == "backstop"
    # close5 stop (close <= sl on a 5-multiple bar) with no backstop/tp -> stop
    Ca4 = Ca.copy()
    sl = lv * (1 - 4.0 * sg)
    Ca4[19] = sl * 0.99  # minute index f+1+3 = 20 -> (20)%5==0 stop bar
    assert outcome_kind(Ha, La, Ca4, Oa, 16, lv, sg) == "stop"
    # find_fill strict trade-through
    assert find_fill(np.array([100.0, 99.0, 98.0]), 99.0) == 2
    assert find_fill(np.array([100.0, 99.0]), 90.0) is None


def test_truncation_causality_presample_bars():
    """Dropping later pre-sample bars cannot change triggers at kept times."""
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet",
                           columns=["T", "close", "sym", "shift"])
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    closes = sub["close"].to_numpy(dtype=float)
    fire_full = triggers_of(closes)
    cut = len(closes) - 500
    fire_tr = triggers_of(closes[:cut])
    assert (fire_tr == fire_full[:cut]).all()


def test_compute_sigma_truncation_causality():
    """Ledger sigma recomputed from truncated opens is identical on kept prefix."""
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet")
    b = bars[(bars["sym"] == "ETHUSDT") & (bars["shift"] == 2)].sort_values("T")
    cut = pd.Timestamp("2019-06-01", tz="UTC")
    b_tr = b[b["T"] < cut].reset_index(drop=True)
    got = compute_sigma(b_tr["open"].to_numpy(dtype=float))
    ref_full = compute_sigma(b.sort_values("T")["open"].to_numpy(dtype=float))
    n = len(b_tr)
    np.testing.assert_allclose(got, ref_full[:n], rtol=1e-12, atol=1e-15,
                               equal_nan=True)


def test_boost_parquet_invariants():
    """Built pre-sample grid: mults in {1.0, 1.5}, B3 subset of B7, 4 shifts."""
    d = pd.read_parquet(MINE / "boost_mult_presample.parquet")
    assert set(d["mult_B7"].unique()) <= {1.0, 1.5}
    assert set(d["mult_B3"].unique()) <= {1.0, 1.5}
    assert ((d["mult_B3"] == 1.5) <= (d["mult_B7"] == 1.5)).all()
    assert set(d["shift"].unique()) == {0, 1, 2, 3}
    tmin = pd.to_datetime(d["T"], utc=True).min()
    assert tmin <= pd.Timestamp("2017-10-16", tz="UTC")


def test_ledger_interval_truncation():
    """Ledger fills sit on bars with open inside their own pre-sample interval."""
    bt = np.load(PST / "tmp/bt_presample.npy", allow_pickle=True)
    led = dict(np.load(PST / "tmp/ledger_presample.npz"))
    bounds = {
        0: (pd.Timestamp("2017-10-16", tz="UTC"), pd.Timestamp("2018-01-01", tz="UTC")),
        1: (pd.Timestamp("2018-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
        2: (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2020-01-01", tz="UTC")),
        3: (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2020-09-01", tz="UTC")),
    }
    assert len(bt) == 9731 == len(led["w"])
    for y, (S, E) in bounds.items():
        m = led["year"] == y
        assert m.any()
        for t in pd.DatetimeIndex([pd.Timestamp(x) for x in bt[m]]):
            assert S <= t < E


def test_replica_reproduction_gate():
    """Reused ledger reproduces the frozen presample base sums."""
    res = json.loads((MINE / "tmp/boost_presample.json").read_text())
    assert res["reproduction"]["n_fills"] == 9731
    assert res["reproduction"]["base_sums"] == [2.313362, 2.67887, 0.577643, 0.297538]
    for v in ("B7", "B3"):
        assert len(res[v]["per_year"]) == 4
        for row, trow, brow in zip(res[v]["per_year"], res[v]["timing_placebo"],
                                   res[v]["block_placebo"]):
            assert 0.0 <= trow["percentile"] <= 100.0
            assert 0.0 <= brow["percentile"] <= 100.0
            assert abs(row["norm"] - row["base"] - row["gain"]) < 5e-6


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


def test_stop_kinds_sanity():
    """Kind recompute covers ~all fills; pooled stop rate is a small share."""
    st = json.loads((MINE / "tmp/stop_presample.json").read_text())
    assert st["config"]["unknown"] <= 30  # got 15; loose bound guards regressions
    tot = sum(r["n_fills"] for r in st["per_year"])
    known = sum(r["n_known"] for r in st["per_year"])
    assert tot == 9731 and known >= 9700
    for r in st["per_year"]:
        assert 0.0 <= r["base_stop_rate"] <= 0.30
        assert -0.10 <= r["B7_stop_delta"] <= 0.10
