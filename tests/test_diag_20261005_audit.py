"""Audit tests for diag_20261005 (light: reads saved JSONs + synthetic edge cases)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "research/diagnostics/diag_20261005_audit"


def _load_json(p):
    return json.loads((AUD / p).read_text())


def test_files_present():
    for f in ("rolling_part_a.json", "rolling_part_b.json", "manual_part_a.json", "manual_part_b.json", "COMPARISON.md"):
        assert (AUD / f).exists(), f


def test_rolling_part_a_shape():
    a = _load_json("rolling_part_a.json")
    for rule in ("A0_k3.0", "A1_k3.0", "A2_k3.0", "A3_k3.0", "R_open_k3.0"):
        assert rule in a, rule
        for coin in ("BTCUSDT", "SOLUSDT"):
            assert coin in a[rule], (rule, coin)
            for per in ("pre", "2021", "2022", "2023", "2024"):
                c = a[rule][coin][per]
                assert c["n"] >= 0 and "sum" in c and "mean" in c


def test_rolling_part_b_pass():
    b = _load_json("rolling_part_b.json")
    assert b["mismatches"] == []
    assert b["pass_compare"] is True
    assert b["pass_lookahead"] is True


def test_manual_part_b_pass():
    a = _load_json("manual_part_a.json")
    assert set(a["rows"]) == {"M2_human", "M5_human"}
    for row in ("M2_human", "M5_human"):
        assert len(a["rows"][row]) == 4
    b = _load_json("manual_part_b.json")
    assert b["mismatches"] == []
    assert b["pass_compare"] is True
    assert b["pass_lookahead"] is True
    assert b["m5_base_phase1"]["equals_within_rounding"] is True


def _load_audit_fn():
    spec = importlib.util.spec_from_file_location("raa", AUD / "rolling_audit_a.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_exit_stop_first_and_costs():
    m = _load_audit_fn()
    import numpy as np
    # level 100, sg small so stop=100*(1-8s), tp=100*(1+s); craft bar where both hit same minute
    sg = 0.01
    lv = 100.0
    stop, tp = lv * (1 - 8 * sg), lv * (1 + sg)
    O = np.array([100.0, 100.0, 100.0])
    H = np.array([100.0, tp + 1.0, 100.0])
    Lo = np.array([100.0, stop - 1.0, 100.0])
    r = m.first_exit(O, H, Lo, 0, lv, sg, 2)
    assert r[2] == "stop"  # tie -> stop
    assert abs(r[1] - (min(stop, O[1]) / lv - 1 - m.MK - m.TK)) < 1e-12
    # tp-only minute
    Lo2 = np.array([100.0, stop + 1.0, 100.0])
    r2 = m.first_exit(O, H, Lo2, 0, lv, sg, 2)
    assert r2[2] == "tp"
    assert abs(r2[1] - (tp / lv - 1 - 2 * m.MK)) < 1e-12


def test_comparison_verdicts():
    txt = (AUD / "COMPARISON.md").read_text()
    assert "## Verdict rolling_anchor_dips: PASS" in txt
    assert "## Verdict manual_human: PASS" in txt
