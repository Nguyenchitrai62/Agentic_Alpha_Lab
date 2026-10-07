"""Tests for research/diagnostics/oc_usdt4p (assignment OPENCODE_W_oc_usdt4p)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "diagnostics" / "oc_usdt4p"


def _load_script():
    spec = importlib.util.spec_from_file_location("oc_usdt4p_mod", str(OC / "oc_usdt4p.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _results():
    return json.loads((OC / "results.json").read_text())


def test_results_exists_and_schema():
    r = _results()
    assert r["version"] == "oc_usdt4p"
    assert r["reproduced"] is True
    assert set(r["rows"]) == {"R2B1D17BFG2", "R2B1D17BFG2_USDT"}
    for row in r["rows"].values():
        for k in ("mean5y", "worst", "maxDD", "losing", "years", "dev4", "full_path_dd",
                  "per_year", "win_all_5y", "book_5y_R", "book_5y_W", "book_maxDD",
                  "book_dev4", "book_per_year"):
            assert k in row, k
        assert len(row["years"]) == 5
        assert len(row["per_year"]) == 5
        assert len(row["book_per_year"]) == 5
        for y in row["per_year"]:
            for k in ("year", "R", "DD", "win", "n", "nb", "nr"):
                assert k in y, k
            assert y["win"] is None or 0.0 <= y["win"] <= 1.0
        for b in row["book_per_year"]:
            assert "R" in b and "DD" in b
    assert len(r["gaps_usdt_minus_base yearly R"]) == 5
    assert "full_path_dd_gap_pp" in r
    assert "live_feasibility" in r
    assert r["verdict"] in ("KEEP-CANDIDATE", "NO")


def test_usdt_z_uses_only_closed_bars_20_rows():
    """The z at each book row uses only hourly bars that closed before the row time."""
    m = _load_script()
    usdt = m.USDT
    # 20 random 4h grid times across the walk-forward window.
    grid = pd.date_range("2021-09-24", "2026-09-23 16:00", freq="4h", tz="UTC")
    rng = np.random.default_rng(404)
    sample = np.sort(rng.choice(np.arange(len(grid)), size=20, replace=False))
    for i in sample:
        T = grid[i]
        trunc = usdt[usdt["end"] <= T - pd.Timedelta(seconds=1)]
        expect = float(trunc["usdt_z90"].iloc[-1]) if len(trunc) else np.nan
        got = float(m.asof_z(usdt, pd.DatetimeIndex([T]))[0])
        if np.isnan(expect):
            assert np.isnan(got), f"expected NaN at {T}"
        else:
            assert np.isclose(got, expect, equal_nan=True), f"z mismatch at {T}"
        # The hourly bar straddling T (end == T) must never leak in:
        # its close is not in the truncation set even though its start < T.
        leak = usdt[usdt["end"] == T]
        if len(leak):
            assert (trunc["end"] != T).all()
    # Full-window coverage: USDT history starts 2021-05-04, so every scored
    # 4h row has a finite z (warmed up before 2021-09-24).
    zbar = m.asof_z(usdt, grid)
    assert bool(np.isfinite(zbar).all())


def test_rule_math_tilt():
    m = _load_script()
    assert m.Z_HI == 1.0 and m.Z_LO == -1.0
    assert m.UP_MULT == 1.15 and m.DOWN_MULT == 0.85
    rng = np.random.default_rng(7)
    base = rng.normal(size=(8, 3))
    z = np.array([1.5, -1.5, 0.5, np.nan, 1.0, -1.0, 2.0, -2.0])
    mult = m.usdt_mult(z)
    assert list(mult) == [1.15, 0.85, 1.0, 1.0, 1.0, 1.0, 1.15, 0.85]
    # Boundary z == +/-1 is NOT tilted (strict > / <).
    rule = np.where(base > 0, base * mult[:, None], base)
    assert bool((rule[2] == base[2]).all())
    assert bool((rule[3] == base[3]).all())
    assert bool((rule[base[:, 0] <= 0, 0] == base[base[:, 0] <= 0, 0]).all())
    pos_up = (base > 0) & (z[:, None] > 1.0)
    pos_dn = (base > 0) & (z[:, None] < -1.0)
    assert bool((rule[pos_up] == 1.15 * base[pos_up]).all())
    assert bool((rule[pos_dn] == 0.85 * base[pos_dn]).all())
    # Shorts/flats bit-identical everywhere.
    assert bool((rule[base <= 0] == base[base <= 0]).all())


def test_reproduction_matches_v421():
    r = _results()
    base = r["rows"]["R2B1D17BFG2"]
    assert base["mean5y"] == 5.41
    assert base["maxDD"] == 16.91
    assert base["full_path_dd"] == 16.82


def test_verdict_matches_rule():
    r = _results()
    base, usdt = r["rows"]["R2B1D17BFG2"], r["rows"]["R2B1D17BFG2_USDT"]
    gaps = [round(usdt["per_year"][y]["R"] - base["per_year"][y]["R"], 3) for y in range(5)]
    assert list(r["gaps_usdt_minus_base yearly R"]) == gaps
    assert r["worst_year_gap"] == min(gaps)
    assert r["full_path_dd_gap_pp"] == round(usdt["full_path_dd"] - base["full_path_dd"], 2)
    expect = "KEEP-CANDIDATE" if (r["full_path_dd_gap_pp"] <= 0.3 + 1e-12
                                  and usdt["mean5y"] >= 5.45
                                  and min(gaps) > -0.3 - 1e-12
                                  and usdt["dev4"] > base["dev4"]) else "NO"
    assert r["verdict"] == expect
    rep = (OC / "REPORT.md").read_text()
    assert f"VERDICT: {expect}" in rep
