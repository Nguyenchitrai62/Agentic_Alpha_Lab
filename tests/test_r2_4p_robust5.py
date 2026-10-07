"""Lightweight tests for the R2-4P 5-year robustness task (no heavy simulation here)."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
TASK = ROOT / "research/diagnostics/r2_4p_robust5/r2_4p_robust5.py"
BASE_RUNS = ROOT / "research/diagnostics/r2_decompose5/runs.pkl"


def _load_task():
    spec = importlib.util.spec_from_file_location("r2_4p_robust5", TASK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_task_file_only_in_allowed_dirs():
    assert TASK.exists()
    assert (ROOT / "research/diagnostics/r2_decompose5/r2_decompose5.py").exists()


def test_geo_mean_monthly():
    m = _load_task()
    assert abs(m.geo_mean_monthly([5.0] * 5) - 5.0) < 1e-9
    # (1.01 * 1.03 * 1.05) ** (1/3) - 1 on 3 entries
    import numpy as np
    rs = [1.0, 3.0, 5.0]
    g = float(np.prod([1 + r / 100 for r in rs]) ** (1 / 3) - 1) * 100
    assert abs(m.geo_mean_monthly(rs) - g) < 1e-9


def test_full_dd_marks_to_minima():
    import pandas as pd
    m = _load_task()
    e = pd.Series([1.0, 1.2, 1.1, 1.3])
    mn = pd.Series([1.0, 1.2, 1.05, 1.3])
    assert abs(m.full_dd(e, mn) - 100 * (1 - 1.05 / 1.2)) < 1e-9


def test_scenario_kwargs_match_assignment():
    m = _load_task()
    assert m.scenario_kwargs("S1") == dict(win_start=5, maker=0.0004, taker=0.0007 + 0.0005)
    assert m.scenario_kwargs("S2") == dict(win_start=15, sleeve_start=16)
    assert m.scenario_kwargs("S3") == dict(win_start=30, sleeve_start=31)
    assert m.scenario_kwargs("S4") == dict(win_start=5, stop_slip=0.5)
    assert m.scenario_kwargs("S5") == dict(win_start=5)


def test_engine_supports_stop_slip_and_no_taker_bps_kwarg():
    spec = importlib.util.spec_from_file_location(
        "v221_sig", ROOT / "research/parallel/rounds/parallel-20260906-r2/v221/v221_grid_hysteresis.py")
    v221 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v221)
    import inspect
    params = inspect.signature(v221.eu.simulate).parameters
    assert "stop_slip" in params  # S4
    assert "win_start" in params and "sleeve_start" in params  # S2/S3
    assert "taker_slip_bps" not in params and "taker_slip" not in params  # S1 documents fallback


def test_baseline_reproduction():
    """Reuse runs.pkl: phase-0 final equity + mix year_stats match r2_decompose5.json."""
    import pickle
    m = _load_task()
    assert BASE_RUNS.exists()
    runs = pickle.loads(BASE_RUNS.read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    assert abs(float(runs[0]["R2"]["eq"][-1]) - 51.6025139386159) < 1e-6
    r = m.reproduction_check()
    assert r["reproduced"], r
    ref = json.loads((ROOT / "research/diagnostics/r2_decompose5/r2_decompose5.json").read_text())["R2"]
    assert len(ref) == 5


def test_results_schema_if_present():
    p = ROOT / "research/diagnostics/r2_4p_robust5/results.json"
    if not p.exists():
        return
    out = json.loads(p.read_text())
    assert out["reproduction"]["reproduced"]
    assert set(out["scenarios"]) == {"S1", "S2", "S3", "S4", "S5"}
    for s, mm in out["scenarios"].items():
        assert len(mm["years"]) == 5
        assert all(set(y) >= {"R", "DD"} for y in mm["years"])
        assert all(isinstance(y["R"], float) and isinstance(y["DD"], float) for y in mm["years"])
        assert isinstance(mm["mean5y"], float) and isinstance(mm["maxDD"], float) and isinstance(mm["fullDD"], float)
