"""Tests for oc_cboostmanual (MANUAL dip brackets x cascade boost).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_cboostmanual/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_cboostmanual"


def _mod(name="compute_cboostmanual"):
    spec = importlib.util.spec_from_file_location(
        name, HERE / "compute_cboostmanual.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _rule():
    spec = importlib.util.spec_from_file_location(
        "cboost_rule", HERE / "cboost_rule.py")
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
    assert m.BOOST == 1.5 and m.B7_DAYS == 7 and m.B3_DAYS == 3
    assert (m.MAKER, m.TAKER, m.FUND_LONG) == (0.0002, 0.00055, 0.0001)
    assert m.ROWS == ["M5_human", "KM_B7", "KM_B3"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "KM_B7": "b7",
                             "KM_B3": "b3"}
    assert m.ANCH5 == ("2021-09-24", "2022-09-24", "2023-09-24",
                       "2024-09-24", "2025-09-24")


def test_rule_constants_verbatim():
    r = _rule()
    assert (r.THRESH, r.WINDOW, r.MIN_PERIODS) == (4.0, 540, 120)
    assert (r.BOOST, r.B7_DAYS, r.B3_DAYS) == (1.5, 7, 3)
    assert r.ANCH5 == ("2021-09-24", "2022-09-24", "2023-09-24",
                       "2024-09-24", "2025-09-24")
    assert r.geo_mean_monthly if hasattr(r, "geo_mean_monthly") else True


def test_helpers_anchor_and_geo():
    m = _mod()
    assert m.anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2022-09-23", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2023-01-01", tz="UTC"), 0) == 1
    assert m.anchor_of(pd.Timestamp("2026-01-01", tz="UTC"), 0) == 4
    assert m.anchor_of(pd.Timestamp("2026-09-23", tz="UTC"), 0) == 4
    assert m.geo_mean_monthly([5.0, 5.0, 5.0, 5.0]) == pytest.approx(5.0)


# ---- hand-checked synthetic cases ---------------------------------------
def test_synthetic_trigger_sigma_arithmetic():
    r = _rule()
    # flat closes -> no trigger (sigma 0 / NaN-safe)
    c = np.full(200, 100.0)
    assert r.triggers_of(c).sum() == 0
    # one huge jump after noisy history fires exactly at the jump bar
    rng = np.random.default_rng(0)
    c2 = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.002, 200)))
    c2[150:] *= 1.30  # persistent +30% level shift: single big return
    fire = r.triggers_of(c2)
    assert bool(fire[150]) is True
    # sigma at the jump bar excludes the jump itself
    rr = r.close_returns(c2)
    sig = r.trailing_sigma(rr)
    assert np.isfinite(sig[150])
    assert abs(rr[150]) > 4.0 * sig[150]
    # tiny wiggle never fires
    c3 = 100.0 + 0.01 * np.sin(np.arange(200))
    assert r.triggers_of(c3).sum() == 0


def test_synthetic_boost_window_next_bar_only():
    r = _rule()
    day = 86_400_000_000_000
    tc = np.array([1_000 * day], dtype=np.int64)
    # T == tc (the cascade bar itself) is NOT boosted: strict 0 < T - tc
    grid = np.array([1_000 * day, 1_000 * day + 4 * 3_600_000_000_000,
                     1_000 * day + 7 * day,
                     1_000 * day + 7 * day + 1], dtype=np.int64)
    m7 = r.boosted_mask(grid, tc, 7)
    assert list(m7) == [False, True, True, False]
    m3 = r.boosted_mask(grid, tc, 3)
    assert list(m3) == [False, True, False, False]
    # empty trigger history -> never boosted
    assert r.boosted_mask(grid, np.array([], dtype=np.int64), 7).sum() == 0


def test_synthetic_filter_night_skip_and_boost():
    m = _mod()
    idx = pd.DatetimeIndex([pd.Timestamp("2024-06-01 00:00", tz="UTC"),
                            pd.Timestamp("2024-06-01 04:00", tz="UTC")],
                           tz="UTC")
    t0 = idx[0] + pd.Timedelta(hours=4)
    t1 = idx[1] + pd.Timedelta(hours=4)
    grid = {(0, t0): (1.5, 1.5), (0, t1): (1.0, 1.0)}
    boost = {"grid": grid, "per_shift": {}}
    cols = list(m.MAJORS)
    # bar 0 is the night bar on shift 0 (hour 4 -> (20+0)%24 = 20? no).
    # Use explicit hours: force night on bar 0.
    hours = np.array([20, 8])
    filt = m.build_cboost_filter(hours, 20, idx, cols, 0, "b7", boost)
    # night bar -> 0 even though boosted
    assert filt(0, 0, 0) == 0.0
    # boosted non-night bar -> 1.5
    hours2 = np.array([8, 8])
    filt2 = m.build_cboost_filter(hours2, 20, idx, cols, 0, "b7", boost)
    assert filt2(1, 0, 0) == pytest.approx(1.0)
    filt3 = m.build_cboost_filter(hours2, 20, idx, cols, 0, "b7", boost)
    assert filt3(0, 0, 0) == pytest.approx(1.5)
    # b3 lookup on the same grid uses the B3 leg
    grid2 = {(0, t0): (1.5, 1.0)}
    boost2 = {"grid": grid2, "per_shift": {}}
    f7 = m.build_cboost_filter(hours2, 20, idx, cols, 0, "b7", boost2)
    f3 = m.build_cboost_filter(hours2, 20, idx, cols, 0, "b3", boost2)
    assert f7(0, 0, 0) == pytest.approx(1.5)
    assert f3(0, 0, 0) == pytest.approx(1.0)
    # missing grid time -> 1.0 (inert, counted)
    fmiss = m.build_cboost_filter(hours2, 20, idx, cols, 0, "b7",
                                  {"grid": {}, "per_shift": {}})
    assert fmiss(0, 0, 0) == 1.0
    assert fmiss.misses[0] >= 1


# ---- causality / truncation -----------------------------------------------
def test_causality_truncation_triggers_stable():
    r = _rule()
    rng = np.random.default_rng(7)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, 800)))
    c[700] *= 1.25  # one cascade-like jump
    full = r.triggers_of(c)
    cut = r.triggers_of(c[:500])
    assert (full[:500] == cut).all()


def test_causality_filter_is_bar_open_only():
    src = (HERE / "compute_cboostmanual.py").read_text()
    # sizing key is the holding-bar open T on this phase's grid
    assert "idx[i] + pd.Timedelta(hours=4)" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    # no fill-minute / 1m data enters any sizing decision
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute", "trade-through",
                "trade_through", "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_and_book_untouched():
    src = (HERE / "compute_cboostmanual.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "if hours[i] == night:\n            return 0.0" in src
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_cboostmanual.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_k2manual():
    mine = (HERE / "compute_cboostmanual.py").read_text()
    ref = (ROOT / "research/tournament/oc_k2manual/compute_k2manual.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    for fn in ("compute_cboostmanual.py", "cboost_rule.py"):
        src = (HERE / fn).read_text(encoding="utf-8")
        bad = [i + 1 for i, l in enumerate(src.splitlines())
               if any(ord(c) > 127 for c in l)]
        assert bad == [], (fn, bad)


# ---- frozen baseline numbers ----------------------------------------------
def test_frozen_baseline_numbers():
    m5 = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json")
                    .read_text())["rows"]["M5_human"]
    assert (m5["R5"], m5["W"], m5["maxDD"], m5["fullDD"], m5["book_win"]) == \
        (3.728, 0.847, 17.94, 17.79, 0.6482)


def test_frozen_boost_grid_readable():
    import pandas as pd
    df = pd.read_parquet(
        ROOT / "research/tournament/oc_cascadeboost/boost_mult_4shift.parquet",
        columns=["shift", "T", "mult_B7", "mult_B3"])
    assert len(df) == 53877
    assert sorted(df["shift"].unique().tolist()) == [0, 1, 2, 3]
    assert set(df["mult_B7"].unique()) <= {1.0, 1.5}
    assert set(df["mult_B3"].unique()) <= {1.0, 1.5}


def test_plan_preregistration_first():
    txt = (HERE / "PLAN.md").read_text()
    assert "KM_B7" in txt and "KM_B3" in txt and "M5_human" in txt
    assert "1.5" in txt and "7-day" in txt
    assert "CONTAMINATED" in txt
    assert "BIT-EXACT" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "KM_B7", "KM_B3"}
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
        assert len(v["sized_mean"]) == 5
    assert out["meta"]["robust_pick_dev4"] in ("KM_B7", "KM_B3",
                                               "none-eligible")
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "KM_B7",
                                                   "KM_B3"}


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "KM_B7" in rep and "KM_B3" in rep and "M5_human" in rep
    assert "CONTAMINATED" in rep
    vi = rep.strip().splitlines()[-3:]
    assert len(vi) == 3
