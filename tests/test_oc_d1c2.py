"""oc_d1c2 tests: ensemble-rule units + causality/truncation + hand-checked synthetic cases.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_d1c2.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OC = HERE.parent / "research/tournament/oc_d1c2"
sys.path.insert(0, str(OC))
from tilt_rule import ANCH5, anchor_of, assign_mult, ensemble_agree, ensemble_avg  # noqa: E402


# ---- hand-checked synthetic cases ----
def test_assign_mult_dir_pos():
    assert assign_mult(0.9, 1, 0.2, 0.8) == 1.25
    assert assign_mult(0.1, 1, 0.2, 0.8) == 0.75
    assert assign_mult(0.5, 1, 0.2, 0.8) == 1.0
    assert assign_mult(float("nan"), 1, 0.2, 0.8) == 1.0


def test_assign_mult_dir_neg():
    assert assign_mult(0.1, -1, 0.2, 0.8) == 1.25
    assert assign_mult(0.9, -1, 0.2, 0.8) == 0.75
    assert assign_mult(0.5, -1, 0.2, 0.8) == 1.0
    assert assign_mult(float("inf"), -1, 0.2, 0.8) == 1.0


def test_ensemble_avg_handchecked():
    assert ensemble_avg(1.25, 1.25) == 1.25
    assert ensemble_avg(0.75, 0.75) == 0.75
    assert ensemble_avg(1.25, 0.75) == 1.0
    assert ensemble_avg(1.25, 1.0) == 1.125
    assert ensemble_avg(0.75, 1.0) == 0.875
    assert ensemble_avg(1.0, 1.0) == 1.0
    assert ensemble_avg(None, 0.75) == 0.875
    assert ensemble_avg(float("nan"), None) == 1.0


def test_ensemble_agree_handchecked():
    assert ensemble_agree(1.25, 1.25) == 1.25
    assert ensemble_agree(0.75, 0.75) == 0.75
    assert ensemble_agree(1.25, 0.75) == 1.0
    assert ensemble_agree(1.25, 1.0) == 1.0
    assert ensemble_agree(0.75, 1.0) == 1.0
    assert ensemble_agree(1.0, 1.0) == 1.0
    assert ensemble_agree(None, 1.25) == 1.0
    assert ensemble_agree(float("nan"), float("nan")) == 1.0


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00+00:00", 0) == 0
    assert anchor_of("2022-09-23 23:00+00:00", 0) == 0
    assert anchor_of("2025-09-24 00:00+00:00", 0) == 4
    assert anchor_of("2026-09-22 00:00+00:00", 0) == 4
    assert len(ANCH5) == 5


def test_truncation_invariance():
    """Dropping later multiplier rows cannot change earlier ensemble values
    (causality: the ensemble is a row-wise function of frozen leg mults)."""
    rng = np.random.default_rng(7)
    m1 = rng.choice([0.75, 1.0, 1.25], size=5000, p=[0.2, 0.6, 0.2])
    m2 = rng.choice([0.75, 1.0, 1.25], size=5000, p=[0.2, 0.6, 0.2])
    full_avg = np.array([ensemble_avg(a, b) for a, b in zip(m1, m2)])
    trunc_avg = np.array([ensemble_avg(a, b) for a, b in zip(m1[:3000], m2[:3000])])
    np.testing.assert_allclose(full_avg[:3000], trunc_avg, rtol=0, atol=0)
    full_ag = np.array([ensemble_agree(a, b) for a, b in zip(m1, m2)])
    trunc_ag = np.array([ensemble_agree(a, b) for a, b in zip(m1[:3000], m2[:3000])])
    np.testing.assert_allclose(full_ag[:3000], trunc_ag, rtol=0, atol=0)
    assert set(np.unique(full_avg)) <= {0.75, 0.875, 1.0, 1.125, 1.25}
    assert set(np.unique(full_ag)) <= {0.75, 1.0, 1.25}


def test_frozen_inputs_exist():
    root = HERE.parent
    assert (root / "research/tournament/oc_downshare/downshare_features_4shift.parquet").exists()
    assert (root / "research/tournament/oc_chronos/chronos_features_4shift.parquet").exists()
    assert (root / "research/tournament/oc_downshare/fits.json").exists()
    assert (root / "research/tournament/oc_chronos/fits.json").exists()
    assert (OC / "PLAN.md").exists()
    assert (OC / "tilt_rule.py").exists()
