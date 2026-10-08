"""Tests for oc_clockweights (LIGHT: v421 pkl + results.json + synthetic hand-checks)."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_clockweights"
RES = json.loads((HERE / "results.json").read_text())


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ref_reproduces_g2_to_digit():
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    ref = RES["ref_G2"]
    assert [y["R"] for y in ref["years"]] == [r for r, _ in exp["years"]]
    assert [y["DD"] for y in ref["years"]] == [d for _, d in exp["years"]]
    assert ref["R5"] == exp["R"] and ref["W5"] == exp["W"] and ref["DDmax"] == exp["DD"]
    assert ref["full_path_dd"] == exp["full_path_dd"] == 16.82
    assert ref["losing5"] == 0


def test_dev4_stats_and_robust_pick():
    v1, v2 = RES["variants"]["V1_invDD"]["dev4"], RES["variants"]["V2_sharpe"]["dev4"]
    assert v1["mean4"] == 5.573 and v1["worst4"] == 2.588 and v1["DDmax4"] == 17.02 and v1["losing4"] == 0
    assert v2["mean4"] == 5.77 and v2["worst4"] == 2.588 and v2["DDmax4"] == 16.63 and v2["losing4"] == 0
    for v in (v1, v2):  # mean4 is the geometric mean of the four dev yearly rates
        fac = float(np.prod([1 + r / 100 for r in v["R"]]))
        assert abs(fac ** (1 / 4) - 1 - v["mean4"] / 100) < 5e-5
        assert v["worst4"] == min(v["R"]) and v["DDmax4"] == max(v["DD"])
    # robust rule: both eligible, mean>=5, worst tied -> higher mean -> V2
    assert RES["pick"]["name"] == "V2_sharpe"
    assert v2["mean4"] > v1["mean4"] and v2["DDmax4"] <= 20 and v1["DDmax4"] <= 20
    assert RES["variants"]["V2_sharpe"]["R5_with_scored_y4"] == 5.55


def test_y4_scored_once_for_pick_and_ref_only():
    once = RES["y4_once"]
    assert set(once) == {"V2_sharpe", "REF_G2"}
    assert once["V2_sharpe"]["R"] == 4.677 and once["V2_sharpe"]["DD"] == 12.78
    assert once["REF_G2"]["R"] == 4.648 and once["REF_G2"]["DD"] == 12.9
    assert "NOT_SCORED" in RES["variants"]["V1_invDD"]["y4"]
    assert "SCORED ONCE" in RES["variants"]["V2_sharpe"]["y4"]


def test_weights_causal_and_sum_to_one():
    for tag in ("V1_invDD", "V2_sharpe"):
        for _, w in RES["variants"][tag]["weights"].items():
            assert abs(sum(w) - 1.0) < 1e-9 and all(x >= 0 for x in w)
    # y0 fallback: no history -> equal
    assert RES["trailing_info"]["2021-09-24"]["n_rows"] == 0
    assert RES["variants"]["V1_invDD"]["weights"]["2021-09-24"] == [0.25] * 4
    # trailing windows end at anchor-7d: exactly 365d of hourly rows (8760),
    # except y1 whose history starts at grid start (8589 < 8760)
    assert RES["trailing_info"]["2022-09-24"]["n_rows"] == 8589
    for a in ("2023-09-24", "2024-09-24", "2025-09-24"):
        assert RES["trailing_info"][a]["n_rows"] == 8760
    # V2 zero-weight only where trailing Sharpe <= 0 (p3 into 2024: -0.683)
    assert RES["variants"]["V2_sharpe"]["weights"]["2024-09-24"][3] == 0.0
    assert RES["trailing_info"]["2024-09-24"]["trail_sharpe"][3] < 0
    # source uses embargoed window, never the test year
    src = (HERE / "compute_clockweights.py").read_text()
    assert "EMBARGO" in src and "A_y" in src or "anchor-7d" in src.lower() or "anchor − 7d" in src or "anchor-7d" in src


def test_weighted_year_synthetic_handcheck():
    mod = _load("ocw_mod", HERE / "compute_clockweights.py")
    # 365d of hourly points strictly inside year 0: (A0, A0+365d]
    idx = pd.date_range("2021-09-24 01:00", periods=24 * 365, freq="h", tz="UTC")
    n = len(idx)
    # all phases double monotonically over the span -> es_end=2 regardless of weights
    Ec = np.column_stack([np.linspace(1.0, 2.0, n)] * 4)
    Mc = Ec.copy()
    r, d, end, _, _ = mod.weighted_year(Ec, Mc, idx, 0, np.array([0.4, 0.3, 0.2, 0.1]))
    assert abs(end - 2.0) < 1e-9
    assert r == round(100 * (2.0 ** (1 / 12) - 1), 3) == 5.946
    assert d == 0.0
    # flat line -> R 0, DD 0
    E0 = np.ones((n, 4))
    r0, d0, e0, _, _ = mod.weighted_year(E0, E0.copy(), idx, 0, np.full(4, 0.25))
    assert (r0, d0, e0) == (0.0, 0.0, 1.0)
    # one phase dips 10% in marks only at mid-year -> weighted DD = 2.5%, R same
    E1 = np.column_stack([np.linspace(1.0, 2.0, n)] * 4)
    M1 = E1.copy()
    M1[n // 2, 0] *= 0.9
    r1, dd, _, _, _ = mod.weighted_year(E1, M1, idx, 0, np.full(4, 0.25))
    assert r1 == 5.946 and abs(dd - 2.5) < 0.01


def test_stitched_full_covers_leap_gap():
    # regression: 2023-09-24+365d = 2024-09-23 but A_3 = 2024-09-24; every grid
    # point (incl. the leap day) must be assigned (no NaN/zero hole -> fake DD)
    mod = _load("ocw_mod2", HERE / "compute_clockweights.py")
    # full-span grid so every anchor year has a segment; the leap day
    # 2024-09-23..24 must be assigned (no NaN/zero hole -> fake DD)
    idx = pd.date_range("2021-09-24 01:00", "2026-09-24 00:00", freq="h", tz="UTC")
    n = len(idx)
    Ec = np.column_stack([np.linspace(1.0, 1.5, n)] * 4)
    Mc = Ec.copy()
    W = {y: np.full(4, 0.25) for y in range(5)}
    A, M = mod.stitched_full(Ec, Mc, idx, W)
    assert bool(np.isfinite(A).all()) and bool(np.isfinite(M).all())
    assert (A > 0).all()
    gap = (idx > pd.Timestamp("2024-09-23", tz="UTC")) & (idx <= pd.Timestamp("2024-09-24", tz="UTC"))
    assert int(gap.sum()) == 24 and bool(np.isfinite(A[gap]).all())


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("V2_sharpe", "5.770", "5.550", "16.63", "NOT_SCORED",
                   "4.677", "REJECT", "Leakage checklist"):
        assert needle in rep, needle
    assert "(3 dong)" in rep
