"""Tests for oc_phaserebal (LIGHT, no market-data reload except the small v411 pkl)."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
HERE = ROOT / "research/tournament/oc_phaserebal"
RES = json.loads((HERE / "results.json").read_text())


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_files_exist():
    assert (HERE / "PLAN.md").exists()
    assert (HERE / "compute_rebalance.py").exists()
    assert (HERE / "results.json").exists()
    assert (HERE / "REPORT.md").exists()


def test_arm_a_matches_v411():
    v411 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v411/v411_result.json").read_text())
    ref = v411["rows"]["R2B1D17BF"]["years"]
    a = RES["arms"]["a_no_rebal"]
    for got_r, got_dd, (r0, d0) in zip(a["R"], a["DD"], ref):
        assert abs(got_r - r0) < 1e-9
        assert abs(got_dd - d0) < 1e-9
    assert RES["checks"]["reset_match_v411"] is True
    assert abs(a["full_gate"] - v411["rows"]["R2B1D17BF"]["full_path_dd"]) < 0.05


def test_rebalance_calendars():
    assert RES["arms"]["b_monthly"]["n_rebalances"] == 60
    assert RES["arms"]["c_weekly"]["n_rebalances"] == 261
    assert RES["arms"]["b_monthly"]["first_rebal"].startswith("2021-10-01")
    assert RES["arms"]["b_monthly"]["last_rebal"].startswith("2026-09-01")
    assert RES["arms"]["c_weekly"]["first_rebal"].startswith("2021-09-27")
    assert RES["arms"]["c_weekly"]["last_rebal"].startswith("2026-09-21")


def test_r5_is_geo_mean_of_years():
    for arm in ("a_no_rebal", "b_monthly", "c_weekly"):
        m = RES["arms"][arm]
        r5 = 100 * (float(np.prod([1 + r / 100 for r in m["R"]])) ** (1 / 5) - 1)
        assert abs(r5 - m["R5"]) < 0.002
        assert m["DDmax"] == max(m["DD"])


def test_decisions_internally_consistent():
    a = RES["arms"]["a_no_rebal"]
    for cand in ("b_monthly", "c_weekly"):
        c = RES["arms"][cand]
        d = RES["decisions"][cand]
        assert d["n_dd_not_worse"] == sum(x >= -0.005 for x in d["d_DD"])
        assert d["R5_gap"] == round(c["R5"] - a["R5"], 4)
        assert d["specific_pass"] == (d["n_dd_not_worse"] >= 4 and c["R5"] >= a["R5"] - 0.0005)
        assert d["promising"] == (d["specific_pass"] and d["default_pass"])
    assert RES["decisions"]["b_monthly"]["promising"] is False
    assert RES["decisions"]["c_weekly"]["promising"] is False


def test_rebalanced_math_on_synthetic():
    mod = _load("ocph_mod", HERE / "compute_rebalance.py")
    idx = pd.date_range("2021-09-24 04:00", periods=48, freq="h", tz="UTC")
    n = len(idx)
    E = np.column_stack([np.linspace(1, 1 + 0.01 * (k + 1), n) for k in range(4)])
    M = E.copy()
    cal = pd.DatetimeIndex([idx[10], idx[20], idx[30]])
    Ep, Mp, used = mod.rebalanced_path(E, M, idx, cal)
    assert len(used) == 3
    assert abs(float(Ep.iloc[0]) - 1.0) < 1e-12
    # persistent drift differs per phase -> rebalanced end below buy-and-hold mean (rebalance drag)
    assert float(Ep.iloc[-1]) < float(E.mean(axis=1)[-1])
    assert float(Ep.iloc[-1]) > 1.0
    # identical series across phases -> rebalanced equals buy-and-hold mean
    E_same = np.column_stack([np.linspace(1, 1.05, n)] * 4)
    Ep0, _, _ = mod.rebalanced_path(E_same, E_same.copy(), idx, cal)
    assert abs(float(Ep0.iloc[-1]) - 1.05) < 1e-9
    # no rebalances -> pure mean path
    Ep2, _, used2 = mod.rebalanced_path(E, M, idx, pd.DatetimeIndex([], tz="UTC"))
    assert used2 == []
    assert abs(float(Ep2.iloc[-1]) - float(E.mean(axis=1)[-1])) < 1e-9
