"""Tests for oc_manualveto (MANUAL volatility veto of new bracket placement).

Fast only: no engine runs, no 1m data. Post-run schema/verdict tests skip
until research/tournament/oc_manualveto/results.json exists.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_manualveto"


def _mod():
    spec = importlib.util.spec_from_file_location(
        "compute_manualveto", HERE / "compute_manualveto.py")
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
    assert m.ROWS == ["M5_human", "VETO_V1", "VETO_V2"]
    assert m.ENGINE_MODE == {"M5_human": "ref", "VETO_V1": "v1",
                             "VETO_V2": "v2"}
    assert m.ANCH5 == ("2021-09-24", "2022-09-24", "2023-09-24",
                       "2024-09-24", "2025-09-24")
    assert m.SIG_WIN == 360 and m.SIG_MIN == 120
    assert m.P80_WIN == 540 and m.P80_Q == 0.80
    assert m.RANGE_BARS == 6 and m.RANGE_MULT == 2.0
    assert m.MED_WIN == 180


def test_helpers_geo_anchor():
    m = _mod()
    assert m.geo_mean_monthly([5.0, 5.0, 5.0, 5.0]) == pytest.approx(5.0)
    assert m.anchor_of(pd.Timestamp("2021-09-24", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2022-09-23", tz="UTC"), 0) == 0
    assert m.anchor_of(pd.Timestamp("2023-01-01", tz="UTC"), 0) == 1
    assert m.anchor_of(pd.Timestamp("2026-01-01", tz="UTC"), 0) == 4


# ---- hand-checked synthetic cases ---------------------------------------
def test_synthetic_sigma_veto():
    m = _mod()
    # flat opens -> sigma ~0, never above its own trailing p80 spike
    idx = pd.date_range("2021-01-01", periods=800, freq="4h", tz="UTC")
    opens = pd.Series(100.0, index=idx)
    # inject one volatile block: +-5% alternating for 10 bars
    opens.iloc[700:710] = [100 * (1.05 if k % 2 else 0.95) for k in range(10)]
    sig = m.sigma360_from_opens(opens)
    p80 = m.trailing_p80(sig)
    v = m.veto_v1_from_sigma(sig, p80)
    # warmup: first 120+540 bars have no veto (min_periods gate)
    assert bool(v.iloc[100]) is False
    # the volatile block must trip at least one veto shortly after
    assert bool(v.iloc[700:760].any()) is True
    # causality: veto at i uses only bars < i -> shifting opens forward by
    # one bar must not change veto[i] through future data
    opens2 = opens.copy()
    opens2.iloc[750] = 200.0  # future spike
    sig2 = m.sigma360_from_opens(opens2)
    p802 = m.trailing_p80(sig2)
    v2 = m.veto_v1_from_sigma(sig2, p802)
    assert v.iloc[740] == v2.iloc[740]


def test_synthetic_sigma_shift_is_past_only():
    m = _mod()
    idx = pd.date_range("2021-01-01", periods=500, freq="4h", tz="UTC")
    opens = pd.Series(100.0, index=idx)
    opens.iloc[-1] = 150.0  # last-bar jump
    sig = m.sigma360_from_opens(opens)
    # shift(1): the jump bar itself has NaN-or-old sigma, never the jump
    assert not np.isfinite(sig.iloc[-1]) or sig.iloc[-1] < 0.2


def test_synthetic_range_expansion():
    m = _mod()
    idx = pd.date_range("2021-01-01", periods=300, freq="4h", tz="UTC")
    high = pd.Series(100.5, index=idx)
    low = pd.Series(99.5, index=idx)
    close = pd.Series(100.0, index=idx)
    # calm: 1% range for 200 bars, then one 10% 24h bar
    high.iloc[250:256] = 105.0
    low.iloc[250:256] = 95.0
    rng = m.range24_from_bars(high, low, close)
    med = m.trailing_median(rng)
    v = m.veto_expansion_from_range(rng, med)
    assert bool(v.iloc[100]) is False  # warmup -> no veto
    assert bool(v.iloc[255]) is True  # 10% range >> 2x ~0 median
    # hand check: 6-bar (105-95)/100 = 0.10
    assert rng.iloc[255] == pytest.approx(0.10)
    # threshold uses strictly past bars: future spike must not move past veto
    high2 = high.copy()
    high2.iloc[290:296] = 120.0
    rng2 = m.range24_from_bars(high2, low, close)
    med2 = m.trailing_median(rng2)
    v2 = m.veto_expansion_from_range(rng2, med2)
    assert v.iloc[255] == v2.iloc[255]


def test_warmup_never_vetoes():
    m = _mod()
    idx = pd.date_range("2021-01-01", periods=100, freq="4h", tz="UTC")
    sig = pd.Series(0.05, index=idx)
    sig.iloc[:50] = np.nan
    p80 = m.trailing_p80(sig)
    v = m.veto_v1_from_sigma(sig, p80)
    assert bool(v.any()) is False
    rng = pd.Series(np.nan, index=idx)
    med = m.trailing_median(rng)
    assert bool(m.veto_expansion_from_range(rng, med).any()) is False


# ---- causality / truncation -----------------------------------------------
def test_causality_veto_is_bar_open_only():
    src = (HERE / "compute_manualveto.py").read_text()
    # veto joined by decision-bar close via merge_asof backward
    assert "merge_asof" in src and "direction=\"backward\"" in src
    assert "pipe_setup" in src  # agent size/TP stay bar-open keyed
    # no fill-minute / 1m data enters any sizing decision
    for bad in ("C[i, f", "La[f", "Ha[f", "fill_minute", "trade-through",
                "trade_through", "minute f", "o1_prev", "sig_prev"):
        assert bad not in src, bad


def test_night_skip_and_veto_skip_and_book_untouched():
    src = (HERE / "compute_manualveto.py").read_text()
    assert "0.0 if hours[i] == night else 1.0" in src  # M5 identity line
    assert "bool(varr[i, a])" in src  # per-coin veto gate
    assert "wait" in src and "hold" in src  # book skip keeps holds
    assert "book_mult" not in src  # book path untouched (harness default)
    assert "sleeve_tp" not in src or "kw[\"sleeve_tp\"]" not in src


def test_no_forbidden_markers_in_script():
    src = (HERE / "compute_manualveto.py").read_text()
    for bad in ("tempfile", "gettempdir", "TMPDIR", "artifacts/bot",
                "git stash", "git commit", "Kaggle",
                "authenticated", "bybit_v5"):
        assert bad not in src, bad


def test_m5_filter_line_parity_with_manualsplit():
    mine = (HERE / "compute_manualveto.py").read_text()
    ref = (ROOT / "research/tournament/oc_manualsplit/compute_manualsplit.py").read_text()
    line = "kw[\"sleeve_filter\"] = lambda i, a, r: 0.0 if hours[i] == night else 1.0"
    assert line in mine and line in ref


def test_script_is_ascii():
    src = (HERE / "compute_manualveto.py").read_text(encoding="utf-8")
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
    assert "VETO_V1" in txt and "VETO_V2" in txt and "M5_human" in txt
    assert "sigma360" in txt and "p80" in txt and "2.0" in txt
    assert "POST-HOC" in txt
    assert "skip-only" in txt


# ---- post-run artefacts -------------------------------------------------------
@needs_results
def test_results_schema_and_parity():
    out = json.loads((HERE / "results.json").read_text())
    assert set(out["rows"]) == {"M5_human", "VETO_V1", "VETO_V2"}
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
        assert len(v["veto_rate"]) == 5
    assert out["meta"]["robust_pick_dev4"] in ("VETO_V1", "VETO_V2")
    assert set(out["meta"]["eligibility_dev4"]) == {"M5_human", "VETO_V1",
                                                    "VETO_V2"}


@needs_results
def test_report_final_verdict():
    rep = (HERE / "REPORT.md").read_text()
    assert "VETO_V1" in rep and "VETO_V2" in rep and "M5_human" in rep
    assert "POST-HOC" in rep
    vi = rep.strip().splitlines()[-3:]
    assert len(vi) == 3
