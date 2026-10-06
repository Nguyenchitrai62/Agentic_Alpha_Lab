"""oc_agentskip tests: SKIP gate logic (synthetic) + causality contract."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_agentskip"
sys.path.insert(0, str(OC))

from build_skip import SKIP_TH, apply_skip


def test_both_below_threshold_skips():
    pa = np.array([-0.003, -0.01, -0.0021])
    pb = np.array([-0.004, -0.05, -0.003])
    base = np.array([1.0, 1.5, 0.5])
    out = apply_skip(pa, pb, base)
    assert (out == 0.0).all()


def test_one_above_threshold_keeps_base():
    pa = np.array([-0.01, 0.005, -0.001])
    pb = np.array([0.001, -0.01, -0.01])
    base = np.array([1.0, 1.5, 0.5])
    out = apply_skip(pa, pb, base)
    assert (out == base).all()


def test_boundary_is_strict():
    # exactly at -0.002 does NOT skip (rule is <, not <=)
    assert SKIP_TH == -0.002
    out = apply_skip(np.array([-0.002]), np.array([-0.002]), np.array([1.0]))
    assert out[0] == 1.0


def test_nan_prediction_never_skips():
    out = apply_skip(np.array([np.nan]), np.array([-0.01]), np.array([1.0]))
    assert out[0] == 1.0
    out = apply_skip(np.array([-0.01]), np.array([np.nan]), np.array([0.5]))
    assert out[0] == 0.5


def test_skip_only_touches_size_values():
    pa = np.array([-0.005, 0.01])
    pb = np.array([-0.006, 0.02])
    base = np.array([1.5, 0.5])
    out = apply_skip(pa, pb, base)
    assert out[0] == 0.0 and out[1] == 0.5
    assert set(np.unique(out)).issubset({0.0, 0.5, 1.0, 1.5})
