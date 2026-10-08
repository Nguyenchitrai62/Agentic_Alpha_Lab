"""oc_b7frontier tests: causality/truncation + hand-checked synthetic cases."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OC = ROOT / "research" / "tournament" / "oc_b7frontier"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BOOST = _load("oc_b7frontier_rule", OC / "boost_rule.py")
ENG = _load("oc_b7frontier_eng", OC / "compute_b7frontier_engine.py")


def test_boost_constants_frozen():
    assert BOOST.BOOST == 1.5 and BOOST.B7_DAYS == 7
    assert BOOST.THRESH == 4.0 and BOOST.WINDOW == 540
    assert BOOST.MIN_PERIODS == 120
    assert ENG.BOOST == 1.5
    assert ENG.KD == 1.3 and ENG.F_FLUSH == 2.5


def test_engine_configs_match_plan():
    # D13B7 = kd 1.3, NO gross cap (pipe default None, as v424); S5 harness fixed.
    assert set(ENG.JOBS) == {"D13B7_base", "D13B7_S5"}
    assert ENG.S5_START == pd.Timestamp("2021-11-15", tz="UTC")
    src = (OC / "compute_b7frontier_engine.py").read_text()
    assert "boost_mult_4shift" in src and "mult_B7" in src
    assert "bybit_linear_1m_20261004" in src and "win_start=5" in src
    assert "ch_q10" not in src and "fits.json" not in src
    # no gross cap for the D13 base: engine must NOT set sleeve_gross_cap = 2.0
    assert 'sleeve_gross_cap"] = 2.0' not in src
    assert 'del kw["sleeve_gross_cap"]' in src


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


def test_handchecked_geo_and_d13b7_dev():
    # Hand-checked: geo monthly mean arithmetic used in REPORT for the NEW D13B7 rows.
    g = lambda rs: 100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / 4) - 1)
    assert abs(g([2.807, 3.622, 5.526, 11.368]) - 5.779) < 0.002  # D13B7_base dev4
    assert abs(g([2.092, 2.903, 5.135, 11.037]) - 5.235) < 0.002  # D13B7_S5 dev4
    assert abs(g([2.955, 3.264, 8.537, 12.486]) - 6.738) < 0.002  # G2B7_base dev4 gate
