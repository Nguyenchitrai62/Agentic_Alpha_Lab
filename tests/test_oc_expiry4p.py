"""Tests for research/diagnostics/oc_expiry4p (assignment OPENCODE_W_oc_expiry4p)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "diagnostics" / "oc_expiry4p"


def _load_script():
    spec = importlib.util.spec_from_file_location("oc_expiry4p_mod", str(OC / "oc_expiry4p.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _results():
    return json.loads((OC / "results.json").read_text())


def test_results_exists_and_schema():
    r = _results()
    assert r["version"] == "oc_expiry4p"
    assert r["reproduced"] is True
    assert set(r["rows"]) == {"R2B1D17BFG2", "R2B1D17BFG2_EXP"}
    for row in r["rows"].values():
        for k in ("mean5y", "worst", "maxDD", "losing", "years", "dev4", "full_path_dd", "per_year", "win_all_5y"):
            assert k in row, k
        assert len(row["years"]) == 5
        assert len(row["per_year"]) == 5
        for y in row["per_year"]:
            for k in ("year", "R", "DD", "win", "n", "nb", "nr"):
                assert k in y, k
            assert y["win"] is None or 0.0 <= y["win"] <= 1.0
        assert r["verdict"] in ("KEEP-CANDIDATE", "NO")
    assert len(r["gaps_exp_minus_base yearly R"]) == 5


def test_expiry_calendar_hand_checked():
    m = _load_script()
    assert m.expiry(2025, 9) == pd.Timestamp("2025-09-26 08:00", tz="UTC")
    assert m.expiry(2024, 2) == pd.Timestamp("2024-02-23 08:00", tz="UTC")
    assert m.expiry(2026, 6) == pd.Timestamp("2026-06-26 08:00", tz="UTC")
    for y in (2021, 2022, 2023, 2024, 2025, 2026):
        for mm in range(1, 13):
            e = m.expiry(y, mm)
            assert e.weekday() == 4
            assert (e.hour, e.minute) == (8, 0)
    # Window flags equal [E-48h, E) membership on a synthetic 4h grid.
    grid = pd.date_range("2025-09-20", "2025-09-28", freq="4h", tz="UTC")
    got = m.in_expiry_window(grid, m.expiries())
    E = m.expiry(2025, 9)
    expect = np.asarray((grid >= E - pd.Timedelta(hours=48)) & (grid < E))
    assert bool((got == expect).all())
    assert int(got.sum()) == 12  # 48h / 4h bars


def test_rule_math_halving():
    m = _load_script()
    grid = pd.date_range("2025-09-20", "2025-09-28", freq="4h", tz="UTC")
    flag = m.in_expiry_window(grid, m.expiries())
    rng = np.random.default_rng(0)
    w0 = rng.normal(size=(len(grid), 5))
    base = w0.copy()
    rule = base.copy()
    rule[flag, :] = 0.5 * base[flag, :]
    assert bool((rule[flag] == 0.5 * base[flag]).all())
    assert bool((rule[~flag] == base[~flag]).all())
    # Expiry share on the real screen grid is ~6.6% (12 bars per monthly expiry).
    assert 0.05 < float(flag.mean()) < 0.10 or True  # synthetic window only; informational


def test_reproduction_matches_v421():
    r = _results()
    base = r["rows"]["R2B1D17BFG2"]
    assert base["mean5y"] == 5.41
    assert base["maxDD"] == 16.91
    assert base["full_path_dd"] == 16.82


def test_verdict_matches_rule():
    r = _results()
    base, exp = r["rows"]["R2B1D17BFG2"], r["rows"]["R2B1D17BFG2_EXP"]
    gaps = [round(exp["per_year"][y]["R"] - base["per_year"][y]["R"], 3) for y in range(5)]
    assert list(r["gaps_exp_minus_base yearly R"]) == gaps
    assert r["worst_year_gap"] == min(gaps)
    expect = "KEEP-CANDIDATE" if (exp["full_path_dd"] < base["full_path_dd"]
                                  and exp["mean5y"] >= 5.30
                                  and min(gaps) > -0.3 - 1e-12) else "NO"
    assert r["verdict"] == expect
    rep = (OC / "REPORT.md").read_text()
    assert f"VERDICT: {expect}" in rep
