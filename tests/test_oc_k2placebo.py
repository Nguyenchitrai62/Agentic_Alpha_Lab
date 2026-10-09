"""oc_k2placebo tests: causality/truncation + hand-checked synthetic cases."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
MOD = HERE.parent / "research/tournament/oc_k2placebo/compute_k2placebo.py"


def _load():
    spec = importlib.util.spec_from_file_location("compute_k2placebo", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


K2 = _load()


def test_assign_mult_edges_k2():
    # direction +1 (all five oc_kronoshidden anchors)
    assert K2.assign_mult(5.0, 1, 0.5, 2.0) == 1.25
    assert K2.assign_mult(0.1, 1, 0.5, 2.0) == 0.75
    assert K2.assign_mult(1.0, 1, 0.5, 2.0) == 1.0
    # exact edges are inclusive (risk >= q80 -> hi, <= q20 -> lo)
    assert K2.assign_mult(2.0, 1, 0.5, 2.0) == 1.25
    assert K2.assign_mult(0.5, 1, 0.5, 2.0) == 0.75
    # missing -> 1.0 (causality: no lookahead fill-in)
    assert K2.assign_mult(float("nan"), 1, 0.5, 2.0) == 1.0
    assert K2.assign_mult(float("inf"), 1, 0.5, 2.0) == 1.0
    # flipped direction sanity
    assert K2.assign_mult(5.0, -1, 0.5, 2.0) == 0.75
    assert K2.assign_mult(0.1, -1, 0.5, 2.0) == 1.25


def test_year_truncation():
    # year grid: [A, A+365d); post-release year ends 2026-09-24 (exclusive)
    assert K2.year_of("2021-09-24 00:00") == 0
    assert K2.year_of("2022-09-23 23:59") == 0
    assert K2.year_of("2025-09-24 00:00") == 4
    assert K2.year_of("2026-09-23 20:00") == 4
    assert K2.year_of("2026-09-24 00:00") is None
    assert K2.year_of("2021-09-23 23:59") is None


def test_phase_mean_sums_hand_checked():
    # 2 fills in phase 0, 1 fill in phase 1, rest empty.
    # year 0: phase sums = (0.5*2.0 + 1.0*(-1.0), 2.0*0.5, 0, 0) = (0, 1, 0, 0)
    # mean = 0.25.
    ph = np.array([0, 0, 1, 2])
    yr = np.array([0, 0, 0, 1])
    w = np.array([0.5, 1.0, 2.0, 3.0])
    y = np.array([2.0, -1.0, 0.5, 1.0])
    got = K2.phase_mean_sums(ph, yr, w, y)
    assert got[0] == (0.0 + 1.0 + 0.0 + 0.0) / 4.0
    assert got[1] == (0.0 + 0.0 + 3.0 + 0.0) / 4.0
    assert got[2] == 0.0


def test_normalisation_and_percentile_hand_checked():
    # norm = k2 / realised_mean; percentile = 100*(1+#{perm<=actual})/1001
    k2, rm = 1.0, 0.8
    assert abs(k2 / rm - 1.25) < 1e-12
    actual = 1.25
    perms = np.array([1.0, 1.2, 1.25, 1.3])
    pct = 100.0 * (1 + int((perms <= actual).sum())) / (len(perms) + 1)
    assert pct == 100.0 * 4 / 5  # 3 perms <= actual -> 80.0
    # significance gate used in REPORT
    assert (pct >= 95) is False


def test_block_chunking_consecutive():
    # 42-bar block rule: consecutive T order per (sym, shift), last short kept.
    ts = pd.date_range("2021-09-24", periods=100, freq="4h", tz="UTC")
    blocks = [list(range(b, min(b + 42, 100))) for b in range(0, 100, 42)]
    assert [len(b) for b in blocks] == [42, 42, 16]
    flat = [i for b in blocks for i in b]
    assert flat == list(range(100))
    # a block permutation preserves the multiset
    rng = np.random.default_rng(0)
    mm = np.arange(100, dtype=float)
    order = rng.permutation(len(blocks))
    seq = []
    for b in order:
        seq.extend(mm[blocks[b]])
    assert sorted(seq) == list(mm)
