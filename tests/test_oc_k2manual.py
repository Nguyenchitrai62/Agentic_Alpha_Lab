"""Tests for oc_k2manual (MANUAL dip brackets x Kronos K2 multiplier).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_k2manual/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_k2manual"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_k2manual", HERE / "compute_k2manual.py")
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
    assert m.K2_HI == 1.25 and m.K2_LO == 0.75
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "KM_K2", "CTRL"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "KM_K2": "k2",
                             "CTRL": "ctrl"}
    assert m.ANCH5 == ("2021-09-24", "2022-09-24", "2023-09-24",
                       "2024-09-24", "2025-09-24")


def test_helpers_assign_mult():
    m = _mod()
    # direction +1 (all frozen fits): high risk -> hi, low risk -> lo
    assert m.assign_mult(3.0, 1, 0.5, 2.0) == pytest.approx(1.25)
    assert m.assign_mult(0.2, 1, 0.5, 2.0) == pytest.approx(0.75)
    assert m.assign_mult(1.0, 1, 0.5, 2.0) == pytest.approx(1.0)
    assert m.assign_mult(2.0, 1, 0.5, 2.0) == pytest.approx(1.25)  # edge in
    assert m.assign_mult(0.5, 1, 0.5, 2.0) == pytest.approx(0.75)  # edge in
    assert m.assign_mult(float("nan"), 1, 0.5, 2.0) == 1.0
    # mirrored direction (not hit with frozen fits, coded symmetrically)
    assert m.assign_mult(3.0, -1, 0.5, 2.0) == pytest.approx(0.75)
    assert m.assign_mult(0.2, -1, 0.5, 2.0) == pytest.approx(1.25)
    assert m.assign_mult(1.0, -1, 0.5, 2.0) == pytest.approx(1.0)
    assert m.geo_mean_monthly([5.0, 5.0, 5.0, 5.0]) == pytest.approx(5.0)


def test_helpers_anchor_of():
    m = _mod()
    assert m.anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2022-09-23", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2023-01-01", tz="UTC"), 0) == 1
    assert m.anchor_of(pd.Timestamp("2026-01-01", tz="UTC"), 0) == 4
    assert m.anchor_of(pd.Timestamp("2026-09-23", tz="UTC"), 0) == 4
    assert m.anchor_of(pd.Timestamp("2021-09-24 02:00", tz="UTC"), 3) == 0


# ---- hand-checked synthetic cases ---------------------------------------
def test_synthetic_k2_from_low1():
    m = _mod()
    # risk = -low1; fits dir +1, q20 0.5, q80 2.0
    fits = {"2021-09-24": {"direction": 1, "q20": 0.5, "q80": 2.0,
                           "rho": 0.05},
            "2022-09-24": {"direction": 1, "q20": 0.5, "q80": 2.0,
                           "rho": 0.05},
            "2023-09-24": {"direction": 1, "q20": 0.5, "q80": 2.0,
                           "rho": 0.05},
            "2024-09-24": {"direction": 1, "q20": 0.5, "q80": 2.0,
                           "rho": 0.05},
            "2025-09-24": {"direction": 1, "q20": 0.5, "q80": 2.0,
                           "rho": 0.05}}
    t0 = pd.Timestamp("2024-06-01 04:00", tz="UTC")
    kronos = {(sym, 0, t0): -1.0 for sym in m.MAJORS}
    # deep low on this coin: risk 3.0 -> hi
    kronos[("BTCUSDT", 0, t0)] = -3.0
    assert m.k2_mult_for("BTCUSDT", t0, 0, kronos, fits) == pytest.approx(1.25)
    # shallow low: risk 0.2 -> lo
    kronos[("BTCUSDT", 0, t0)] = -0.2
    assert m.k2_mult_for("BTCUSDT", t0, 0, kronos, fits) == pytest.approx(0.75)
    # middle: risk 1.0 -> 1.0
    kronos[("BTCUSDT", 0, t0)] = -1.0
    assert m.k2_mult_for("BTCUSDT", t0, 0, kronos, fits) == pytest.approx(1.0)
    # missing feature row -> neutral 1.0
    assert m.k2_mult_for("BTCUSDT", t0, 1, kronos, fits) == 1.0


def test_synthetic_ctrl_is_decision_mean():
    m = _mod()
    t0 = pd.Timestamp("2024-06-01 04:00", tz="UTC")
    t1 = pd.Timestamp("2024-06-01 08:00", tz="UTC")
    fits = {a: {"direction": 1, "q20": 0.5, "q80": 2.0, "rho": 0.05}
            for a in m.ANCH5}
    # one bar where every coin is hi (1.25), one where every coin is lo
    kronos = {}
    for sym in m.MAJORS:
        kronos[(sym, 0, t0)] = -3.0  # risk 3.0 -> 1.25
        kronos[(sym, 0, t1)] = -0.2  # risk 0.2 -> 0.75
    # filler bars (mult 1.0) so every anchor year has rows, as real data does
    for ts in ("2022-01-01 04:00", "2023-01-01 04:00", "2025-01-01 04:00",
               "2026-01-01 04:00"):
        tt = pd.Timestamp(ts, tz="UTC")
        for sym in m.MAJORS:
            kronos[(sym, 0, tt)] = -1.0  # risk 1.0 -> 1.0
    ctrl = m.decision_means(kronos, fits)
    y0 = m.anchor_of(t0, 0)
    c = ctrl[m.ANCH5[y0]]["c"]
    assert c == pytest.approx((1.25 + 0.75) / 2.0)
    assert ctrl[m.ANCH5[y0]]["n_train"] == 10  # 5 coins x 2 bars


def test_year_of_feature_excludes_unsimulated_rows():
    m = _mod()
    # pre-live rows (before the first anchor) are never simulated: excluded
    assert m.year_of_feature(pd.Timestamp("2020-11-01 04:00", tz="UTC"),
                             0) is None
    # rows at/after live1 are never simulated: excluded
    assert m.year_of_feature(pd.Timestamp("2026-09-23 04:00", tz="UTC"),
                             0) is None
    assert m.year_of_feature(pd.Timestamp("2021-09-24 04:00", tz="UTC"),
                             0) == 0
    assert m.year_of_feature(pd.Timestamp("2024-06-01 04:00", tz="UTC"),
                             0) == 2


# ---- causality / truncation -----------------------------------------------
def test_causality_filter_is_bar_open_only():
    src = (HERE / "compute_k2manual.py").read_text()
    # sizing key is the holding-bar open T on this phase's grid
    assert "idx[i] + pd.Timedelta(hours=4)" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    # no fill-minute / 1m data enters any sizing decision
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute", "trade-through",
                "trade_through", "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_and_book_untouched():
    src = (HERE / "compute_k2manual.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "if hours[i] == night:\n            return 0.0" in src  # K2 filter
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_k2manual.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_manualsplit():
    mine = (HERE / "compute_k2manual.py").read_text()
    ref = (ROOT / "research/tournament/oc_manualsplit/compute_manualsplit.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_k2manual.py").read_text(encoding="utf-8")
    bad = [i + 1 for i, l in enumerate(src.splitlines())
           if any(ord(c) > 127 for c in l)]
    assert bad == [], bad


# ---- frozen baseline numbers ----------------------------------------------
def test_frozen_baseline_numbers():
    m5 = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json")
                    .read_text())["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)


def test_frozen_k2_fits():
    fits = json.loads((ROOT / "research/tournament/oc_kronoshidden/fits.json")
                       .read_text())
    assert set(fits) == {"2021-09-24", "2022-09-24", "2023-09-24",
                         "2024-09-24", "2025-09-24"}
    for a, f in fits.items():
        assert f["direction"] == 1
        assert f["q20"] < f["q80"]


def test_plan_preregistration_first():
    txt = (HERE / "PLAN.md").read_text()
    assert "KM_K2" in txt and "CTRL" in txt and "M5_human" in txt
    assert "1.25" in txt and "0.75" in txt and "fits.json" in txt
    assert "POST-HOC" in txt and "UPPER" in txt
    assert "decision mean" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "KM_K2", "CTRL"}
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
        assert len(v["decision_mean"]) == 5
    assert set(out["meta"]["ctrl"]) == {"2021-09-24", "2022-09-24",
                                        "2023-09-24", "2024-09-24",
                                        "2025-09-24"}
    for a, c in out["meta"]["ctrl"].items():
        assert 0.5 < c["c"] < 1.5 and c["n_train"] > 0
    km = out["rows"]["KM_K2"]
    assert km["decision_mean"] == pytest.approx(
        [out["meta"]["ctrl"][a]["c"] for a in
         ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24",
          "2025-09-24")])
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "KM_K2",
                                                   "CTRL"}


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "KM_K2" in rep and "CTRL" in rep and "M5_human" in rep
    assert "POST-HOC" in rep and "UPPER BOUND" in rep
    vi = rep.strip().splitlines()[-3:]
    assert len(vi) == 3
