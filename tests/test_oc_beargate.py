"""oc_beargate tests: gate units + bear causality/truncation + hand-checked synthetic cases.

Run: .venv/Scripts/python.exe -m pytest tests/test_oc_beargate.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OC = HERE.parent / "research/tournament/oc_beargate"
sys.path.insert(0, str(OC))
from tilt_rule import ANCH5, anchor_of, assign_mult, bear_at, bear_series_from_btc, gate_mult  # noqa: E402


# ---- hand-checked synthetic cases ----
def test_assign_mult_dir_pos():
    assert assign_mult(3.0, 1, 0.5, 2.9, 1.25, 0.75) == 1.25
    assert assign_mult(0.4, 1, 0.5, 2.9, 1.25, 0.75) == 0.75
    assert assign_mult(1.0, 1, 0.5, 2.9, 1.25, 0.75) == 1.0
    assert assign_mult(float("nan"), 1, 0.5, 2.9, 1.25, 0.75) == 1.0


def test_gate_mult():
    assert gate_mult(1.25, False) == 1.25
    assert gate_mult(0.75, False) == 0.75
    assert gate_mult(1.25, True) == 1.0
    assert gate_mult(0.75, True) == 1.0
    assert gate_mult(1.0, True) == 1.0
    assert gate_mult(float("nan"), False) == 1.0


def test_bear_series_handchecked():
    # rising prices -> never bear; falling below long mean -> bear
    idx = pd.date_range("2020-01-01", periods=10, freq="4h", tz="UTC")
    up = pd.Series(np.arange(10, dtype=float) + 100.0, index=idx)
    b_up = bear_series_from_btc(up, window=4, min_periods=2)
    # strictly rising: price always above its trailing mean -> all False
    assert not b_up.any()
    dn = pd.Series(100.0 - np.arange(10, dtype=float), index=idx)
    b_dn = bear_series_from_btc(dn, window=4, min_periods=2)
    # strictly falling: after warm-up every bar is below its mean -> bear True
    assert bool(b_dn.iloc[-1])
    assert b_dn.dtype == bool


def test_bear_at_ffill_causal():
    idx = pd.date_range("2021-09-24", periods=6, freq="4h", tz="UTC")
    idx_ns = idx.values.astype("datetime64[ns]").astype(np.int64)
    val = np.array([False, False, True, True, False, False])
    # exactly on grid
    assert bear_at(idx_ns, val, idx[2].value) is True
    assert bear_at(idx_ns, val, idx[4].value) is False
    # between grid rows: ffill -> latest row <= T
    mid = idx[2] + pd.Timedelta(hours=1)
    assert bear_at(idx_ns, val, mid.value) is True
    mid2 = idx[4] + pd.Timedelta(hours=3, minutes=59)
    assert bear_at(idx_ns, val, mid2.value) is False
    # before history -> False (no look-ahead)
    assert bear_at(idx_ns, val, (idx[0] - pd.Timedelta(hours=1)).value) is False


def test_truncation_invariance():
    """Dropping later btc rows cannot change bear states at kept times
    (causality: bear[T] uses only data <= T)."""
    rng = np.random.default_rng(11)
    idx = pd.date_range("2020-01-01", periods=2000, freq="4h", tz="UTC")
    px = 100 + np.cumsum(rng.normal(0, 1, len(idx)))
    btc = pd.Series(px, index=idx)
    full = bear_series_from_btc(btc, window=1200, min_periods=600)
    trunc = bear_series_from_btc(btc.iloc[:1500], window=1200, min_periods=600)
    pd.testing.assert_series_equal(full.iloc[:1500], trunc)
    # ffill mapping is stable under truncation too
    idx_ns = idx.values.astype("datetime64[ns]").astype(np.int64)
    val = full.to_numpy(dtype=bool)
    t_ns = idx_ns[:1500]
    for t in (t_ns[700], t_ns[1400]):
        assert bear_at(idx_ns, val, t) == bear_at(idx_ns[:1500], val[:1500], t)


def test_anchor_of_boundaries():
    assert anchor_of("2021-09-24 00:00+00:00", 0) == 0
    assert anchor_of("2025-09-24 00:00+00:00", 0) == 4
    assert len(ANCH5) == 5


def test_frozen_inputs_exist():
    root = HERE.parent
    ch_fits = root / "research/tournament/oc_chronos/fits.json"
    vt_fits = root / "research/tournament/oc_voltilt/fits.json"
    assert ch_fits.exists() and vt_fits.exists()
