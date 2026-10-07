"""Lightweight checks for oc_manualnight (no market data, no simulation)."""
import importlib.util
import inspect
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "oc_manualnight", ROOT / "research/diagnostics/oc_manualnight/oc_manualnight.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_rows_fixed():
    assert MOD.ROWS == ["M5_human", "M5_human_night", "M5_human_K13G15",
                        "M5_human_night_K13G15"]
    assert MOD.PIPES == {"M5": "v367"}
    assert MOD.GCAP == {"M5_human": None, "M5_human_night": None,
                       "M5_human_K13G15": 1.5, "M5_human_night_K13G15": 1.5}
    assert MOD.NIGHT_STALE == {"M5_human": False, "M5_human_night": True,
                               "M5_human_K13G15": False,
                               "M5_human_night_K13G15": True}
    assert MOD.K13 == {"M5_human": False, "M5_human_night": False,
                       "M5_human_K13G15": True,
                       "M5_human_night_K13G15": True}
    assert list(MOD.ANCH5) == ["2021-09-24", "2022-09-24", "2023-09-24",
                               "2024-09-24", "2025-09-24"]
    # K13 = x1.3 on the M5 base values (4.375 / 0.26)
    assert abs(MOD.SIZE_MULT_BASE * MOD.K_MULT - 5.6875) < 1e-12
    assert abs(MOD.RISK_BASE * MOD.K_MULT - 0.338) < 1e-12


def test_night_level_is_prev_bar():
    assert abs(MOD.night_level(100.0, 0.01, 3.0) - 97.0) < 1e-12
    assert abs(MOD.night_level(200.0, 0.02, 4.0) - 184.0) < 1e-12


def test_compute_scale():
    assert MOD.compute_scale(1.0, 0.0, 0.33) == 1.0
    assert MOD.compute_scale(1.5, 2.0, 0.33) == 1.0
    sc = MOD.compute_scale(1.0, 11.0, 0.33)
    assert sc == min(1.0, 1.0 / (0.33 * 11.0))
    assert abs(0.33 * 11.0 * sc - 1.0) < 1e-9


def test_geo_mean_monthly():
    assert MOD.geo_mean_monthly([0, 0, 0, 0, 0]) == 0.0
    assert abs(MOD.geo_mean_monthly([6.0] * 5) - 6.0) < 1e-9


def _synth_filter(G, skip_night=True):
    hours = np.array([0, 20, 1, 20])
    lsz = {(("T%d" % i), a, r): 1.5 for i in range(4) for a in range(5)
           for r in (1, 3)}
    keys = ["T%d" % i for i in range(4)]
    size_of = lambda T, a, r: lsz[(T, a, r)]
    return MOD.build_filter(hours, 20, lambda i: keys[i], size_of, 5, (1, 3),
                            G, 0.33, skip_night=skip_night), hours


def test_filter_skips_night_by_default():
    filt, _ = _synth_filter(None, skip_night=True)
    assert filt(1, 0, 0) == 0.0
    assert filt(0, 0, 0) == 1.0


def test_filter_night_row_places_on_night():
    filt, _ = _synth_filter(None, skip_night=False)
    assert filt(1, 0, 0) == 1.0  # night bar NOT skipped for dips
    assert filt(0, 0, 0) == 1.0


def test_filter_gcap_scales_both_clocks():
    filt, _ = _synth_filter(1.5, skip_night=False)
    s0 = filt(0, 0, 0)
    s1 = filt(1, 0, 0)  # night bar gets the same static G-scale
    assert abs(s0 - s1) < 1e-12
    assert abs(s0 - 1.5 / (0.33 * 15.0)) < 1e-12


def test_filter_uses_bar_open_info_only():
    src = inspect.getsource(MOD.build_filter)
    for token in ("La[", "Ha[", "Ca[", "O[i,", "cube"):
        assert token not in src
    assert "fill_minute" not in src


def test_patched_simulate_uses_stale_on_night():
    src = inspect.getsource(MOD.make_night_simulate)
    assert "night_stale" in src
    assert "o1_prev" in src
    assert "sig_prev" in src
    # the old/new sleeve blocks are present and distinct
    assert "sig_sl[i][a]" in MOD._OLD_SLEEVE
    assert "_sg" in MOD._NEW_SLEEVE
    assert MOD._OLD_SLEEVE != MOD._NEW_SLEEVE
    assert "_OLD_SLEEVE" in src and "_NEW_SLEEVE" in src


def test_runs_for_reset_shape():
    allres = {s: {"M5_human": {"run": {"t": [], "eq": [], "eq_min": []},
                               "wins": [], "cross": []}} for s in range(4)}
    runs = MOD.runs_for_reset(allres, "M5_human")
    assert set(runs) == {0, 1, 2, 3}
    for s in range(4):
        assert set(runs[s]) == {"M5_human"}
        assert runs[s]["M5_human"] is allres[s]["M5_human"]["run"]
