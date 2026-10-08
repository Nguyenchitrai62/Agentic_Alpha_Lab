"""Tests for oc_m_btceth (IDEAS9 #1 BTC+ETH-only bracket focus, MANUAL).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_m_btceth/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_m_btceth"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_m_btceth", HERE / "compute_m_btceth.py")
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
    assert m.V1_COINS == ("BTCUSDT", "ETHUSDT")
    assert m.V2_COINS == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    assert set(m.V1_COINS) < set(m.V2_COINS) < set(m.MAJORS)
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "V1_BTCETH", "V2_BTCETHSOL"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "V1_BTCETH": "v1",
                             "V2_BTCETHSOL": "v2"}
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
def test_synthetic_coin_filter_values():
    m = _mod()
    cols = list(m.MAJORS)
    v1 = m.allowed_indices(cols, m.V1_COINS)
    v2 = m.allowed_indices(cols, m.V2_COINS)
    assert v1 == {0, 1}
    assert v2 == {0, 1, 2}
    # V1: BTC/ETH pass, SOL/BNB/XRP blocked; night blocks everything
    assert m.coin_filter_value(0, v1, False) == 1.0
    assert m.coin_filter_value(1, v1, False) == 1.0
    assert m.coin_filter_value(2, v1, False) == 0.0
    assert m.coin_filter_value(4, v1, False) == 0.0
    assert m.coin_filter_value(0, v1, True) == 0.0
    # V2: SOL passes, BNB/XRP blocked
    assert m.coin_filter_value(2, v2, False) == 1.0
    assert m.coin_filter_value(3, v2, False) == 0.0
    assert m.coin_filter_value(4, v2, False) == 0.0
    # full universe passes everywhere except night
    assert m.coin_filter_value(4, set(range(5)), False) == 1.0
    assert m.coin_filter_value(4, set(range(5)), True) == 0.0


def test_synthetic_book_action_for_excluded():
    m = _mod()
    # allowed + day -> None (use base policy)
    assert m.book_action_for_excluded(0, False, True) is None
    assert m.book_action_for_excluded(1, False, True) is None
    # night applies first even on allowed coins
    assert m.book_action_for_excluded(0, True, True) == "wait"
    assert m.book_action_for_excluded(1, True, True) == "hold"
    # excluded coin: wait-if-flat / hold-if-in-position
    assert m.book_action_for_excluded(0, False, False) == "wait"
    assert m.book_action_for_excluded(2, False, False) == "hold"
    # night + excluded: same wait/hold
    assert m.book_action_for_excluded(0, True, False) == "wait"
    assert m.book_action_for_excluded(1, True, False) == "hold"


def test_synthetic_robust_pick_dev4_only():
    m = _mod()

    def _row(rdev4, wdev4, dddev4, losing):
        return {"Rdev4": rdev4, "Wdev4": wdev4, "DDdev4": dddev4,
                "losing_dev4": losing}

    # highest WORST wins; ties -> higher mean
    t = {"V1_BTCETH": _row(3.0, 0.9, 15.0, 0),
         "V2_BTCETHSOL": _row(3.5, 0.8, 15.0, 0),
         "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t) == "V1_BTCETH"
    # mean >= 5 preferred even with a lower WORST
    t2 = {"V1_BTCETH": _row(4.9, 1.5, 15.0, 0),
          "V2_BTCETHSOL": _row(5.1, 0.2, 15.0, 0),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t2) == "V2_BTCETHSOL"
    # DD breach / losing year -> none-eligible
    t3 = {"V1_BTCETH": _row(6.0, 1.5, 21.0, 0),
          "V2_BTCETHSOL": _row(6.0, 1.5, 19.0, 1),
          "M5_human": _row(3.6, 0.8, 17.9, 0)}
    assert m.robust_pick(t3) == "none-eligible"


# ---- causality / truncation -----------------------------------------------
def test_causality_filter_is_bar_open_only():
    src = (HERE / "compute_m_btceth.py").read_text()
    # dip sizing key is the frozen coin allow-list (no market data at all)
    assert "coin_filter_value" in src
    assert "V1_COINS" in src and "V2_COINS" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    # book filter keys only on (position, night hour, allow-list)
    assert "book_action_for_excluded" in src
    # no fill-minute / 1m data enters any sizing decision
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute",
                "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_first_and_book_mult_untouched():
    src = (HERE / "compute_m_btceth.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "book_action_for_excluded" in src
    assert "hours[i] == night" in src
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_m_btceth.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_k2manual():
    mine = (HERE / "compute_m_btceth.py").read_text()
    ref = (ROOT / "research/tournament/oc_k2manual/compute_k2manual.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_m_btceth.py").read_text(encoding="utf-8")
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
    assert "V1_BTCETH" in txt and "V2_BTCETHSOL" in txt and "M5_human" in txt
    assert "BTCUSDT" in txt and "ETHUSDT" in txt and "SOLUSDT" in txt
    assert "POST-RELEASE" in txt
    assert "Others flat" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "V1_BTCETH", "V2_BTCETHSOL"}
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
        assert v["coins"] == out["meta"]["coins"][row]
    assert out["meta"]["coins"]["V1_BTCETH"] == ["BTCUSDT", "ETHUSDT"]
    assert out["meta"]["coins"]["V2_BTCETHSOL"] == ["BTCUSDT", "ETHUSDT",
                                                   "SOLUSDT"]
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "V1_BTCETH",
                                                    "V2_BTCETHSOL"}
    assert out["meta"]["pick_dev4"] in ("V1_BTCETH", "V2_BTCETHSOL",
                                        "none-eligible")


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "V1_BTCETH" in rep and "V2_BTCETHSOL" in rep and "M5_human" in rep
    assert "POST-RELEASE" in rep
    assert len(rep.strip().splitlines()[-3:]) == 3
