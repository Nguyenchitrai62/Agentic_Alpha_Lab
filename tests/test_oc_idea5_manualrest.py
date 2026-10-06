"""Tests for oc_idea5_manualrest (MANUAL 4h-rest brackets, IDEAS_20261007 s5).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_idea5_manualrest/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_idea5_manualrest"
EU_SRC = (ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py").read_text()


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_manualrest", HERE / "compute_manualrest.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


HAS_RESULTS = (HERE / "results.json").exists()
needs_results = pytest.mark.skipif(not HAS_RESULTS, reason="post-heavy")


# ---- pre-registered constants -------------------------------------------
def test_prereg_constants():
    m = _mod()
    assert m.WIN_START == 15 and m.SLEEVE_START == 16
    assert m.B0_END == 75 and m.H1_END == 240
    assert m.H2_SIZE_MULT == 8.75 and m.BASE_SIZE_MULT == 4.375
    assert m.RISK_BUDGET == 0.26
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "B0_60min", "H1_rest4h", "H2_rest4h_x2dip"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "B0_60min": "b0",
                             "H1_rest4h": "h1", "H2_rest4h_x2dip": "h1"}
    assert m.SIZE_MULT["H2_rest4h_x2dip"] == 8.75
    assert all(v is None for k, v in m.SIZE_MULT.items() if k != "H2_rest4h_x2dip")


def test_gate_costs_match_engine():
    assert "MAKER, TAKER = 0.0002, 0.00055" in EU_SRC
    assert "FUND_LONG = 0.0001" in EU_SRC


def test_helpers():
    m = _mod()
    assert m.entry_fill_end("b0", True) == 75
    assert m.entry_fill_end("b0", False) == 240
    assert m.entry_fill_end("h1", True) == 240
    assert m.entry_fill_end("ref", True) == 240
    assert m.entry_exp_bar("h1", 10) == 11
    assert m.entry_exp_bar("b0", 10) == 11
    assert m.entry_exp_bar("ref", 10) == 13
    assert m.entry_exp_bar("ref", 10, n_valid=2) == 12


# ---- patch mechanics ------------------------------------------------------
def test_patch_anchors_unique_in_engine():
    m = _mod()
    assert EU_SRC.count(m.OLD_EXP) == 1
    assert EU_SRC.count(m.OLD_HIT) == 1


def _eu():
    spec = importlib.util.spec_from_file_location(
        "engine_user_for_manualrest",
        ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_make_simulate_ref_is_identity():
    m = _mod()
    eu = _eu()
    assert m.make_simulate(eu, "ref") is eu.simulate


def test_make_simulate_h1_single_bar():
    m = _mod()
    eu = _eu()
    got = m.make_simulate(eu, "h1")._patched_src
    assert "i + 1, sd_a, i" in got
    assert m.OLD_EXP not in got  # entry orders: single-bar validity
    assert 'T["aexp"][a], T["aiss"][a] = i + P.get("n_valid", 2), i' in got  # scale orders untouched


def test_make_simulate_b0_sixty_minute_expiry():
    m = _mod()
    eu = _eu()
    got = m.make_simulate(eu, "b0")._patched_src
    assert "_cut = 75 if" in got
    assert "La[start:_cut]" in got and "Ha[start:_cut]" in got
    assert '"order_expire"' in got
    assert "T[\"side\"][a] = 0" in got


def test_no_leak_markers_in_script():
    src = (HERE / "compute_manualrest.py").read_text()
    assert "sleeve_fill_size" not in src  # agents untouched
    assert "min_off" not in src and "k_off" not in src  # entry price rule untouched
    assert "re-peg" not in src and "repeg" not in src  # no chasing
    for bad in ("tempfile", "gettempdir", "/tmp", "TMPDIR", "/proc",
                "artifacts/bot", "git stash", "git commit", "Kronos"):
        assert bad not in src, bad


def test_night_dip_skip_on_every_row():
    # M5_human schedule skips the night bar for dips too (sleeve_filter 0);
    # without it the rerun cannot reproduce oc_manualcap bit-exact.
    src = (HERE / "compute_manualrest.py").read_text()
    assert 'kw["sleeve_filter"]' in src
    assert "0.0 if hours[i] == night else 1.0" in src


def test_script_is_ascii():
    src = (HERE / "compute_manualrest.py").read_text(encoding="utf-8")
    bad = [i + 1 for i, l in enumerate(src.splitlines()) if any(ord(c) > 127 for c in l)]
    assert bad == [], bad


# ---- selection logic ------------------------------------------------------
def _t(Rdev4, Wdev4, DDdev4, losing=0):
    return {"Rdev4": Rdev4, "Wdev4": Wdev4, "DDdev4": DDdev4, "losing_dev4": losing}


def test_robust_pick_prefers_worst_year_then_mean():
    m = _mod()
    table = {"H1_rest4h": _t(4.0, 1.0, 15.0), "H2_rest4h_x2dip": _t(3.5, 1.5, 15.0)}
    assert m.robust_pick(table) == "H2_rest4h_x2dip"
    table = {"H1_rest4h": _t(4.0, 1.0, 15.0), "H2_rest4h_x2dip": _t(4.5, 1.0, 15.0)}
    assert m.robust_pick(table) == "H2_rest4h_x2dip"


def test_robust_pick_filters_dd_and_losing():
    m = _mod()
    table = {"H1_rest4h": _t(6.0, 2.0, 21.0), "H2_rest4h_x2dip": _t(3.0, 0.5, 15.0)}
    assert m.robust_pick(table) == "H2_rest4h_x2dip"
    table = {"H1_rest4h": _t(6.0, 2.0, 25.0), "H2_rest4h_x2dip": _t(3.0, -1.0, 25.0, losing=1)}
    assert m.robust_pick(table) == "none-eligible"


def test_robust_pick_prefers_mean_above_five():
    m = _mod()
    table = {"H1_rest4h": _t(5.5, 0.5, 15.0), "H2_rest4h_x2dip": _t(4.5, 2.0, 15.0)}
    assert m.robust_pick(table) == "H1_rest4h"


# ---- frozen baseline numbers ----------------------------------------------
def test_frozen_baseline_numbers():
    v421 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json")
                      .read_text())["rows"]["R2B1D17BFG2"]
    assert (v421["R"], v421["W"], v421["DD"], v421["full_path_dd"]) == (5.41, 2.588, 16.91, 16.82)
    cc = json.loads((HERE.parent / "oc_carrycompound/results.json").read_text())
    g = cc["rows"]["G2_f0.25"]
    assert (g["R"], g["W"], g["DD"], g["full_path_dd"]["full"]) == (5.634, 2.778, 16.75, 16.66)
    assert cc["carry_add_pp_per_month"] == 0.224
    m5 = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json")
                    .read_text())["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)


# ---- pre-reg report ---------------------------------------------------------
def test_report_preregistration_first():
    rep = (HERE / "REPORT.md").read_text().splitlines()
    head = "\n".join(rep[:40])
    assert "PRE-REGISTRATION" in head
    assert "H1_rest4h" in head and "H2_rest4h_x2dip" in head
    assert "B0_60min" in head


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "B0_60min", "H1_rest4h", "H2_rest4h_x2dip"}
    assert out["meta"]["costs"] == {"maker": 0.0002, "taker": 0.00055, "fund_long_8h": 0.0001}
    m5 = out["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)
    for row, v in out["rows"].items():
        assert len(v["years_R"]) == 5 and len(v["years_DD"]) == 5
        assert v["W"] == min(v["years_R"])
        assert v["maxDD"] == max(v["years_DD"])
        fac = 1.0
        for r in v["years_R"]:
            fac *= 1 + r / 100
        assert abs(fac ** (1 / 5) - 1 - v["R5"] / 100) < 5e-5
        assert v["book_win"] is not None and v["book_win"] >= 0
    assert out["meta"]["pick"] in ("H1_rest4h", "H2_rest4h_x2dip", "none-eligible")


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "H1_rest4h" in rep and "H2_rest4h_x2dip" in rep
    assert "POST-HOC" in rep
    vi = rep.strip().splitlines()[-3:]
    assert len(vi) == 3
