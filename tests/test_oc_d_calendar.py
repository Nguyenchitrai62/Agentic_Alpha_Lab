"""Tests for oc_d_calendar (frozen UTC-window rule; PLAN.md first, no outcome used here)."""
import numpy as np
import pandas as pd

from research.tournament.oc_d_calendar.calendar_rule import (
    find_fill,
    mult_at,
    mult_V1,
    mult_V2,
    outcome_kind,
)


def test_v1_weekend_boundaries():
    # 2020-03-12 Thursday (COVID crash day) -> NOT boosted by construction
    assert mult_V1(pd.Timestamp("2020-03-12 04:00", tz="UTC")) == 1.0
    # Saturday / Sunday UTC -> boosted
    assert mult_V1(pd.Timestamp("2020-03-14 00:00", tz="UTC")) == 1.25  # Sat
    assert mult_V1(pd.Timestamp("2020-03-15 20:00", tz="UTC")) == 1.25  # Sun
    # Monday 00:00 UTC -> not boosted
    assert mult_V1(pd.Timestamp("2020-03-16 00:00", tz="UTC")) == 1.0
    # Friday late -> not boosted
    assert mult_V1(pd.Timestamp("2020-03-13 23:00", tz="UTC")) == 1.0


def test_v2_session_boundaries():
    assert mult_V2(pd.Timestamp("2020-03-12 00:00", tz="UTC")) == 1.2
    assert mult_V2(pd.Timestamp("2020-03-12 07:59", tz="UTC")) == 1.2
    assert mult_V2(pd.Timestamp("2020-03-12 08:00", tz="UTC")) == 1.0
    assert mult_V2(pd.Timestamp("2020-03-12 23:00", tz="UTC")) == 1.0
    # naive timestamp treated as UTC
    assert mult_V2(pd.Timestamp("2020-03-12 04:00")) == 1.2


def test_missing_nat_inert():
    assert mult_V1(pd.NaT) == 1.0
    assert mult_V2(pd.NaT) == 1.0
    assert mult_at(pd.NaT, "V1") == 1.0
    assert mult_at(pd.NaT, "V2") == 1.0


def test_truncation_causality_synthetic():
    # timestamps-only rule: truncating the grid cannot change kept-prefix mults
    full = pd.to_datetime([
        "2020-03-12 00:00", "2020-03-12 04:00", "2020-03-13 00:00",
        "2020-03-14 00:00", "2020-03-15 04:00", "2020-03-16 00:00",
    ], utc=True)
    cut = pd.Timestamp("2020-03-14 00:00", tz="UTC")
    kept = full[full < cut]
    for v in ("V1", "V2"):
        a = np.array([mult_at(t, v) for t in full[:len(kept)]])
        b = np.array([mult_at(t, v) for t in kept])
        assert (a == b).all()


def test_find_fill_strict_trade_through():
    assert find_fill(np.array([10.0, 9.5, 9.0]), 9.0) is None  # equal never fills
    assert find_fill(np.array([10.0, 8.9, 9.0]), 9.0) == 1
    assert find_fill(np.array([np.nan, np.nan]), 9.0) is None


def test_outcome_kind_stop_first_ordering():
    # flat tape: no TP, no stop -> time
    n = 240
    Ha = np.full(n, 100.0)
    La = np.full(n, 100.0)
    Ca = np.full(n, 100.0)
    Oa = np.full(n, 100.0)
    assert outcome_kind(Ha, La, Ca, Oa, 16, 100.0, 0.01) == "time"
    # deep low breaches backstop first -> backstop even if TP also touched later
    La2 = np.full(n, 100.0)
    La2[20] = 50.0
    Ha2 = np.full(n, 100.0)
    Ha2[30] = 500.0
    assert outcome_kind(Ha2, La2, Ca, Oa, 16, 110.0, 0.01) == "backstop"
