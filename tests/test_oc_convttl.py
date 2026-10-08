"""Tests for oc_convttl (IDEAS8 #7 conviction-dependent order TTL).

Pure-helper checks + causality/truncation tests. No 1m data reads.
Run: .venv/Scripts/python.exe -m pytest tests/test_oc_convttl.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research/tournament/oc_convttl"))

from convttl import mean_ttl_scale, thresholds_for_bars, ttl_for_weight, year_index


def test_ttl_strict_gt_ties_go_short():
    assert ttl_for_weight(0.10, 0.05) == 2
    assert ttl_for_weight(0.05, 0.05) == 1  # tie -> short
    assert ttl_for_weight(0.04, 0.05) == 1
    assert ttl_for_weight(0.0, 0.05) == 1
    assert ttl_for_weight(float("nan"), 0.05) == 1
    assert ttl_for_weight(0.10, float("nan")) == 1


def test_mean_ttl_scale_handcheck():
    # p=0.5 (median) -> mean TTL 1.5 bars -> scale 0.75; p=0.25 -> 0.625
    assert mean_ttl_scale(0.5) == 0.75
    assert mean_ttl_scale(0.25) == 0.625
    assert mean_ttl_scale(0.0) == 0.5
    assert mean_ttl_scale(1.0) == 1.0


def test_year_index_partition():
    # shift 0: year bounds [A, A+365d); 2023 year holds the leap-day orphans
    assert year_index(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert year_index(pd.Timestamp("2022-09-23 20:00", tz="UTC"), 0) == 0
    assert year_index(pd.Timestamp("2022-09-24", tz="UTC"), 0) == 1
    assert year_index(pd.Timestamp("2025-09-24", tz="UTC"), 0) == 4
    assert year_index(pd.Timestamp("2026-09-23 20:00", tz="UTC"), 0) == 4
    assert year_index(pd.Timestamp("2026-09-24", tz="UTC"), 0) is None
    assert year_index(pd.Timestamp("2021-09-23", tz="UTC"), 0) is None
    # shift 3 moves every boundary by 3h
    assert year_index(pd.Timestamp("2021-09-24 02:00", tz="UTC"), 3) is None
    assert year_index(pd.Timestamp("2021-09-24 03:00", tz="UTC"), 3) == 0


def test_thresholds_for_bars_causal_truncation():
    idx = pd.date_range("2021-09-24", periods=9000, freq="4h", tz="UTC")
    qs = [0.01, 0.02, 0.03, 0.04, 0.05]
    thr = thresholds_for_bars(idx, 0, qs)
    # first bar of each anchor year carries that year's threshold
    for k, a in enumerate(["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]):
        pos = idx.get_loc(pd.Timestamp(a, tz="UTC"))
        assert thr[pos] == qs[k]
    # perturbing later thresholds leaves earlier bars unchanged (no lookahead)
    qs2 = [0.01, 0.02, 0.03, 0.04, 0.99]
    thr2 = thresholds_for_bars(idx, 0, qs2)
    assert (thr2[:400] == thr[:400]).all()
    assert (thr2[400:] != thr[400:]).any()
    # truncation: first 100 bars identical with a cut index
    cut = thresholds_for_bars(idx[:100], 0, qs)
    assert (cut == thr[:100]).all()


def test_ttl_uses_signal_bar_only():
    # hand check: high conviction (|w|=0.09 > q=0.05) rests 2 bars, low rests 1.
    # The TTL decision may use only the signal bar's |w|; a later bar's |w|
    # must not change the already-issued expiry (no re-peg).
    q = 0.05
    assert ttl_for_weight(0.09, q) == 2
    assert ttl_for_weight(0.01, q) == 1
    # expiry arithmetic: issued at bar i, exp = i + ttl
    assert 10 + ttl_for_weight(0.09, q) == 12
    assert 10 + ttl_for_weight(0.01, q) == 11
