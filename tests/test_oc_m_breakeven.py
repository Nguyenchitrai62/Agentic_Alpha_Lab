"""Tests for oc_m_breakeven (IDEAS9 #2 one-move break-even, MANUAL).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_m_breakeven/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_m_breakeven"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_m_breakeven", HERE / "compute_m_breakeven.py")
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
    assert m.BE_K == {"V1_BE075": 0.75, "V2_BE050": 0.50}
    assert m.BE_OFF == 0.0
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "V1_BE075", "V2_BE050"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "V1_BE075": "v1",
                             "V2_BE050": "v2"}
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
def test_synthetic_be_prices():
    m = _mod()
    # long: trigger above entry, stop exactly at entry
    assert m.be_trigger_price(100.0, 1, 0.75, 0.01) == pytest.approx(100.75)
    assert m.be_trigger_price(100.0, 1, 0.50, 0.01) == pytest.approx(100.50)
    assert m.be_stop_price(100.0, 1, 0.0) == pytest.approx(100.0)
    # short mirrors
    assert m.be_trigger_price(100.0, -1, 0.75, 0.01) == pytest.approx(99.25)
    assert m.be_stop_price(100.0, -1, 0.0) == pytest.approx(100.0)


def test_synthetic_dip_be_arm_strict_before():
    m = _mod()
    assert m.dip_be_arm(5, None, None) is True
    assert m.dip_be_arm(5, 10, 12) is True
    assert m.dip_be_arm(None, 10, 12) is False
    # same-minute ties go to the base exit (never arms)
    assert m.dip_be_arm(5, 5, None) is False
    assert m.dip_be_arm(5, None, 5) is False
    assert m.dip_be_arm(5, 3, None) is False
    assert m.dip_be_arm(5, None, 4) is False


def test_synthetic_dip_be_exit_arms_then_stops():
    m = _mod()
    lv, sg, m0 = 100.0, 0.01, 1.0
    # tp=101, sl=92, V1 trig=100.75, be_stop=100
    # minute0 triggers (high 100.8), minute1 BE-stops (low 99.9)
    lows = np.array([100.2, 99.9, 100.1])
    highs = np.array([100.8, 100.2, 101.5])
    opens = np.array([100.3, 100.0, 100.2])
    kind, ret, armed, tb = m.dip_be_exit(lows, highs, opens, lv, sg, m0, 0.75)
    assert armed is True and tb == 0
    assert kind == "rung_sl"
    assert ret == pytest.approx(100.0 / 100.0 - 1 - 0.0002 - 0.00055)


def test_synthetic_dip_be_tie_goes_to_base():
    m = _mod()
    lv, sg, m0 = 100.0, 0.01, 1.0
    # trigger and base stop in the same minute: base wins, never arms
    # sl=92; craft sl touch at minute0 together with trigger
    # use sl_mult default 8 -> sl 92; low 91 touches both
    lows = np.array([91.0, 99.9])
    highs = np.array([100.8, 100.2])
    opens = np.array([100.3, 100.0])
    kind, ret, armed, tb = m.dip_be_exit(lows, highs, opens, lv, sg, m0, 0.75)
    assert tb == 0
    assert armed is False
    assert kind == "rung_sl"
    assert ret == pytest.approx(92.0 / 100.0 - 1 - 0.0002 - 0.00055)


def test_synthetic_dip_be_no_trigger_equals_base():
    m = _mod()
    lv, sg, m0 = 100.0, 0.01, 1.0
    # never reaches 100.75, never stops (sl 92), never TPs (101): timeout
    lows = np.array([99.0, 99.0])
    highs = np.array([100.5, 100.6])
    opens = np.array([100.0, 100.0])
    kind, ret, armed, tb = m.dip_be_exit(lows, highs, opens, lv, sg, m0, 0.75)
    assert armed is False and tb is None
    assert kind == "rung_timeout" and ret is None


def test_synthetic_robust_pick_dev4_only():
    m = _mod()

    def _row(rdev4, wdev4, dddev4, losing):
        return {"Rdev4": rdev4, "Wdev4": wdev4, "DDdev4": dddev4,
                "losing_dev4": losing}

    t = {"V1_BE075": _row(3.0, 0.9, 15.0, 0),
         "V2_BE050": _row(3.5, 0.8, 15.0, 0),
         "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t) == "V1_BE075"
    t2 = {"V1_BE075": _row(4.9, 1.5, 15.0, 0),
          "V2_BE050": _row(5.1, 0.2, 15.0, 0),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t2) == "V2_BE050"
    t3 = {"V1_BE075": _row(6.0, 1.5, 21.0, 0),
          "V2_BE050": _row(6.0, 1.5, 19.0, 1),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t3) == "none-eligible"


# ---- causality / truncation -----------------------------------------------
def test_causality_be_is_fill_and_mark_only():
    src = (HERE / "compute_m_breakeven.py").read_text()
    # book BE comes from the engine-native bar-open sigma + fill entry
    assert 'trade["be_k"]' in src
    assert 'trade["be_off"]' in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    # dip BE trigger uses only 1m marks up to the amend minute
    assert "Ha[f + 1:end_m] >= _be_trig" in src
    assert "_tba < _ksa" in src and "_tba < _kta" in src
    # no future / fill-minute markers enter any sizing decision
    for bad in ("C[i, f", "fill_minute", "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_first_and_m5_identity():
    src = (HERE / "compute_m_breakeven.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "hours[i] == night" in src
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "be_k" in src and "BE_K" in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_m_breakeven.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_k2manual():
    mine = (HERE / "compute_m_breakeven.py").read_text()
    ref = (ROOT / "research/tournament/oc_k2manual/compute_k2manual.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_m_breakeven.py").read_text(encoding="utf-8")
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
    assert "V1_BE075" in txt and "V2_BE050" in txt and "M5_human" in txt
    assert "0.75" in txt and "0.50" in txt and "BE_OFF" in txt
    assert "POST-RELEASE" in txt
    assert "ALL brackets" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "V1_BE075", "V2_BE050"}
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
        assert v["be_k"] == ({"V1_BE075": 0.75, "V2_BE050": 0.50}.get(row))
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "V1_BE075",
                                                    "V2_BE050"}
    assert out["meta"]["pick_dev4"] in ("V1_BE075", "V2_BE050",
                                        "none-eligible")


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "V1_BE075" in rep and "V2_BE050" in rep and "M5_human" in rep
    assert "POST-RELEASE" in rep
    assert len(rep.strip().splitlines()[-3:]) == 3
