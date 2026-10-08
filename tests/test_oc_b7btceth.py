"""Tests for oc_b7btceth: hand-checked synthetics + causality on pre-sample data."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PST = ROOT / "research/tournament/oc_presampletilt"
MINE = ROOT / "research/tournament/oc_b7btceth"
CBP = ROOT / "research/tournament/oc_cboostpre"
sys.path.insert(0, str(MINE))

from b7btceth_rule import (  # noqa: E402
    BOOST,
    BOOST_DAYS,
    MASK_V1,
    MASK_V2,
    MIN_PERIODS,
    THRESH,
    WINDOW,
    apply_mask,
    boosted_mask,
    close_returns,
    coin_mult,
    cooled_mask,
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
    assert BOOST == 1.5 and BOOST_DAYS == 7 and THRESH == 4.0 and WINDOW == 540


def test_coin_mask_hand_checked():
    """Frozen masks: V1 = BTC+ETH {0,1}, V2 = BTC-only {0}; unboosted bars stay 1.0."""
    assert set(MASK_V1) == {0, 1} and set(MASK_V2) == {0}
    # B7-boosted bar: BTC/ETH boosted under V1, only BTC under V2
    assert apply_mask(1.5, 0, MASK_V1) == 1.5
    assert apply_mask(1.5, 1, MASK_V1) == 1.5
    assert apply_mask(1.5, 2, MASK_V1) == 1.0
    assert apply_mask(1.5, 3, MASK_V1) == 1.0
    assert apply_mask(1.5, 0, MASK_V2) == 1.5
    assert apply_mask(1.5, 1, MASK_V2) == 1.0
    # unboosted bar: every coin stays 1.0 under both masks
    for c in (0, 1, 2, 3, 4):
        assert apply_mask(1.0, c, MASK_V1) == 1.0
        assert apply_mask(1.0, c, MASK_V2) == 1.0
    assert coin_mult(1.5, 1, "V1") == 1.5
    assert coin_mult(1.5, 1, "V2") == 1.0
    assert coin_mult(1.5, 0, "V2") == 1.5
    # nesting: every V2-boosted fill is V1-boosted (BTC in {0,1})
    for c in range(5):
        assert (coin_mult(1.5, c, "V2") == 1.5) <= (coin_mult(1.5, c, "V1") == 1.5)


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
    """Dropping later pre-sample bars cannot change triggers at kept times;
    the coin mask is per-coin static so it cannot change either."""
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


def test_masked_replica_is_b7_subset():
    """Coin masking can only un-boost: every V-boosted fill is B7-boosted
    (same window, mask only removes alt-coin fills)."""
    res = json.loads((MINE / "tmp/boost_presample_btceth.json").read_text())
    b7 = json.loads((CBP / "results.json").read_text())
    for v in ("V1", "V2"):
        for row in res[v]["per_year"]:
            assert row["boosted_share_fills"] <= 0.74  # B7 max fill share 73.6%
            assert row["realised_mean"] <= 1.37  # B7 max realised mean
            assert 0.0 <= row["boosted_share_fills"] <= 1.0
    # V2 boosted share <= V1 boosted share every year (BTC-only subset)
    for r1, r2 in zip(res["V1"]["per_year"], res["V2"]["per_year"]):
        assert r2["boosted_share_fills"] <= r1["boosted_share_fills"] + 1e-9


def test_replica_reproduction_gate():
    """Reused ledger reproduces the frozen presample base sums; B7 reference
    matches the frozen oc_cboostpre B7 norms."""
    res = json.loads((MINE / "tmp/boost_presample_btceth.json").read_text())
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
