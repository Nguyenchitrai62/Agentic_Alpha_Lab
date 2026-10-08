"""Tests for oc_m_conflict (IDEAS9 #3 book-vs-dip conflict skip, MANUAL).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_m_conflict/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_m_conflict"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_m_conflict", HERE / "compute_m_conflict.py")
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
    assert m.EMBARGO_DAYS == 7 and m.THR_MIN_N == 100
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "V1", "V2"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "V1": "v1", "V2": "v2"}
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
def test_synthetic_skip_v1_sign_only():
    m = _mod()
    assert m.skip_v1(-0.5) is True
    assert m.skip_v1(-0.0001) is True  # strictly negative: any short skips
    assert m.skip_v1(0.0) is False  # flat book never skips the long dip
    assert m.skip_v1(0.3) is False
    assert m.skip_v1(float("nan")) is False


def test_synthetic_skip_v2_strong_short_only():
    m = _mod()
    assert m.skip_v2(-0.5, 0.3) is True  # strong short skips
    assert m.skip_v2(-0.2, 0.3) is False  # weak short kept
    assert m.skip_v2(-0.3, 0.3) is False  # strictly above the median
    assert m.skip_v2(0.5, 0.3) is False  # long book never skips
    assert m.skip_v2(0.0, 0.3) is False
    assert m.skip_v2(-0.5, float("inf")) is False  # thin history: no skip
    assert m.skip_v2(float("nan"), 0.3) is False


def test_synthetic_conflict_filter_values():
    m = _mod()
    assert m.conflict_filter_value(False, False) == 1.0
    assert m.conflict_filter_value(False, True) == 0.0
    assert m.conflict_filter_value(True, False) == 0.0  # night first
    assert m.conflict_filter_value(True, True) == 0.0


def test_synthetic_median_thr_frozen():
    m = _mod()
    assert m.median_thr([0.1, 0.2, 0.3] * 50) == pytest.approx(0.2)
    assert m.median_thr([0.5] * 200) == pytest.approx(0.5)
    assert m.median_thr([0.1, 0.2]) == float("inf")  # < 100: never skip
    assert m.median_thr([]) == float("inf")


def test_synthetic_build_skip_masks_bar_open_only():
    m = _mod()
    idx = pd.DatetimeIndex([pd.Timestamp("2022-01-01", tz="UTC") + i * pd.Timedelta(hours=4)
                            for i in range(3)])
    cols = ["BTCUSDT", "ETHUSDT"]
    books_arr = np.array([[-0.5, 0.2], [-0.1, -0.4], [0.0, 0.3]])
    thr = {(c, a): 0.3 for c in cols for a in m.ANCH5}
    v1, v2 = m.build_skip_masks(books_arr, idx, cols, 0, thr)
    assert v1.tolist() == [[True, False], [True, True], [False, False]]
    assert v2.tolist() == [[True, False], [False, True], [False, False]]


def test_synthetic_robust_pick_dev4_only():
    m = _mod()

    def _row(rdev4, wdev4, dddev4, losing):
        return {"Rdev4": rdev4, "Wdev4": wdev4, "DDdev4": dddev4,
                "losing_dev4": losing}

    t = {"V1": _row(3.0, 0.9, 15.0, 0),
         "V2": _row(3.5, 0.8, 15.0, 0),
         "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t) == "V1"
    t2 = {"V1": _row(4.9, 1.5, 15.0, 0),
          "V2": _row(5.1, 0.2, 15.0, 0),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t2) == "V2"
    t3 = {"V1": _row(6.0, 1.5, 21.0, 0),
          "V2": _row(6.0, 1.5, 19.0, 1),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t3) == "none-eligible"


# ---- causality / truncation -----------------------------------------------
def test_causality_filter_is_bar_open_only():
    src = (HERE / "compute_m_conflict.py").read_text()
    assert "build_skip_masks" in src
    assert "books_arr" in src  # close-known book targets only
    assert "compute_thr" in src and "EMBARGO_DAYS" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute",
                "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_first_and_book_mult_untouched():
    src = (HERE / "compute_m_conflict.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "hours[i] == night" in src
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_m_conflict.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_k2manual():
    mine = (HERE / "compute_m_conflict.py").read_text()
    ref = (ROOT / "research/tournament/oc_k2manual/compute_k2manual.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_m_conflict.py").read_text(encoding="utf-8")
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
    assert "V1" in txt and "V2" in txt and "M5_human" in txt
    assert "median" in txt and "7d" in txt
    assert "POST-RELEASE" in txt
    assert "w[i,a] < 0" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "V1", "V2"}
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
        assert len(v["skip_rate"]) == 5
    assert out["rows"]["V1"]["skip_rate"][0] >= out["rows"]["V2"]["skip_rate"][0]
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "V1", "V2"}
    assert out["meta"]["pick_dev4"] in ("V1", "V2", "none-eligible")


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "V1" in rep and "V2" in rep and "M5_human" in rep
    assert "POST-RELEASE" in rep
    assert len(rep.strip().splitlines()[-3:]) == 3
