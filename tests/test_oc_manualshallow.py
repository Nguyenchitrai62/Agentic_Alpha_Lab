"""Lightweight checks for oc_manualshallow (no market data, no simulation)."""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "oc_manualshallow", ROOT / "research/diagnostics/oc_manualshallow/oc_manualshallow.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_rows_fixed():
    assert MOD.ROWS == ["M5_human", "M5_human_r3", "M5_human_r3x", "M5_human_r253"]
    assert MOD.ROWDEF["M5_human"] == {"rungs": (3.0, 4.0), "size_mult": 4.375, "rmap": {0: 1, 1: 3}}
    assert MOD.ROWDEF["M5_human_r3"] == {"rungs": (3.0,), "size_mult": 4.375, "rmap": {0: 1}}
    assert MOD.ROWDEF["M5_human_r3x"] == {"rungs": (3.0,), "size_mult": 6.5625, "rmap": {0: 1}}
    assert MOD.ROWDEF["M5_human_r3x"]["size_mult"] == 4.375 * 1.5
    assert MOD.ROWDEF["M5_human_r253"] == {"rungs": (2.5, 3.0), "size_mult": 4.375, "rmap": {0: 0, 1: 1}}
    assert list(MOD.ANCH5) == ["2021-09-24", "2022-09-24", "2023-09-24",
                               "2024-09-24", "2025-09-24"]


def test_rmaps_hit_deployed_rung_depths():
    # R2 ladder table rungs 0..4 = 2.5/3.0/3.5/4.0/5.0 sigma; every row's map
    # must land on the matching depth (3.0 -> 1, 4.0 -> 3, 2.5 -> 0).
    depth = {0: 2.5, 1: 3.0, 2: 3.5, 3: 4.0, 4: 5.0}
    for row, spec in MOD.ROWDEF.items():
        assert len(spec["rungs"]) == len(spec["rmap"])
        for i, k in enumerate(spec["rungs"]):
            assert depth[spec["rmap"][i]] == k, row


def test_geom5_math():
    r = MOD.geom5_from_reset_R([1.0] * 5)
    assert r == round(100 * ((1.01 ** 60) ** (1 / 60) - 1), 3) or abs(r - 1.0) < 1e-9
    nets = [(1 + 2.0 / 100) ** 12 - 1] * 5
    exp = 100 * (float(np.prod([1 + n for n in nets])) ** (1 / 60) - 1)
    assert abs(MOD.geom5_from_reset_R([2.0] * 5) - exp) < 1e-9
    assert abs(MOD._monthly(0.12) - (100 * (1.12 ** (1 / 12) - 1))) < 1e-12


def test_pooled_win():
    assert MOD.pooled_win([(6, 10), (3, 10)]) == 0.45
    assert MOD.pooled_win([(0, 0)]) is None
    assert MOD.pooled_win([]) is None
