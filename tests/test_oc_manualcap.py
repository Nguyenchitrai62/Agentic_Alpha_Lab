"""Lightweight checks for oc_manualcap (no market data, no simulation)."""
import importlib.util
import inspect
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "oc_manualcap", ROOT / "research/diagnostics/oc_manualcap/oc_manualcap.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_rows_fixed():
    assert MOD.ROWS == ["M5_human", "M5_human_G15", "M5_human_G10",
                        "M3_human_G10"]
    assert MOD.PIPES == {"M5": "v367", "M3": "v342"}
    assert MOD.GCAP == {"M5_human": None, "M5_human_G15": 1.5,
                        "M5_human_G10": 1.0, "M3_human_G10": 1.0}
    assert list(MOD.ANCH5) == ["2021-09-24", "2022-09-24", "2023-09-24",
                               "2024-09-24", "2025-09-24"]


def test_compute_scale():
    # nothing planned -> no scaling
    assert MOD.compute_scale(1.0, 0.0, 0.33) == 1.0
    # plan below G -> no scaling
    assert MOD.compute_scale(1.5, 2.0, 0.33) == 1.0
    # plan above G -> proportional cut, placed total == G
    sc = MOD.compute_scale(1.0, 11.0, 0.33)
    assert sc == min(1.0, 1.0 / (0.33 * 11.0))
    assert abs(0.33 * 11.0 * sc - 1.0) < 1e-9
    # tighter G scales harder
    assert MOD.compute_scale(1.0, 11.0, 0.33) < MOD.compute_scale(1.5, 11.0, 0.33)


def test_geo_mean_monthly():
    assert MOD.geo_mean_monthly([0, 0, 0, 0, 0]) == 0.0
    assert abs(MOD.geo_mean_monthly([6.0] * 5) - 6.0) < 1e-9
    m = MOD.geo_mean_monthly([1.0, 2.0, 3.0, 4.0, 5.0])
    assert abs(m - 100 * ((1.01 * 1.02 * 1.03 * 1.04 * 1.05) ** 0.2 - 1)) < 1e-9


def _synth_filter(G):
    hours = np.array([0, 20, 1, 20])
    lsz = {(("T%d" % i), a, r): 1.5 for i in range(4) for a in range(5)
           for r in (1, 3)}
    keys = ["T%d" % i for i in range(4)]
    size_of = lambda T, a, r: lsz[(T, a, r)]
    return MOD.build_filter(hours, 20, lambda i: keys[i], size_of, 5, (1, 3),
                            G, 0.33), hours


def test_filter_night_and_reference():
    filt, _ = _synth_filter(None)
    assert filt(1, 0, 0) == 0.0  # night bar -> no dip limit
    assert filt(0, 0, 0) == 1.0  # reference -> unscaled


def test_filter_scales_proportionally_and_caches():
    filt, _ = _synth_filter(1.0)
    assert filt(1, 2, 1) == 0.0
    s0 = filt(0, 0, 0)
    # S = 5 coins x 2 rungs x 1.5 = 15 -> scale = 1/(0.33*15)
    assert abs(s0 - 1.0 / (0.33 * 15.0)) < 1e-12
    # same scale for every rung of the bar (proportional)
    assert filt(0, 4, 1) == s0
    assert filt(2, 3, 0) == s0  # same table values -> same scale
    assert len(filt.cache) == 2  # bars 0 and 2 cached (bar 1 = night)


def test_filter_uses_bar_open_info_only():
    src = inspect.getsource(MOD.build_filter)
    assert "fill_minute" not in src
    assert "minute" not in src.lower() or "fill_minute" not in src
    for token in ("La[", "Ha[", "Ca[", "O[i,", "cube"):
        assert token not in src
    sig = inspect.signature(MOD.build_filter)
    assert list(sig.parameters) == ["hours", "night", "bar_key", "size_of",
                                    "na", "mapped", "G", "base_max"]


def test_runs_for_reset_shape():
    # reset_metric.year_reset / v388.mix index runs as runs[shift][strat]
    allres = {s: {"M5_human": {"run": {"t": [], "eq": [], "eq_min": []},
                               "wins": [], "cross": []}} for s in range(4)}
    runs = MOD.runs_for_reset(allres, "M5_human")
    assert set(runs) == {0, 1, 2, 3}
    for s in range(4):
        assert set(runs[s]) == {"M5_human"}
        assert runs[s]["M5_human"] is allres[s]["M5_human"]["run"]
