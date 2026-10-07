"""oc_voltilt tests: tilt-rule hand checks + feature causality/truncation.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_voltilt.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research/tournament/oc_voltilt"))

from tilt_rule import ANCH5, anchor_of, assign_mult  # noqa: E402
from build_vol_features import garch_filter, unpack  # noqa: E402


def _sig_rv6(open_, close):
    lo = np.log(np.clip(open_, 1e-12, None))
    sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
    lc = np.log(np.clip(close, 1e-12, None))
    r = np.empty_like(lc)
    r[0] = np.nan
    r[1:] = lc[1:] - lc[:-1]
    rv6 = pd.Series(r).rolling(6).std().shift(1).to_numpy()
    return sig, rv6, r


def test_assign_mult_handchecked():
    # direction +1: high risk favourable
    assert assign_mult(3.0, 1, 1.0, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(2.0, 1, 1.0, 2.0, 1.25, 0.75) == 1.25  # boundary inclusive
    assert assign_mult(0.5, 1, 1.0, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(1.0, 1, 1.0, 2.0, 1.25, 0.75) == 0.75  # boundary inclusive
    assert assign_mult(1.5, 1, 1.0, 2.0, 1.25, 0.75) == 1.0
    # direction -1: mirrored
    assert assign_mult(3.0, -1, 1.0, 2.0, 1.25, 0.75) == 0.75
    assert assign_mult(0.5, -1, 1.0, 2.0, 1.25, 0.75) == 1.25
    assert assign_mult(1.5, -1, 1.0, 2.0, 1.25, 0.75) == 1.0
    # missing risk -> 1 on both legs
    assert assign_mult(float("nan"), 1, 1.0, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(float("nan"), -1, 1.0, 2.0, 1.25, 0.75) == 1.0
    assert assign_mult(float("inf"), 1, 1.0, 2.0, 1.25, 0.75) == 1.0


def test_anchor_of_handchecked():
    assert anchor_of("2021-09-24 00:00", 0) == 0
    assert anchor_of("2022-09-24 00:00", 0) == 1
    assert anchor_of("2025-09-24 00:00", 0) == 4
    assert anchor_of("2026-09-23 00:00", 0) == 4
    assert anchor_of("2021-09-24 02:00", 3) == 0  # shift-3 year starts 03:00
    assert anchor_of("2021-09-24 04:00", 3) == 0
    assert len(ANCH5) == 5


def test_unpack_stationary_by_construction():
    rng = np.random.default_rng(7)
    for _ in range(50):
        om, al, be = unpack(rng.normal(0, 5, size=3))
        assert om > 0 and al >= 0 and be >= 0
        assert al + be <= 1.0  # strict stationarity, no penalty cliff


def test_garch_filter_handchecked_zero_returns():
    # r == 0 forever: v[e+1] = om + be*v[e] (alpha term vanishes) -> om/(1-be).
    om, al, be, v0 = 1e-6, 0.08, 0.88, 5e-6
    r = np.zeros(500)
    var = garch_filter(r, om, al, be, v0)
    uncond = om / (1 - al - be)
    assert var[0] == uncond  # var_T[0] = unconditional by construction
    assert abs(var[-1] - om / (1 - be)) < 1e-15
    assert bool((var > 0).all())


def test_sigma_rv6_truncation_causal():
    # Recomputing from bars truncated at a cut must be identical on the kept prefix.
    rng = np.random.default_rng(20261007)
    n = 500
    close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.01, size=n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.002, size=n))
    sig_f, rv6_f, _ = _sig_rv6(open_, close)
    cut = 400
    sig_t, rv6_t, _ = _sig_rv6(open_[:cut], close[:cut])
    m_sig = np.isfinite(sig_f[:cut]) | np.isfinite(sig_t)
    assert np.allclose(sig_f[:cut][m_sig], sig_t[m_sig], equal_nan=True)
    m_rv = np.isfinite(rv6_f[:cut]) | np.isfinite(rv6_t)
    assert np.allclose(rv6_f[:cut][m_rv], rv6_t[m_rv], equal_nan=True)
    # spot check causality: RV6[E] uses only r[E-6..E-1]
    lc = np.log(close)
    r = np.r_[np.nan, np.diff(lc)]
    e = 100
    assert np.isclose(rv6_f[e], np.std(r[e - 6:e], ddof=1), rtol=1e-12)
    # rolling-360 sigma needs 360 diffs: first finite at index 360
    assert int(np.argmax(np.isfinite(sig_f))) == 360


def test_garch_filter_truncation_frozen_params():
    # With FROZEN params, the filter on truncated bars matches the full-run prefix
    # (filter uses only r[E-1] and earlier).
    rng = np.random.default_rng(3)
    r = np.r_[np.nan, rng.normal(0, 0.01, size=999)]
    om, al, be, v0 = 2e-6, 0.06, 0.92, 1e-4
    full = garch_filter(r, om, al, be, v0)
    cut = 700
    trunc = garch_filter(r[:cut], om, al, be, v0)
    assert np.allclose(full[:cut], trunc)
    # hand check of the recursion at two steps
    uncond = om / (1 - al - be)
    assert full[0] == uncond
    assert full[1] == om + al * 0.0**2 + be * uncond  # r[0] is NaN -> treated as 0
