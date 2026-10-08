"""oc_cboostbybit tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OC = ROOT / "research" / "tournament" / "oc_cboostbybit"
CB = ROOT / "research" / "tournament" / "oc_cascadeboost"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BOOST = _load("oc_cboostbybit_rule", OC / "boost_rule.py")
ENG = _load("oc_cboostbybit_eng", OC / "compute_cboostbybit_engine.py")


def test_boost_constants_frozen():
    assert BOOST.BOOST == 1.5 and BOOST.B7_DAYS == 7
    assert BOOST.THRESH == 4.0 and BOOST.WINDOW == 540
    assert BOOST.MIN_PERIODS == 120
    assert ENG.BOOST == 1.5


def test_friction_constants_match_robust_v421():
    # Exact defs from robust_v421.py / PLAN (one knob each, base win_start=5).
    assert ENG.fric_extra("base") == dict(win_start=5)
    assert ENG.fric_extra("S2") == dict(win_start=15, sleeve_start=16)
    assert ENG.fric_extra("S3") == dict(win_start=30, sleeve_start=31)
    assert ENG.fric_extra("S4") == dict(win_start=5, stop_slip=0.5)
    assert ENG.fric_extra("S5") == dict(win_start=5)
    src = (OC / "compute_cboostbybit_engine.py").read_text()
    assert "0.0004" in src and "0.0007 + 0.0005" in src
    assert "S5_START" in src and "bybit_linear_1m_20261004" in src
    assert ENG.S5_START == pd.Timestamp("2021-11-15", tz="UTC")
    # B7 uses the frozen cascadeboost boost mult (not a Chronos/Kronos tilt)
    assert "boost_mult_4shift" in src and "mult_B7" in src
    assert "ch_q10" not in src and "fits.json" not in src


def test_boosted_mask_boundaries_hand_checked():
    DAY = 86_400_000_000_000
    t0 = 1000 * DAY
    trig = np.array([t0], dtype=np.int64)
    h = 3_600_000_000_000
    grid = np.array([t0 - h, t0, t0 + h, t0 + 7 * DAY - 1, t0 + 7 * DAY,
                     t0 + 7 * DAY + h], dtype=np.int64)
    got = BOOST.boosted_mask(grid, trig, 7)
    assert list(got) == [False, False, True, True, True, False]
    assert BOOST.boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0


def test_truncation_causal_on_real_bars():
    """Dropping later bars cannot change triggers at kept times (real data)."""
    bars = pd.read_parquet(
        ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet",
        columns=["T", "close", "sym", "shift"])
    sub = bars[(bars["sym"] == "BTCUSDT") & (bars["shift"] == 0)].sort_values("T")
    closes = sub["close"].to_numpy(dtype=float)
    fire_full = BOOST.triggers_of(closes)
    cut = len(closes) - 500
    fire_tr = BOOST.triggers_of(closes[:cut])
    assert (fire_tr == fire_full[:cut]).all()
    assert BOOST.anchor_of("2021-09-24 00:00", 0) == 0
    assert BOOST.anchor_of("2025-09-24 00:00", 0) == 4


def test_handchecked_geo_and_gap():
    # Hand-checked: cascadeboost dev4 geo means + B7-REF gap used in REPORT.
    ref = [2.588, 3.282, 6.045, 10.677]
    b7 = [2.955, 3.264, 8.537, 12.486]
    g = lambda rs: 100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / 4) - 1)
    assert abs(g(ref) - 5.601) < 0.002
    assert abs(g(b7) - 6.738) < 0.002
    assert round(6.738 - 5.601, 3) == 1.137
