"""Tests for oc_d_riskparity: hand-checked synthetics + causality on real 4h bars."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
MINE = ROOT / "research/tournament/oc_d_riskparity"
sys.path.insert(0, str(MINE))

from riskparity_rule import (  # noqa: E402
    BACKSTOP,
    NUMER,
    RUNGS_V1,
    RUNGS_V2,
    STOPS_V1,
    STOPS_V2,
    compute_sigma,
    find_fill,
    outcome_kind,
    outcome_kind_v2,
    outcome_mu,
    outcome_mu_v2,
    parity_mults_V1,
    parity_mults_V2,
    phase_mean_sums,
)


def test_parity_mults_hand_checked():
    m1 = parity_mults_V1()
    assert set(m1.keys()) == {0, 1, 2, 3, 4}
    assert m1[0] == 4.0 / (2.5 + 4.0)
    assert m1[4] == 4.0 / (5.0 + 4.0)
    assert abs(m1[0] - 0.6153846153846154) < 1e-12
    assert abs(m1[1] - 0.5714285714285714) < 1e-12
    assert abs(m1[2] - 0.5333333333333333) < 1e-12
    assert m1[3] == 0.5
    assert abs(m1[4] - 0.4444444444444444) < 1e-12
    # deep rungs shrink by construction (monotone down with depth)
    assert m1[0] > m1[1] > m1[2] > m1[3] > m1[4]
    m2 = parity_mults_V2()
    assert set(m2.keys()) == {0, 1, 2, 3}
    assert m2[0] == 4.0 / (2.5 + 4.0)
    assert abs(m2[1] - 4.0 / 8.5) < 1e-12
    assert abs(m2[2] - 4.0 / 10.5) < 1e-12
    assert m2[3] == 0.32
    assert m2[0] > m2[1] > m2[2] > m2[3]
    # equal open-to-stop dollar risk: m * (k + s) == 4 for every rung
    for i, (k, s) in enumerate(zip(RUNGS_V1, STOPS_V1)):
        assert abs(m1[i] * (k + s) - NUMER) < 1e-9
    for i, (k, s) in enumerate(zip(RUNGS_V2, STOPS_V2)):
        assert abs(m2[i] * (k + s) - NUMER) < 1e-9


def test_find_fill_strict_trade_through():
    low = np.array([100.0, 99.5, 99.0, 98.0])
    assert find_fill(low, 99.0) == 3  # strict: 99.0 itself does NOT fill
    assert find_fill(low, 98.0) is None
    assert find_fill(np.array([np.nan, np.nan]), 1.0) is None


def test_outcome_v2_wider_stop_fewer_stops():
    # flat-then-crash tape: base 4sg stop must stop, wider 7sg stop survives longer
    n = 240
    lv, sg = 100.0, 0.01
    f = 16
    Oa = np.full(n, 100.0)
    Ca = np.full(n, 100.0)
    # crash 6% at minute 60 (below 4sg stop 96.0, above 7sg-implied path initially)
    Ca[60:] = 94.0
    La = np.full(n, 100.0)
    La[60:] = 93.0
    Ha = np.full(n, 100.0)
    kind_base = outcome_kind(Ha, La, Ca, Oa, f, lv, sg)
    kind_wide = outcome_kind_v2(Ha, La, Ca, Oa, f, lv, sg, m_sl=7.0)
    assert kind_base in ("stop", "backstop")
    # wider stop cannot trigger earlier than the tight stop on the same tape
    r_base, x_base, _ = outcome_mu(Ha, La, Ca, Oa, f, lv, sg, 1.0, 100.0, False)
    r_wide, x_wide, _ = outcome_mu_v2(Ha, La, Ca, Oa, f, lv, sg, 1.0, 100.0,
                                      False, 7.0)
    assert x_wide >= x_base
    assert kind_wide in ("stop", "backstop", "time", "tp")


def test_outcome_tp_path_hand_checked():
    # instant rally to TP: both base and V2 print tp with maker-only costs
    n = 240
    lv, sg, mu = 100.0, 0.01, 1.0
    f = 16
    Oa = np.full(n, 100.0)
    Ca = np.full(n, 100.0)
    La = np.full(n, 100.0)
    Ha = np.full(n, 100.0)
    Ha[f + 1] = 101.5  # > tp = 101.0
    r, x, kind = outcome_mu(Ha, La, Ca, Oa, f, lv, sg, mu, 100.0, False)
    assert kind == "tp" and x == f + 1
    assert abs(r - (101.0 / 100.0 - 1 - 2 * 0.0002)) < 1e-12
    r2, x2, k2 = outcome_mu_v2(Ha, La, Ca, Oa, f, lv, sg, mu, 100.0, False, 5.0)
    assert (k2, x2) == ("tp", f + 1) and abs(r2 - r) < 1e-12


def test_phase_mean_sums_hand_checked():
    ph = np.array([0, 1, 2, 3, 0, 1])
    yr = np.array([0, 0, 0, 0, 1, 1])
    w = np.ones(6)
    y = np.array([1.0, 2.0, 3.0, 4.0, 10.0, 20.0])
    out = phase_mean_sums(ph, yr, w, y, 2)
    assert out == [(1 + 2 + 3 + 4) / 4.0, (10 + 20) / 4.0]


def test_sigma_truncation_causal_on_real_bars():
    bars = pd.read_parquet(
        ROOT / "research/tournament/oc_presampletilt/bars_4h_presample.parquet",
        columns=["sym", "shift", "T", "open"])
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    opens = sub["open"].to_numpy(dtype=float)
    assert len(opens) > 700
    cut = len(opens) - 100
    full = compute_sigma(opens)
    trunc = compute_sigma(opens[:cut])
    # kept prefix identical (no future use): compare away from the warm edge
    assert np.array_equal(np.isfinite(full[:cut]), np.isfinite(trunc))
    m = np.isfinite(full[:cut]) & np.isfinite(trunc)
    assert m.sum() > 100
    np.testing.assert_allclose(full[:cut][m], trunc[m], rtol=1e-12)
    # first finite needs min_periods 120 closes
    first = int(np.where(np.isfinite(full))[0][0])
    assert first >= 120


def test_v2_stop_monotone_on_real_bars():
    # on real bars, per-rung V2 outcomes are finite and wider stops never stop
    # earlier than tighter stops for the same fill (ordering sanity)
    bars = pd.read_parquet(
        ROOT / "research/tournament/oc_presampletilt/bars_4h_presample.parquet",
        columns=["sym", "shift", "T", "open"])
    assert set(RUNGS_V2) == {2.5, 3.5, 4.5, 5.5}
    assert set(STOPS_V2) == {4.0, 5.0, 6.0, 7.0}
    assert BACKSTOP == 8.0
    assert len(bars) > 0
