"""Tests for oc_m_settleskip (IDEAS9 #6 settlement-clock skip, MANUAL).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_m_settleskip/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_m_settleskip"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_m_settleskip", HERE / "compute_m_settleskip.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


HAS_RESULTS = (HERE / "results.json").exists()
needs_results = pytest.mark.skipif(not HAS_RESULTS, reason="post-heavy")


# ---- pre-registered constants -------------------------------------------
def test_prereg_constants():
    m = _mod()
    assert m.WIN_START == 15 and m.SLEEVE_START == 16
    assert m.MAJORS == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "V1_SETTLE", "V2_SETTLE_NEXT"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "V1_SETTLE": "v1",
                             "V2_SETTLE_NEXT": "v2"}
    assert m.ANCH5 == ("2021-09-24", "2022-09-24", "2023-09-24",
                       "2024-09-24", "2025-09-24")


def test_helpers_geo_and_anchor():
    m = _mod()
    assert m.geo_mean_monthly([5.0, 5.0, 5.0, 5.0]) == pytest.approx(5.0)
    assert m.anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2022-09-23", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2023-01-01", tz="UTC"), 0) == 1
    assert m.anchor_of(pd.Timestamp("2026-01-01", tz="UTC"), 0) == 4
    assert m.anchor_of(pd.Timestamp("2026-09-23", tz="UTC"), 0) == 4


# ---- hand-checked synthetic cases ---------------------------------------
def test_synthetic_settle_flags_shift0():
    m = _mod()
    # standard 4h decision grid, shift 0: holding bars [T, T+4h), T = idx+4h.
    # settle in (T, T+4h] <=> holding bar ENDS at 00/08/16 UTC.
    idx = pd.DatetimeIndex([
        "2021-09-24 20:00+00:00",  # holding [00,04): ends 04 -> False
        "2021-09-25 00:00+00:00",  # holding [04,08): ends 08 -> True
        "2021-09-25 04:00+00:00",  # holding [08,12): ends 12 -> False
        "2021-09-25 08:00+00:00",  # holding [12,16): ends 16 -> True
        "2021-09-25 12:00+00:00",  # holding [16,20): ends 20 -> False
        "2021-09-25 16:00+00:00",  # holding [20,00): ends 00 -> True
    ])
    got = m.settle_flags_for_idx(idx)
    assert list(bool(x) for x in got) == [False, True, False, True,
                                          False, True]


def test_synthetic_settle_flags_shift1():
    m = _mod()
    # shift-1 decision grid: idx = std + 1h; holding T = idx+4h.
    idx = pd.DatetimeIndex([
        "2021-09-24 21:00+00:00",  # holding [01,05): (01,05] -> False
        "2021-09-25 01:00+00:00",  # holding [05,09): (05,09] has 08 -> True
        "2021-09-25 05:00+00:00",  # holding [09,13): False
        "2021-09-25 09:00+00:00",  # holding [13,17): has 16 -> True
    ])
    got = m.settle_flags_for_idx(idx)
    assert list(bool(x) for x in got) == [False, True, False, True]


def test_synthetic_skip_v1_v2():
    m = _mod()
    settle = np.array([False, True, False, True, False, True])
    v1 = m.skip_for_row(settle, "v1")
    assert list(bool(x) for x in v1) == [False, True, False, True,
                                         False, True]
    v2 = m.skip_for_row(settle, "v2")
    # alternating settle pattern -> V2 skips everything after the first
    # bar (i=0 has no previous bar; pre-registered degeneracy)
    assert list(bool(x) for x in v2) == [False, True, True, True,
                                         True, True]
    assert list(bool(x) for x in m.skip_for_row(settle, "ref")) == [False] * 6
    # isolated settle: V2 skips the settle bar and exactly the next bar
    s2 = np.array([False, False, True, False, False])
    assert list(bool(x) for x in m.skip_for_row(s2, "v2")) == \
        [False, False, True, True, False]


def test_synthetic_coin_filter_and_book_action():
    m = _mod()
    assert m.coin_filter_value(0, False, False) == 1.0
    assert m.coin_filter_value(3, True, False) == 0.0
    assert m.coin_filter_value(0, False, True) == 0.0
    assert m.coin_filter_value(0, True, True) == 0.0
    assert m.book_action_for_skipped(0, False, False) is None
    assert m.book_action_for_skipped(1, False, False) is None
    assert m.book_action_for_skipped(0, True, False) == "wait"
    assert m.book_action_for_skipped(1, True, False) == "hold"
    assert m.book_action_for_skipped(0, False, True) == "wait"
    assert m.book_action_for_skipped(2, False, True) == "hold"
    assert m.book_action_for_skipped(0, True, True) == "wait"
    assert m.book_action_for_skipped(1, True, True) == "hold"


def test_synthetic_robust_pick_dev4_only():
    m = _mod()

    def _row(rdev4, wdev4, dddev4, losing):
        return {"Rdev4": rdev4, "Wdev4": wdev4, "DDdev4": dddev4,
                "losing_dev4": losing}

    t = {"V1_SETTLE": _row(3.0, 0.9, 15.0, 0),
         "V2_SETTLE_NEXT": _row(3.5, 0.8, 15.0, 0),
         "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t) == "V1_SETTLE"
    t2 = {"V1_SETTLE": _row(4.9, 1.5, 15.0, 0),
          "V2_SETTLE_NEXT": _row(5.1, 0.2, 15.0, 0),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t2) == "V2_SETTLE_NEXT"
    t3 = {"V1_SETTLE": _row(6.0, 1.5, 21.0, 0),
          "V2_SETTLE_NEXT": _row(6.0, 1.5, 19.0, 1),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t3) == "none-eligible"


def test_synthetic_gate_stats_skip_frac():
    m = _mod()
    settle = np.array([False, True, False, True])
    skip = m.skip_for_row(settle, "v1")
    hours = np.array([0, 4, 8, 12])
    bar_year = np.array([0, 0, 0, 0])
    g = m._phase_gate_stats(settle, skip, hours, 20, bar_year)
    assert g["skip_frac"][0] == pytest.approx(0.5)
    assert g["settle_frac"][0] == pytest.approx(0.5)
    assert g["n_bars"][0] == 4
    # night bars excluded
    hours2 = np.array([20, 4, 8, 12])
    settle2 = np.array([True, True, False, True])
    skip2 = m.skip_for_row(settle2, "v1")
    g2 = m._phase_gate_stats(settle2, skip2, hours2, 20, bar_year)
    assert g2["n_bars"][0] == 3


# ---- causality / truncation -----------------------------------------------
def test_causality_gate_is_clock_only():
    src = (HERE / "compute_m_settleskip.py").read_text()
    assert "settle_flags_for_idx" in src
    assert "settle[i-1]" in src or "settle[:-1]" in src
    assert "book_action_for_skipped" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    assert "hours[i] == night" in src  # night skip first
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute",
                "minute f", "o1_prev", "sig_prev", "premium_1m",
                "funding.parquet", "q90", "p90"):
        assert bad not in src, bad


def test_night_skip_first_and_book_mult_untouched():
    src = (HERE / "compute_m_settleskip.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "book_action_for_skipped" in src
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_m_settleskip.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_k2manual():
    mine = (HERE / "compute_m_settleskip.py").read_text()
    ref = (ROOT / "research/tournament/oc_k2manual/compute_k2manual.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_m_settleskip.py").read_text(encoding="utf-8")
    bad = [i + 1 for i, l in enumerate(src.splitlines())
           if any(ord(c) > 127 for c in l)]
    assert bad == [], bad


# ---- frozen baseline numbers ----------------------------------------------
def test_frozen_baseline_numbers():
    m5 = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json")
                    .read_text())["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)


def test_plan_preregistration_first():
    txt = (HERE / "PLAN.md").read_text()
    assert "V1_SETTLE" in txt and "V2_SETTLE_NEXT" in txt
    assert "M5_human" in txt
    assert "POST-RELEASE" in txt
    assert "settle[i]" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "V1_SETTLE", "V2_SETTLE_NEXT"}
    assert out["meta"]["costs"] == {"maker": 0.0002, "taker": 0.00055,
                                    "fund_long_8h": 0.0001}
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
        if row == "V2_SETTLE_NEXT":
            # pre-registered degeneracy: V2 skips ~100% of bars, no trades
            assert v["book_trades"] == 0 and v["book_win"] is None
            assert v["rung_trades"] == 0 and v["rung_win"] is None
            assert v["win_all"] is None
        else:
            assert v["book_win"] is not None and v["book_win"] >= 0
            assert v["rung_trades"] > 0
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "V1_SETTLE",
                                                     "V2_SETTLE_NEXT"}
    assert out["meta"]["pick_dev4"] in ("V1_SETTLE", "V2_SETTLE_NEXT",
                                        "none-eligible")


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "V1_SETTLE" in rep and "V2_SETTLE_NEXT" in rep
    assert "M5_human" in rep
    assert "POST-RELEASE" in rep
    assert len(rep.strip().splitlines()[-3:]) == 3
