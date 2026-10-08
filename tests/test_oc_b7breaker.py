"""Tests for oc_b7breaker: hand-checked synthetics + causality on pre-sample data."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PST = ROOT / "research/tournament/oc_presampletilt"
MINE = ROOT / "research/tournament/oc_b7breaker"
sys.path.insert(0, str(MINE))

from breaker_rule import (  # noqa: E402
    B7_DAYS,
    BOOST,
    MIN_PERIODS,
    THRESH,
    V1_K,
    V1_M,
    V2_K,
    V2_M,
    WINDOW,
    boosted_mask,
    breaker_active_mask,
    breaker_mult,
    close_returns,
    compute_sigma,
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
    assert (V1_K, V1_M) == (2, 14) and (V2_K, V2_M) == (3, 21)
    assert BOOST == 1.5 and B7_DAYS == 7 and THRESH == 4.0 and WINDOW == 540


def test_boosted_mask_boundaries():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = boosted_mask(grid, trig, 7)
    assert list(got) == [False, False, True, True, True, False]
    assert boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0


def test_breaker_active_mask_hand_checked():
    # V1: >= 2 cascades in trailing 14d (inclusive both ends, tc == T counts)
    t0 = 1000 * DAY
    trig = np.array([t0, t0 + 10 * DAY], dtype=np.int64)
    grid = np.array([
        t0,                      # 1 cascade in window -> inactive
        t0 + 10 * DAY,           # 2 in window (incl. tc == T) -> active
        t0 + 10 * DAY + 1,       # still 2 -> active
        t0 + 14 * DAY,           # T-tc0 = 14d <= 14d -> active (inclusive upper)
        t0 + 14 * DAY + 1,       # tc0 aged out, only tc1 -> inactive
        t0 + 24 * DAY + 1,       # both aged out -> inactive
    ], dtype=np.int64)
    got = breaker_active_mask(grid, trig, 2, 14)
    assert list(got) == [False, True, True, True, False, False]
    # V2 needs 3 in 21d: same two triggers never fire it
    assert not breaker_active_mask(grid, trig, 3, 21).any()
    # three clustered triggers fire V2
    trig3 = np.array([t0, t0 + 10 * DAY, t0 + 20 * DAY], dtype=np.int64)
    g3 = np.array([t0 + 20 * DAY, t0 + 21 * DAY, t0 + 21 * DAY + 1], dtype=np.int64)
    assert list(breaker_active_mask(g3, trig3, 3, 21)) == [True, True, False]
    # empty trigger history -> never active
    assert not breaker_active_mask(grid, np.array([], dtype=np.int64), 2, 14).any()


def test_breaker_mult_hand_checked():
    b7 = np.array([False, True, True, False])
    br = np.array([False, False, True, True])
    assert list(breaker_mult(b7, br)) == [1.0, 1.5, 1.0, 1.0]
    # breaker can only remove boost, never add it
    assert (breaker_mult(np.zeros(4, dtype=bool), np.ones(4, dtype=bool)) == 1.0).all()


def test_outcome_kind_hand_checked():
    lv, sg = 100.0, 0.01
    Ha = np.full(240, 100.0)
    La = np.full(240, 100.0)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    assert outcome_kind(Ha, La, Ca, Oa, 16, lv, sg) == "time"
    Ha2 = Ha.copy()
    Ha2[20] = lv * (1 + 2 * sg)
    assert outcome_kind(Ha2, La, Ca, Oa, 16, lv, sg) == "tp"
    La3 = La.copy()
    La3[20] = lv * (1 - 9 * sg)
    assert outcome_kind(Ha2, La3, Ca, Oa, 16, lv, sg) == "backstop"
    Ca4 = Ca.copy()
    sl = lv * (1 - 4.0 * sg)
    Ca4[19] = sl * 0.99
    assert outcome_kind(Ha, La, Ca4, Oa, 16, lv, sg) == "stop"
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


def test_breaker_truncation_causality():
    """Breaker counts from truncated bars are identical on the kept prefix."""
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet",
                           columns=["T", "close", "sym", "shift"])
    sub = bars[(bars["sym"] == "ETHUSDT") & (bars["shift"] == 2)].sort_values("T")
    t = pd.to_datetime(sub["T"], utc=True)
    c = sub["close"].to_numpy(dtype=float)
    fire = triggers_of(c)
    tc = (t[fire] + pd.Timedelta(hours=4)).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    grid = t.values.astype("datetime64[ns]").astype(np.int64)
    cut = len(grid) - 700
    br_full = breaker_active_mask(grid, tc, V1_K, V1_M)
    tc_tr = tc[tc < grid[cut]]
    br_tr = breaker_active_mask(grid[:cut], tc_tr, V1_K, V1_M)
    assert (br_tr == br_full[:cut]).all()


def test_breaker_parquet_invariants():
    """Built grids: mults in {1.0, 1.5}, V-subset of B7, B7 matches oc_cboostpre."""
    d = pd.read_parquet(MINE / "breaker_mult_presample.parquet")
    assert set(d["mult_B7"].unique()) <= {1.0, 1.5}
    assert set(d["mult_V1"].unique()) <= {1.0, 1.5}
    assert set(d["mult_V2"].unique()) <= {1.0, 1.5}
    assert ((d["mult_V1"] == 1.5) <= (d["mult_B7"] == 1.5)).all()
    assert ((d["mult_V2"] == 1.5) <= (d["mult_B7"] == 1.5)).all()
    assert set(d["shift"].unique()) == {0, 1, 2, 3}
    ref = pd.read_parquet(ROOT / "research/tournament/oc_cboostpre/boost_mult_presample.parquet")
    m = d.merge(ref[["shift", "T", "mult_B7"]].rename(columns={"mult_B7": "ref"}),
                on=["shift", "T"], how="inner")
    assert len(m) == len(d) == len(ref)
    assert (m["mult_B7"].to_numpy() == m["ref"].to_numpy()).all()


def test_replica_reproduction_and_beats_rule():
    """Ledger reproduces frozen base sums; B7 gains reproduce; beats rule is mechanical."""
    res = json.loads((MINE / "tmp/breaker_presample.json").read_text())
    assert res["reproduction"]["n_fills"] == 9731
    assert res["reproduction"]["base_sums"] == [2.313362, 2.67887, 0.577643, 0.297538]
    exp_gain = [0.045913, 0.078085, 0.111004, -0.069459]
    for row, g in zip(res["B7"]["per_year"], exp_gain):
        assert abs(row["gain_vs_base"] - g) < 2e-6
        assert abs(row["norm"] - row["base"] - row["gain_vs_base"]) < 5e-6
    for v in ("V1", "V2"):
        assert len(res[v]["per_year"]) == 4
        for row, trow, brow in zip(res[v]["per_year"], res[v]["timing_placebo"],
                                   res[v]["block_placebo"]):
            assert 0.0 <= trow["percentile"] <= 100.0
            assert 0.0 <= brow["percentile"] <= 100.0
    for v in ("V1", "V2"):
        d = [r["delta_vs_B7"] for r in res[v]["per_year"]]
        b = res["beats_B7"][v]
        assert b["beats_B7"] == (sum(d) > 0 and d[3] > 0)


def test_stop_kinds_sanity_and_safety_flag():
    """Kind recompute covers ~all fills; safety flag is mechanical (>+1pp pooled)."""
    st = json.loads((MINE / "tmp/stop_breaker.json").read_text())
    assert st["config"]["unknown"] <= 30
    tot = sum(r["n_fills"] for r in st["per_year"])
    known = sum(r["n_known"] for r in st["per_year"])
    assert tot == 9731 and known >= 9700
    for v in ("B7", "V1", "V2"):
        p = st[f"{v}_pooled"]
        assert p["safety_fail"] == (p["stop_delta"] > 0.01)


def test_secondary_reproduction():
    """2021-2026 leg: ledger reproduces; B7 dSum reproduces cascadeboost (+2.946)."""
    res = json.loads((MINE / "tmp/breaker_4shift.json").read_text())
    assert res["reproduction"]["n_fills"] == 22312
    assert abs(res["reproduction"]["base_sum5y"] - 7.718304) <= 0.002
    assert abs(res["B7"]["dSum5y"] - 2.946428) <= 0.01
    assert res["B7"]["sum_half_years_ge"] == 5
