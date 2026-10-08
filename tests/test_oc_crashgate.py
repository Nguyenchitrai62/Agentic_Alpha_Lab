"""oc_crashgate tests: gate units + crash-depth causality/truncation + hand-checked synthetic cases.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_crashgate.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OC = HERE.parent / "research/tournament/oc_crashgate"
sys.path.insert(0, str(OC))
from tilt_rule import ANCH5, V1_X, V2_X, anchor_of, assign_mult, depth_of_window, gate_mult  # noqa: E402


# ---- hand-checked synthetic cases ----
def test_assign_mult_dir_pos():
    assert assign_mult(3.0, 1, 0.5, 2.9, 1.25, 0.75) == 1.25
    assert assign_mult(0.4, 1, 0.5, 2.9, 1.25, 0.75) == 0.75
    assert assign_mult(1.0, 1, 0.5, 2.9, 1.25, 0.75) == 1.0
    assert assign_mult(float("nan"), 1, 0.5, 2.9, 1.25, 0.75) == 1.0


def test_depth_handchecked():
    # flat / rising -> 0
    assert depth_of_window([100.0, 100.0, 100.0]) == 0.0
    assert depth_of_window([100.0, 101.0, 102.0]) == 0.0
    # single 10 % drop -> 0.10
    assert depth_of_window([100.0, 90.0]) == 0.10
    # peak 100, trough 80 after a higher peak -> 0.20 (intra-window max, not current)
    assert abs(depth_of_window([100.0, 80.0, 90.0]) - 0.20) < 1e-12
    # crash then new high then smaller dip: max is still the 20 % crash
    assert abs(depth_of_window([100.0, 80.0, 120.0, 108.0]) - 0.20) < 1e-12
    # < 2 finite closes -> NaN
    assert not np.isfinite(depth_of_window([100.0]))
    assert not np.isfinite(depth_of_window([]))


def test_gate_mult_thresholds():
    assert V1_X == 0.15 and V2_X == 0.10
    # below X -> tilt kept; at/above X -> base sizes
    assert gate_mult(1.25, 0.149, 0.15) == 1.25
    assert gate_mult(1.25, 0.15, 0.15) == 1.0
    assert gate_mult(0.75, 0.20, 0.15) == 1.0
    assert gate_mult(1.25, 0.099, 0.10) == 1.25
    assert gate_mult(1.25, 0.10, 0.10) == 1.0
    assert gate_mult(1.0, 0.50, 0.15) == 1.0
    assert gate_mult(float("nan"), 0.01, 0.15) == 1.0
    # NaN depth (insufficient history) -> allow (base kept)
    assert gate_mult(1.25, float("nan"), 0.15) == 1.25


def test_truncation_invariance():
    """Dropping later closes cannot change depth at kept times (causality)."""
    rng = np.random.default_rng(7)
    px = 100 + np.cumsum(rng.normal(0, 1, 2000))
    full = np.array([depth_of_window(px[max(0, i - 180):i]) for i in range(2000)])
    trunc = np.array([depth_of_window(px[max(0, i - 180):i]) for i in range(1500)])
    np.testing.assert_allclose(full[:1500], trunc, rtol=0, atol=0, equal_nan=True)
    # same via a shifted (later) window: depth at i uses only closes < i
    for i in (500, 1200, 1499):
        assert full[i] == depth_of_window(px[max(0, i - 180):i])


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00+00:00", 0) == 0
    assert anchor_of("2025-09-24 00:00+00:00", 0) == 4
    assert len(ANCH5) == 5


def test_frozen_inputs_exist():
    root = HERE.parent
    assert (root / "research/tournament/oc_chronos/fits.json").exists()
    assert (root / "research/tournament/oc_chronos/chronos_features_4shift.parquet").exists()
    assert (root / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet").exists()
    assert (root / "research/tournament/oc_k2placebo/tmp/ledger.npz").exists()
