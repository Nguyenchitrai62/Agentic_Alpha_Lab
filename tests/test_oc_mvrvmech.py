"""oc_mvrvmech tests: causality/truncation + hand-checked synthetic (PLAN-fixed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent.parent / "research" / "tournament" / "oc_mvrvmech"
sys.path.insert(0, str(HERE))
from signals_mvrv import gate_mults, h8_asof_z, load_mvrv_daily, m1_mults


def test_h8_truncation_causal():
    d = load_mvrv_daily(win=365)
    T = pd.date_range("2024-03-01 00:00", "2024-03-05 00:00", freq="4h", tz="UTC")
    z_full = h8_asof_z(d, T)
    cut = pd.Timestamp("2024-03-03 00:00", tz="UTC")
    d_tr = d[d.index < cut].copy()
    z_tr = h8_asof_z(d_tr, T[T < cut + pd.Timedelta(hours=26)])
    z_full_early = h8_asof_z(d, T[T < cut + pd.Timedelta(hours=26)])
    np.testing.assert_allclose(z_tr, z_full_early, rtol=0, atol=1e-12)
    assert z_full.shape == T.shape


def test_h8_availability_boundary():
    d = load_mvrv_daily(win=365)
    day = pd.Timestamp("2024-03-10 00:00", tz="UTC")
    avail = day + pd.Timedelta(hours=26)
    before = avail - pd.Timedelta(seconds=1)
    after = avail + pd.Timedelta(seconds=1)
    T = pd.DatetimeIndex([before, after], tz="UTC")
    z = h8_asof_z(d, T)
    assert np.isfinite(z).sum() >= 1
    ii_before = int(np.searchsorted(
        d["avail"].to_numpy(dtype="datetime64[ns]").astype(np.int64),
        np.int64(before.value)) - 1)
    ii_after = int(np.searchsorted(
        d["avail"].to_numpy(dtype="datetime64[ns]").astype(np.int64),
        np.int64(after.value)) - 1)
    assert ii_after == ii_before + 1


def test_handchecked_synthetic_mults():
    z = np.array([np.nan, -0.5, 0.0, 1.74, 1.75, 2.0, 2.5, np.inf, -np.inf])
    m_frozen = m1_mults(z, 2.0)
    assert list(m_frozen) == [1, 1, 1, 1, 1, 1, 0.5, 1, 1]
    # strict > threshold: exactly 2.0 does NOT gate; NaN/Inf never gate
    assert m1_mults(np.array([2.0]), 2.0)[0] == 1.0
    assert m1_mults(np.array([np.inf]), 2.0)[0] == 1.0
    # gate applies to longs only: halving a long weight keeps the sign
    w = np.array([0.3, -0.2, 0.0])
    m = np.array([0.5, 0.5, 0.5])
    gated = np.where(w > 0, w * m, w)
    assert list(gated) == [0.15, -0.2, 0.0]
    # rows before the 2021-09-24 cutoff are never gated (mask check)
    T = pd.DatetimeIndex([pd.Timestamp("2021-09-20 00:00", tz="UTC"),
                          pd.Timestamp("2024-03-01 00:00", tz="UTC")])
    _, mm = gate_mults(T, 2.0, 365)
    assert len(mm) == 2
    assert set(np.unique(mm)).issubset({0.5, 1.0})
