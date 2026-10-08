"""Tests for oc_m_top2 (IDEAS9 #4 max-2 bracket priority, MANUAL).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_m_top2/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_m_top2"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_m_top2", HERE / "compute_m_top2.py")
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
    assert m.ROW_K == {"V1_TOP2": 2, "V2_TOP3": 3}
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "V1_TOP2", "V2_TOP3"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "V1_TOP2": "v1",
                             "V2_TOP3": "v2"}
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
def test_synthetic_topk_ranking():
    m = _mod()
    cols = list(m.MAJORS)
    # distinct |w|: top-2 = SOL, BTC (signs ignored)
    w = np.array([0.50, -0.10, 0.90, 0.05, -0.30])
    assert m.topk_kept(w, cols, 2) == frozenset({0, 2})
    assert m.topk_kept(w, cols, 3) == frozenset({0, 2, 4})
    # tie on |w| -> canonical MAJORS order (BTC first, then ETH ...)
    w2 = np.array([0.40, 0.40, 0.40, 0.40, 0.40])
    assert m.topk_kept(w2, cols, 2) == frozenset({0, 1})
    assert m.topk_kept(w2, cols, 3) == frozenset({0, 1, 2})
    # partial tie: BTC/ETH tie at 0.4 beat SOL 0.39
    w3 = np.array([0.40, -0.40, 0.39, 0.01, 0.0])
    assert m.topk_kept(w3, cols, 2) == frozenset({0, 1})
    # non-finite treated as 0.0 (never kept over a real weight)
    w4 = np.array([float("nan"), 0.2, 0.1, 0.0, 0.0])
    assert m.topk_kept(w4, cols, 2) == frozenset({1, 2})
    # permuted columns still break ties by canonical symbol order
    cols_p = ["XRPUSDT", "BNBUSDT", "SOLUSDT", "ETHUSDT", "BTCUSDT"]
    w5 = np.array([0.40, 0.40, 0.40, 0.40, 0.40])
    assert m.topk_kept(w5, cols_p, 2) == frozenset({4, 3})  # BTC, ETH


def test_synthetic_coin_filter_values():
    m = _mod()
    kept = frozenset({0, 2})
    assert m.coin_filter_value(0, kept, False) == 1.0
    assert m.coin_filter_value(2, kept, False) == 1.0
    assert m.coin_filter_value(1, kept, False) == 0.0
    assert m.coin_filter_value(4, kept, False) == 0.0
    assert m.coin_filter_value(0, kept, True) == 0.0
    assert m.coin_filter_value(1, kept, True) == 0.0


def test_synthetic_book_action_for_skipped():
    m = _mod()
    # kept + day -> None (use base policy)
    assert m.book_action_for_skipped(0, False, True) is None
    assert m.book_action_for_skipped(1, False, True) is None
    # night applies first even on kept coins
    assert m.book_action_for_skipped(0, True, True) == "wait"
    assert m.book_action_for_skipped(1, True, True) == "hold"
    # skipped coin: wait-if-flat / hold-if-in-position
    assert m.book_action_for_skipped(0, False, False) == "wait"
    assert m.book_action_for_skipped(2, False, False) == "hold"
    # night + skipped: same wait/hold
    assert m.book_action_for_skipped(0, True, False) == "wait"
    assert m.book_action_for_skipped(1, True, False) == "hold"


def test_synthetic_robust_pick_dev4_only():
    m = _mod()

    def _row(rdev4, wdev4, dddev4, losing):
        return {"Rdev4": rdev4, "Wdev4": wdev4, "DDdev4": dddev4,
                "losing_dev4": losing}

    # highest WORST wins; ties -> higher mean
    t = {"V1_TOP2": _row(3.0, 0.9, 15.0, 0),
         "V2_TOP3": _row(3.5, 0.8, 15.0, 0),
         "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t) == "V1_TOP2"
    # mean >= 5 preferred even with a lower WORST
    t2 = {"V1_TOP2": _row(4.9, 1.5, 15.0, 0),
          "V2_TOP3": _row(5.1, 0.2, 15.0, 0),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t2) == "V2_TOP3"
    # DD breach / losing year -> none-eligible
    t3 = {"V1_TOP2": _row(6.0, 1.5, 21.0, 0),
          "V2_TOP3": _row(6.0, 1.5, 19.0, 1),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t3) == "none-eligible"


def test_synthetic_gate_stats_skip_frac():
    m = _mod()
    cols = list(m.MAJORS)
    # 2 non-night bars, K=2 -> 3/5 slots skipped on each bar
    wmat = np.array([[0.5, 0.1, 0.9, 0.05, 0.3],
                     [0.1, 0.8, 0.2, 0.7, 0.0]])
    hours = np.array([4, 8])
    bar_year = np.array([0, 0])
    g = m._phase_gate_stats(wmat, cols, hours, 20, bar_year, 2)
    assert g["K"] == 2
    assert g["n_bars"][0] == 2
    assert g["skip_frac"][0] == pytest.approx(0.6)
    assert g["kept_abs_w"][0] > g["skip_abs_w"][0]
    # night bars excluded from the gate stats
    hours2 = np.array([20, 8])
    g2 = m._phase_gate_stats(wmat, cols, hours2, 20, bar_year, 2)
    assert g2["n_bars"][0] == 1
    assert g2["skip_frac"][0] == pytest.approx(0.6)


# ---- causality / truncation -----------------------------------------------
def test_causality_filter_is_bar_open_only():
    src = (HERE / "compute_m_top2.py").read_text()
    # rank key is the close-known book row only
    assert "topk_kept" in src
    assert "book_action_for_skipped" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    assert "hours[i] == night" in src  # night skip first
    # no fill-minute / 1m data enters any sizing decision
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute",
                "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_first_and_book_mult_untouched():
    src = (HERE / "compute_m_top2.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "book_action_for_skipped" in src
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_m_top2.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_k2manual():
    mine = (HERE / "compute_m_top2.py").read_text()
    ref = (ROOT / "research/tournament/oc_k2manual/compute_k2manual.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_m_top2.py").read_text(encoding="utf-8")
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
    assert "V1_TOP2" in txt and "V2_TOP3" in txt and "M5_human" in txt
    assert "BTC>ETH>SOL>BNB>XRP" in txt
    assert "POST-RELEASE" in txt
    assert "K = 2" in txt and "K = 3" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "V1_TOP2", "V2_TOP3"}
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
        assert v["book_win"] is not None and v["book_win"] >= 0
        assert v["rung_trades"] > 0
    assert out["meta"]["K"] == {"V1_TOP2": 2, "V2_TOP3": 3}
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "V1_TOP2",
                                                    "V2_TOP3"}
    assert out["meta"]["pick_dev4"] in ("V1_TOP2", "V2_TOP3",
                                        "none-eligible")


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "V1_TOP2" in rep and "V2_TOP3" in rep and "M5_human" in rep
    assert "POST-RELEASE" in rep
    assert len(rep.strip().splitlines()[-3:]) == 3
