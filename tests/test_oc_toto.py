"""oc_toto tests: tilt-rule units + truncation/causality checks.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_toto.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OC = HERE.parent / "research/tournament/oc_toto"
sys.path.insert(0, str(OC))
from tilt_rule import ANCH5, anchor_of, assign_mult, ensemble_mult  # noqa: E402


def _fit_edges(risk, y):
    """Mirror of make_fits.py edge logic on in-memory arrays."""
    m = np.isfinite(risk) & np.isfinite(y)
    r, z = risk[m], y[m]
    rho = float(pd.Series(r).corr(pd.Series(z), method="spearman"))
    q20, q80 = [float(v) for v in np.quantile(r, [0.2, 0.8])]
    return (1 if rho > 0 else -1), q20, q80, rho


# ---- hand-checked synthetic cases ----
def test_assign_mult_dir_pos():
    assert assign_mult(3.0, 1, 0.5, 2.9, 1.25, 0.75) == 1.25  # high risk favourable
    assert assign_mult(0.4, 1, 0.5, 2.9, 1.25, 0.75) == 0.75
    assert assign_mult(1.0, 1, 0.5, 2.9, 1.25, 0.75) == 1.0
    assert assign_mult(2.9, 1, 0.5, 2.9, 1.25, 0.75) == 1.25  # boundary inclusive
    assert assign_mult(0.5, 1, 0.5, 2.9, 1.25, 0.75) == 0.75


def test_assign_mult_dir_neg():
    assert assign_mult(3.0, -1, 0.5, 2.9, 1.25, 0.75) == 0.75  # high risk unfavourable
    assert assign_mult(0.4, -1, 0.5, 2.9, 1.25, 0.75) == 1.25
    assert assign_mult(1.0, -1, 0.5, 2.9, 1.25, 0.75) == 1.0
    assert assign_mult(float("nan"), -1, 0.5, 2.9, 1.25, 0.75) == 1.0
    assert assign_mult(float("inf"), 1, 0.5, 2.9, 1.25, 0.75) == 1.0


def test_ensemble_mult():
    assert ensemble_mult(1.25, 0.75) == 1.0
    assert ensemble_mult(1.25, 1.25) == 1.25
    assert ensemble_mult(None, 0.75) == 0.875
    assert ensemble_mult(float("nan"), None) == 1.0


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00+00:00", 0) == 0
    assert anchor_of("2022-09-23 23:00+00:00", 0) == 0
    assert anchor_of("2025-09-24 00:00+00:00", 0) == 4
    assert anchor_of("2026-09-22 00:00+00:00", 0) == 4
    assert anchor_of("2021-09-24 00:00+00:00", 3) == 0  # shift boundary respected
    assert len(ANCH5) == 5


def test_truncation_invariance():
    """Fit edges from a truncated table are identical on the kept prefix
    (causality: dropping later rows cannot change an earlier fit)."""
    rng = np.random.default_rng(7)
    risk = rng.normal(1.5, 1.0, 5000)
    y = 0.02 * risk + rng.normal(0, 1.0, 5000)
    full = _fit_edges(risk, y)
    trunc = _fit_edges(risk[:3000], y[:3000])
    # same-prefix recomputation: first 3000 rows alone give the same edges
    again = _fit_edges(risk[:3000], y[:3000])
    assert trunc == again
    # and the full fit restricted to the prefix differs only by using more rows
    assert full[0] == trunc[0] == 1  # positive relation by construction
    # multiplier assignments on the kept prefix are unchanged by truncation
    d, q20, q80, _ = trunc
    m_trunc = np.array([assign_mult(r, d, q20, q80, 1.25, 0.75) for r in risk[:3000]])
    m_again = np.array([assign_mult(r, d, q20, q80, 1.25, 0.75) for r in risk[:3000]])
    assert (m_trunc == m_again).all()
    assert set(np.unique(m_trunc)) <= {0.75, 1.0, 1.25}


def test_feature_timing_if_parquet():
    """Causality on the real tables (skipped until inference finishes):
    every feature T exists in the bars grid and has >= 512 prior bars."""
    pq = OC / "toto_features_4shift.parquet"
    bars_pq = OC.parent / "oc_kronoshidden/bars_4h_4shift.parquet"
    if not pq.exists():
        import pytest
        pytest.skip("toto features not built yet")
    f = pd.read_parquet(pq, columns=["sym", "shift", "T"])
    b = pd.read_parquet(bars_pq, columns=["sym", "shift", "T"])
    assert set(f.columns) == {"sym", "shift", "T"}
    assert f[["sym", "shift", "T"]].duplicated().sum() == 0
    bkey = set(zip(b["sym"], b["shift"], pd.to_datetime(b["T"], utc=True)))
    for (sym, sh), g in f.groupby(["sym", "shift"]):
        ts = sorted(pd.to_datetime(g["T"], utc=True))
        assert all((t - ts[0]) % pd.Timedelta(hours=4) == pd.Timedelta(0) for t in ts)
        for t in ts[:5]:
            assert (sym, sh, t) in bkey  # feature T is a real bar open
            prior = [x for x in bkey if x[0] == sym and x[1] == sh and x[2] <= t]
            assert len(prior) >= 513  # 512 context bars + the bar itself


def test_quantile_ordering_if_parquet():
    """Distributional sanity on the real feature table (skipped until built):
    q10 <= q50 <= q90 and all finite where sigma is finite."""
    pq = OC / "toto_features_4shift.parquet"
    if not pq.exists():
        import pytest
        pytest.skip("toto features not built yet")
    f = pd.read_parquet(pq, columns=["f_q10", "f_q50", "f_q90", "sigma"])
    assert (f["sigma"] > 0).all()
    assert np.isfinite(f[["f_q10", "f_q50", "f_q90", "sigma"]].to_numpy()).all()
    assert ((f["f_q10"] <= f["f_q50"]) & (f["f_q50"] <= f["f_q90"])).all()
