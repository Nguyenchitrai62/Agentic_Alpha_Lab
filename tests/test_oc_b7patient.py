"""Tests for oc_b7patient: hand-checked synthetics + causality on pre-sample data."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PST = ROOT / "research/tournament/oc_presampletilt"
MINE = ROOT / "research/tournament/oc_b7patient"
sys.path.insert(0, str(MINE))

from patient_rule import (  # noqa: E402
    B7_DAYS,
    BOOST,
    MIN_PERIODS,
    MU_V1,
    THRESH,
    WINDOW,
    boosted_mask,
    close_returns,
    compute_sigma,
    cooled_mask,
    find_fill,
    outcome_extended,
    outcome_kind,
    outcome_ret,
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
    assert not fire[: MIN_PERIODS + 1].any()
    assert THRESH == 4.0 and WINDOW == 540
    assert BOOST == 1.5 and B7_DAYS == 7


def test_boosted_mask_boundaries():
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = boosted_mask(grid, trig, 7)
    assert list(got) == [False, False, True, True, True, False]
    assert cooled_mask is boosted_mask


def test_outcome_v1_patient_tp_hand_checked():
    # Flat at lv then a late spike that clears 1.0sg TP but the V1 TP (1.5sg)
    # needs a bigger spike: base TP hits, V1 does not -> V1 stays to timeout.
    lv, sg = 100.0, 0.01
    Ha = np.full(240, 100.0)
    La = np.full(240, 100.0)
    Ca = np.full(240, 100.0)
    Oa = np.full(240, 100.0)
    # spike +1.2sg clears base tp (1.0) but not V1 tp (1.5)
    Ha[30] = lv * (1 + 1.2 * sg)
    rb, _, kb = outcome_ret(Ha, La, Ca, Oa, 16, lv, sg, 1.0, 100.0, False)
    r1, _, k1 = outcome_ret(Ha, La, Ca, Oa, 16, lv, sg, MU_V1, 100.0, False)
    assert kb == "tp" and k1 == "time"
    assert np.isfinite(rb) and np.isfinite(r1)
    assert r1 < rb  # wider TP misses this spike -> worse here (room costs)
    # bigger spike +2sg clears both
    Ha2 = np.full(240, 100.0)
    Ha2[30] = lv * (1 + 2.0 * sg)
    rb2, _, kb2 = outcome_ret(Ha2, La, Ca, Oa, 16, lv, sg, 1.0, 100.0, False)
    r12, _, k12 = outcome_ret(Ha2, La, Ca, Oa, 16, lv, sg, MU_V1, 100.0, False)
    assert kb2 == "tp" and k12 == "tp"
    assert r12 > rb2  # wider TP pays more when hit
    # stop-first kept under V1: backstop at same bar as TP -> backstop wins
    La3 = np.full(240, 100.0)
    La3[30] = lv * (1 - 9 * sg)
    _, _, k3 = outcome_ret(Ha2, La3, Ca, Oa, 16, lv, sg, MU_V1, 100.0, False)
    assert k3 == "backstop"
    Ha0 = np.full(240, 100.0)
    La0 = np.full(240, 100.0)
    Ca0 = np.full(240, 100.0)
    Oa0 = np.full(240, 100.0)
    assert outcome_kind(Ha0, La0, Ca0, Oa0, 16, lv, sg) == "time"


def test_outcome_extended_hand_checked():
    # Base timeout then extension TP in the second clock -> V2 tp.
    lv, sg = 100.0, 0.01
    tp = lv * (1 + 1.0 * sg)
    Hb = np.full(240, 100.0)
    Lb = np.full(240, 100.0)
    Cb = np.full(240, 100.0)
    Ob = np.full(240, 100.0)
    Hb[50] = tp * 1.01  # second-clock TP touch
    r, k = outcome_extended(Hb, Lb, Cb, Ob, lv, sg, 1.0, 100.0, False, False)
    assert k == "tp"
    assert abs(r - (tp / lv - 1 - 2 * 0.0002)) < 1e-12
    # funding: mid settle adds -0.0001; end settle on timeout adds another
    r2, k2 = outcome_extended(Hb, Lb, Cb, Ob, lv, sg, 1.0, 100.0, True, False)
    assert k2 == "tp" and abs(r2 - (r - 0.0001)) < 1e-12
    Hf = np.full(240, 100.0)
    r3, k3 = outcome_extended(Hf, Lb, Cb, Ob, lv, sg, 1.0, 100.0, True, True)
    assert k3 == "time"
    assert abs(r3 - (100.0 / lv - 1 - 0.0002 - 0.00055 - 0.0002)) < 1e-9
    # second-clock stop-first: backstop at same index as TP -> backstop wins
    Lb2 = np.full(240, 100.0)
    Lb2[50] = lv * (1 - 9 * sg)
    _, k4 = outcome_extended(Hb, Lb2, Cb, Ob, lv, sg, 1.0, 100.0, False, False)
    assert k4 == "backstop"
    # close5 continuity: close <= sl on a (m+1)%5==0 minute in 240..479
    Cb5 = np.full(240, 100.0)
    sl = lv * (1 - 4.0 * sg)
    # absolute m=244 -> (244+1)%5==0, index j=4
    Cb5[4] = sl * 0.99
    _, k5 = outcome_extended(Hf, Lb, Cb5, Ob, lv, sg, 1.0, 100.0, False, False)
    assert k5 == "stop"
    assert find_fill(np.array([100.0, 99.0, 98.0]), 99.0) == 2


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
    bars = pd.read_parquet(PST / "bars_4h_presample.parquet")
    b = bars[(bars["sym"] == "ETHUSDT") & (bars["shift"] == 2)].sort_values("T")
    cut = pd.Timestamp("2019-06-01", tz="UTC")
    b_tr = b[b["T"] < cut].reset_index(drop=True)
    got = compute_sigma(b_tr["open"].to_numpy(dtype=float))
    ref_full = compute_sigma(b.sort_values("T")["open"].to_numpy(dtype=float))
    n = len(b_tr)
    np.testing.assert_allclose(got, ref_full[:n], rtol=1e-12, atol=1e-15,
                               equal_nan=True)
