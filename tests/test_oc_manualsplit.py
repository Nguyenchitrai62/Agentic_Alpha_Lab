"""Tests for oc_manualsplit (MANUAL split-TP brackets, IDEAS_20261007c B8).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_manualsplit/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_manualsplit"
EU_SRC = (ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py").read_text()


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_manualsplit", HERE / "compute_manualsplit.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


HAS_RESULTS = (HERE / "results.json").exists()
needs_results = pytest.mark.skipif(not HAS_RESULTS, reason="post-heavy")


# ---- pre-registered constants -------------------------------------------
def test_prereg_constants():
    m = _mod()
    assert m.WIN_START == 15 and m.SLEEVE_START == 16
    assert m.RATIOS_H1 == (0.75, 1.5) and m.RATIOS_H2 == (0.5, 1.0)
    assert m.RATIOS == {"H1_split75_150": (0.75, 1.5),
                        "H2_split50_100": (0.5, 1.0)}
    assert m.BASE_SIZE_MULT == 4.375 and m.RISK_BUDGET == 0.26
    assert m.MIN_NOTIONAL_HALF == 5.0 and m.ACCOUNT == 10000.0
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "H1_split75_150", "H2_split50_100"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "H1_split75_150": "h1",
                             "H2_split50_100": "h2"}


def test_gate_costs_match_engine():
    assert "MAKER, TAKER = 0.0002, 0.00055" in EU_SRC
    assert "FUND_LONG = 0.0001" in EU_SRC


def test_helpers_ratios_and_merge():
    m = _mod()
    assert m.split_tp_mult(1.0, 0.75) == 0.75
    assert m.split_tp_mult(1.0, 1.5) == 1.5
    assert m.split_tp_mult(1.5, 0.75) == 1.125
    assert m.split_tp_mult(1.5, 1.5) == 2.25
    assert m.split_tp_mult(1.0, 0.5) == 0.5
    # half notional: rn=0.16 weight at equity 1.0 -> half = 800 USDT
    assert m.half_notional(0.16, 1.0) == pytest.approx(800.0)
    assert m.half_notional(0.16, 1.0, 10000.0) == pytest.approx(800.0)
    assert m.should_merge(0.16, 1.0) is False
    # tiny rung merges: rn=0.0008 -> half = 4 USDT < 5
    assert m.half_notional(0.0008, 1.0) == pytest.approx(4.0)
    assert m.should_merge(0.0008, 1.0) is True
    assert m.should_merge(0.001, 1.0) is False  # half = 5.0, not below
    assert m.geo_mean_monthly([5.0, 5.0, 5.0, 5.0]) == pytest.approx(5.0)


# ---- hand-checked synthetic exit cases ------------------------------------
def test_synthetic_fast_half_banks_while_runner_waits():
    m = _mod()
    lv, sg = 100.0, 0.01
    # minute0 rallies to 100.8: TP at +0.75sg (100.75) hit, +1.5sg (101.5) not
    kind_a, ret_a = m.rung_exit_touch([99.5], [100.8], [100.0], lv, sg, 0.75)
    kind_b, ret_b = m.rung_exit_touch([99.5], [100.8], [100.0], lv, sg, 1.5)
    assert kind_a == "rung_tp" and ret_a is not None and ret_a > 0
    assert abs(ret_a - (100.75 / 100.0 - 1 - 2 * 0.0002)) < 1e-12
    assert kind_b == "rung_timeout" and ret_b is None
    # next minute flushes to 91.5: runner stops
    kind_c, ret_c = m.rung_exit_touch([91.5], [92.5], [100.5], lv, sg, 1.5)
    assert kind_c == "rung_sl" and ret_c < 0


def test_synthetic_stop_first_on_same_minute_tie():
    m = _mod()
    lv, sg = 100.0, 0.01  # tp 100.75, sl 92.0
    kind, ret = m.rung_exit_touch([91.0], [102.0], [100.0], lv, sg, 0.75)
    assert kind == "rung_sl" and ret < 0


def test_synthetic_h2_faster_bank():
    m = _mod()
    lv, sg = 100.0, 0.01  # H2 fast half TP at +0.5sg = 100.5
    kind, ret = m.rung_exit_touch([99.8], [100.6], [100.0], lv, sg, 0.5)
    assert kind == "rung_tp" and ret > 0
    # same bar does NOT bank the deployed 1.0sg TP at 101.0
    kind2, _ = m.rung_exit_touch([99.8], [100.6], [100.0], lv, sg, 1.0)
    assert kind2 == "rung_timeout"


# ---- causality / truncation -----------------------------------------------
def test_causality_tp_uses_bar_open_only():
    m = _mod()
    src = (HERE / "compute_manualsplit.py").read_text()
    # TP multiplier comes from the bar-open R2 table lookup, never minute data
    assert "sleeve_tp(i, a, r, f)" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed via harness
    # no fill-minute data feeds the TP decision
    assert "night_stale" not in src
    assert "o1_prev" not in src and "sig_prev" not in src


def test_patch_anchors_unique_in_engine():
    m = _mod()
    assert EU_SRC.count(m.OLD_HA_LINE) == 1
    assert EU_SRC.count(m.OLD_TP_LINE) == 1
    assert EU_SRC.count(m.OLD_SL_LINE) == 1
    assert EU_SRC.count(m.BODY_START) == 1
    assert EU_SRC.count(m.BODY_END) == 1


def _eu():
    spec = importlib.util.spec_from_file_location(
        "engine_user_for_manualsplit",
        ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_make_simulate_ref_is_identity():
    m = _mod()
    eu = _eu()
    assert m.make_simulate(eu, "ref") is eu.simulate


def test_make_simulate_h1_ratios_and_merge():
    m = _mod()
    eu = _eu()
    fn = m.make_simulate(eu, "h1")
    assert fn._ratios == (0.75, 1.5)
    got = fn._patched_src
    assert "_ratios = (0.75, 1.5)" in got
    assert "split_merged" in got and "split_halves" in got
    assert "_half_not" in got and "prev_eq * ACCOUNT" in got
    fn2 = m.make_simulate(eu, "h2")
    assert fn2._ratios == (0.5, 1.0)
    assert "_ratios = (0.5, 1.0)" in fn2._patched_src


def test_no_leak_markers_in_script():
    src = (HERE / "compute_manualsplit.py").read_text()
    assert "min_off" not in src and "k_off" not in src  # entry price untouched
    assert "re-peg" not in src and "repeg" not in src  # no chasing
    for bad in ("tempfile", "gettempdir", "/tmp", "TMPDIR", "/proc",
                "artifacts/bot", "git stash", "git commit", "Kronos"):
        assert bad not in src, bad


def test_night_dip_skip_on_every_row():
    src = (HERE / "compute_manualsplit.py").read_text()
    assert 'kw["sleeve_filter"]' in src
    assert "0.0 if hours[i] == night else 1.0" in src


def test_script_is_ascii():
    src = (HERE / "compute_manualsplit.py").read_text(encoding="utf-8")
    bad = [i + 1 for i, l in enumerate(src.splitlines()) if any(ord(c) > 127 for c in l)]
    assert bad == [], bad


# ---- selection logic ------------------------------------------------------
def _t(Rdev4, Wdev4, DDdev4, losing=0):
    return {"Rdev4": Rdev4, "Wdev4": Wdev4, "DDdev4": DDdev4, "losing_dev4": losing}


def test_robust_pick_prefers_worst_year_then_mean():
    m = _mod()
    table = {"H1_split75_150": _t(4.0, 1.0, 15.0), "H2_split50_100": _t(3.5, 1.5, 15.0)}
    assert m.robust_pick(table) == "H2_split50_100"
    table = {"H1_split75_150": _t(4.0, 1.0, 15.0), "H2_split50_100": _t(4.5, 1.0, 15.0)}
    assert m.robust_pick(table) == "H2_split50_100"


def test_robust_pick_filters_dd_and_losing():
    m = _mod()
    table = {"H1_split75_150": _t(6.0, 2.0, 21.0), "H2_split50_100": _t(3.0, 0.5, 15.0)}
    assert m.robust_pick(table) == "H2_split50_100"
    table = {"H1_split75_150": _t(6.0, 2.0, 25.0), "H2_split50_100": _t(3.0, -1.0, 25.0, losing=1)}
    assert m.robust_pick(table) == "none-eligible"


def test_robust_pick_prefers_mean_above_five():
    m = _mod()
    table = {"H1_split75_150": _t(5.5, 0.5, 15.0), "H2_split50_100": _t(4.5, 2.0, 15.0)}
    assert m.robust_pick(table) == "H1_split75_150"


# ---- frozen baseline numbers ----------------------------------------------
def test_frozen_baseline_numbers():
    m5 = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json")
                    .read_text())["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)


def test_plan_preregistration_first():
    txt = (HERE / "PLAN.md").read_text()
    assert "H1_split75_150" in txt and "H2_split50_100" in txt
    assert "0.75" in txt and "1.5" in txt and "0.5" in txt
    assert "5.0 USDT" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "H1_split75_150", "H2_split50_100"}
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
        assert v["rung_trades"] > 0 and v["merged"] >= 0 and v["halves"] >= 0
    assert out["meta"]["pick"] in ("H1_split75_150", "H2_split50_100", "none-eligible")


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "H1_split75_150" in rep and "H2_split50_100" in rep
    assert "POST-HOC" in rep
    vi = rep.strip().splitlines()[-3:]
    assert len(vi) == 3
