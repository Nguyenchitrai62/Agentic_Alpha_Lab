"""oc_downshare tests: rule units + downside-share causality/truncation + hand-checked synthetic cases.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_downshare.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OC = HERE.parent / "research/tournament/oc_downshare"
sys.path.insert(0, str(OC))
from tilt_rule import (ANCH5, WIN_D1, WIN_DAILY, WIN_WEEKLY, anchor_of,  # noqa: E402
                       assign_mult, blend_d2, share_of)


# ---- hand-checked synthetic cases ----
def test_assign_mult_dir_pos():
    assert assign_mult(0.9, 1, 0.2, 0.8, 1.25, 0.75) == 1.25
    assert assign_mult(0.1, 1, 0.2, 0.8, 1.25, 0.75) == 0.75
    assert assign_mult(0.5, 1, 0.2, 0.8, 1.25, 0.75) == 1.0
    assert assign_mult(float("nan"), 1, 0.2, 0.8, 1.25, 0.75) == 1.0


def test_assign_mult_dir_neg():
    # direction -1: low share favourable -> hi; high share unfavourable -> lo
    assert assign_mult(0.1, -1, 0.2, 0.8, 1.25, 0.75) == 1.25
    assert assign_mult(0.9, -1, 0.2, 0.8, 1.25, 0.75) == 0.75
    assert assign_mult(0.5, -1, 0.2, 0.8, 1.25, 0.75) == 1.0


def test_share_handchecked():
    # all downside -> 1.0
    assert abs(share_of([-0.01, -0.02, -0.03]) - 1.0) < 1e-12
    # all upside -> 0.0
    assert abs(share_of([0.01, 0.02, 0.03]) - 0.0) < 1e-12
    # symmetric +- pair -> 0.5
    assert abs(share_of([0.02, -0.02]) - 0.5) < 1e-12
    # mixed: down^2=0.0004+0.0001=0.0005, total=0.0004+0.0001+0.0009=0.0014
    assert abs(share_of([-0.02, -0.01, 0.03]) - (0.0005 / 0.0014)) < 1e-12
    # flat (zero vol) -> NaN
    assert not np.isfinite(share_of([0.0, 0.0, 0.0]))
    # empty / non-finite -> NaN
    assert not np.isfinite(share_of([]))
    assert not np.isfinite(share_of([0.01, float("nan"), -0.01]))
    assert not np.isfinite(share_of([0.01, float("inf")]))


def test_blend_handchecked():
    assert abs(blend_d2(0.5, 0.5) - 0.5) < 1e-12
    assert abs(blend_d2(1.0, 0.0) - 0.6) < 1e-12
    assert abs(blend_d2(0.0, 1.0) - 0.4) < 1e-12
    assert not np.isfinite(blend_d2(float("nan"), 0.5))
    assert not np.isfinite(blend_d2(0.5, float("nan")))
    assert WIN_D1 == 36 and WIN_DAILY == 6 and WIN_WEEKLY == 30


def test_truncation_invariance():
    """Dropping later returns cannot change shares at kept times (causality)."""
    rng = np.random.default_rng(11)
    r = rng.normal(0, 0.01, 2000)
    r[0] = np.nan
    full_d1 = np.array([share_of(r[max(1, i - WIN_D1):i]) if i >= WIN_D1 + 1 else np.nan
                        for i in range(2000)])
    trunc_d1 = np.array([share_of(r[max(1, i - WIN_D1):i]) if i >= WIN_D1 + 1 else np.nan
                         for i in range(1500)])
    np.testing.assert_allclose(full_d1[:1500], trunc_d1, rtol=0, atol=0, equal_nan=True)
    # D2 blend uses at most 30 past returns: same prefix property
    full_d2 = np.array([blend_d2(share_of(r[i - WIN_DAILY:i]), share_of(r[i - WIN_WEEKLY:i]))
                        if i >= WIN_WEEKLY + 1 else np.nan for i in range(2000)])
    trunc_d2 = np.array([blend_d2(share_of(r[i - WIN_DAILY:i]), share_of(r[i - WIN_WEEKLY:i]))
                         if i >= WIN_WEEKLY + 1 else np.nan for i in range(1500)])
    np.testing.assert_allclose(full_d2[:1500], trunc_d2, rtol=0, atol=0, equal_nan=True)


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00+00:00", 0) == 0
    assert anchor_of("2025-09-24 00:00+00:00", 0) == 4
    assert len(ANCH5) == 5


def test_frozen_inputs_exist():
    root = HERE.parent
    assert (root / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet").exists()
    assert (root / "research/tournament/oc_k2placebo/tmp/ledger.npz").exists()
    assert (OC / "downshare_features_4shift.parquet").exists()
    assert (OC / "fits.json").exists()
