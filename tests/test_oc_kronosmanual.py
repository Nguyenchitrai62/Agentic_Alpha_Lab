"""Tests for oc_kronosmanual (ex-ante Kronos corr-aware dip sizing, MANUAL).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_kronosmanual/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_kronosmanual"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_kronosmanual", HERE / "compute_kronosmanual.py")
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
    assert m.KM1_K == 1.0 and m.KM2_K == 2.0 and m.EMBARGO_DAYS == 7
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "KM1", "KM2", "CTRL"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "KM1": "km1",
                             "KM2": "km2", "CTRL": "ctrl"}


def test_helpers_raw_mult():
    m = _mod()
    assert m.raw_mult(0.0, "km1") == 1.0
    assert m.raw_mult(0.0, "km2") == 1.0
    assert m.raw_mult(1.0, "km1") == pytest.approx(0.5)
    assert m.raw_mult(1.0, "km2") == pytest.approx(1.0 / 3.0)
    assert m.raw_mult(0.5, "km1") == pytest.approx(1.0 / 1.5)
    assert m.raw_mult(0.5, "km2") == pytest.approx(0.5)
    assert m.raw_mult(0.0, "ctrl", 0.4) == pytest.approx(1.0 / 1.4)
    assert m.geo_mean_monthly([5.0, 5.0, 5.0, 5.0]) == pytest.approx(5.0)


def test_helpers_expected_n_missing_rule():
    m = _mod()
    # four others present: plain sum
    assert m.expected_n([0.1, 0.2, 0.0, 0.3]) == pytest.approx(0.6)
    # one missing -> mean-imputed scaling over 3 available
    assert m.expected_n([0.1, 0.2, float("nan"), 0.3]) == pytest.approx(0.8)
    assert m.expected_n([0.1, None, 0.0, 0.3]) == pytest.approx(0.4 * 4 / 3)
    # fewer than 3 finite -> neutral (caller maps to 1.0)
    assert m.expected_n([0.1, float("nan"), None, float("nan")]) is None
    assert m.expected_n([float("nan")] * 4) is None
    # final_mult neutral on missing
    assert m.final_mult("km1", None, 1.3) == 1.0
    assert m.final_mult("km2", None, 1.3) == 1.0
    assert m.final_mult("ctrl", None, 1.0, 0.4) == 1.0


def test_helpers_anchor_of():
    m = _mod()
    assert m.anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2022-09-23", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2023-01-01", tz="UTC"), 0) == 1
    assert m.anchor_of(pd.Timestamp("2026-01-01", tz="UTC"), 0) == 4
    assert m.anchor_of(pd.Timestamp("2026-09-23", tz="UTC"), 0) == 4
    # shift moves the grid: same clock time belongs to the shifted year
    assert m.anchor_of(pd.Timestamp("2021-09-24 02:00", tz="UTC"), 3) == 0


# ---- hand-checked synthetic cases ---------------------------------------
def test_synthetic_en_and_rescaling():
    m = _mod()
    # BTC bar: others ETH 0.125, SOL 0.0, BNB 0.25, XRP 0.0625 -> E_n = 0.4375
    e = m.expected_n([0.125, 0.0, 0.25, 0.0625])
    assert e == pytest.approx(0.4375)
    assert m.raw_mult(e, "km1") == pytest.approx(1 / 1.4375)
    assert m.raw_mult(e, "km2") == pytest.approx(1 / 1.875)
    # training-anchored rescaling: final = raw / mean(raw)
    assert m.final_mult("km1", e, 1.0 / 0.9) == pytest.approx(1 / 1.4375 / 0.9)
    # CTRL constant, no second rescaling
    assert m.final_mult("ctrl", e, 1.0, 0.4) == pytest.approx(1 / 1.4)


def test_synthetic_kronos_mult_for_with_fake_table():
    m = _mod()
    t0 = pd.Timestamp("2024-06-01 04:00", tz="UTC")
    kronos = {(sym, 0, t0): 0.125 for sym in m.MAJORS}
    kronos[("ETHUSDT", 0, t0)] = 0.5
    fits = {a: dict(c=0.4, m1=0.9, m2=0.8, s1=1 / 0.9, s2=1 / 0.8,
                    n_train=100) for a in m.ANCH5}
    # BTC others: ETH .5 + SOL .125 + BNB .125 + XRP .125 = 0.875
    got1 = m.kronos_mult_for("BTCUSDT", t0, 0, "km1", kronos, fits)
    assert got1 == pytest.approx(1 / 1.875 / 0.9)
    got2 = m.kronos_mult_for("BTCUSDT", t0, 0, "km2", kronos, fits)
    assert got2 == pytest.approx(1 / 2.75 / 0.8)
    gotc = m.kronos_mult_for("BTCUSDT", t0, 0, "ctrl", kronos, fits)
    assert gotc == pytest.approx(1 / 1.4)
    # shift isolation: shift 1 has no rows -> neutral 1.0
    assert m.kronos_mult_for("BTCUSDT", t0, 1, "km1", kronos, fits) == 1.0


# ---- causality / truncation -----------------------------------------------
def test_causality_filter_is_bar_open_only():
    src = (HERE / "compute_kronosmanual.py").read_text()
    # sizing key is the holding-bar open T on this phase's grid
    assert "idx[i] + pd.Timedelta(hours=4)" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    # no fill-minute / 1m data enters any sizing decision
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute", "trade-through",
                "trade_through", "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_and_book_untouched():
    src = (HERE / "compute_kronosmanual.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "if hours[i] == night:\n            return 0.0" in src  # KM filter
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_kronosmanual.py").read_text()
    for bad in ("tempfile", "gettempdir", "/tmp", "TMPDIR", "/proc",
                "artifacts/bot", "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_manualsplit():
    mine = (HERE / "compute_kronosmanual.py").read_text()
    ref = (ROOT / "research/tournament/oc_manualsplit/compute_manualsplit.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_kronosmanual.py").read_text(encoding="utf-8")
    bad = [i + 1 for i, l in enumerate(src.splitlines())
           if any(ord(c) > 127 for c in l)]
    assert bad == [], bad


# ---- selection logic ------------------------------------------------------
def _t(Rdev4, Wdev4, DDdev4, losing=0):
    return {"Rdev4": Rdev4, "Wdev4": Wdev4, "DDdev4": DDdev4,
            "losing_dev4": losing}


def test_robust_pick_prefers_worst_year_then_mean():
    m = _mod()
    table = {"KM1": _t(4.0, 1.0, 15.0), "KM2": _t(3.5, 1.5, 15.0)}
    assert m.robust_pick(table) == "KM2"
    table = {"KM1": _t(4.0, 1.0, 15.0), "KM2": _t(4.5, 1.0, 15.0)}
    assert m.robust_pick(table) == "KM2"


def test_robust_pick_filters_dd_and_losing():
    m = _mod()
    table = {"KM1": _t(6.0, 2.0, 21.0), "KM2": _t(3.0, 0.5, 15.0)}
    assert m.robust_pick(table) == "KM2"
    table = {"KM1": _t(6.0, 2.0, 25.0), "KM2": _t(3.0, -1.0, 25.0, losing=1)}
    assert m.robust_pick(table) == "none-eligible"


def test_robust_pick_prefers_mean_above_five():
    m = _mod()
    table = {"KM1": _t(5.5, 0.5, 15.0), "KM2": _t(4.5, 2.0, 15.0)}
    assert m.robust_pick(table) == "KM1"


# ---- frozen baseline numbers ----------------------------------------------
def test_frozen_baseline_numbers():
    m5 = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json")
                    .read_text())["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)


def test_plan_preregistration_first():
    txt = (HERE / "PLAN.md").read_text()
    assert "KM1" in txt and "KM2" in txt and "CTRL" in txt
    assert "1 / (1 + E_n)" in txt and "1 / (1 + 2 E_n)" in txt
    assert "20 (shift, sym) groups" in txt
    assert "POST-HOC" in txt and "UPPER" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "KM1", "KM2", "CTRL"}
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
    assert out["meta"]["pick"] in ("KM1", "KM2", "none-eligible")
    fits = out["meta"]["fits"]
    assert len(fits) == 5
    for a, f in fits.items():
        assert f["n_train"] > 0 and f["s1"] > 1.0 and f["s2"] > f["s1"]


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "KM1" in rep and "KM2" in rep and "CTRL" in rep
    assert "POST-HOC" in rep
    vi = rep.strip().splitlines()[-3:]
    assert len(vi) == 3
