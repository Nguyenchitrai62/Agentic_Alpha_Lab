"""Tests for research/tournament/oc_mcdd (deployment-risk bootstrap)."""
import importlib.util
import json
from pathlib import Path

import numpy as np

OC = Path(__file__).resolve().parents[1] / "research/tournament/oc_mcdd"


def _load():
    spec = importlib.util.spec_from_file_location("mcdd_boot", OC / "mcdd_bootstrap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_results_schema_and_ranges():
    d = json.loads((OC / "results.json").read_text())
    assert d["meta"]["bootstrap"]["seed"] == 0
    assert d["meta"]["bootstrap"]["mean_block_days"] == 20.0
    assert d["meta"]["bootstrap"]["n_paths"] == 10000
    assert d["meta"]["R2B1D16_v411_eq_v406_maxabsdiff"] == 0.0
    for strat, s in d["strategies"].items():
        assert s["n_days"] == 1826 and s["n_returns"] == 1825
        assert len(s["years_empirical"]) == 5
        b = s["bootstrap"]
        for k, v in b.items():
            assert np.isfinite(v), (strat, k)
        for k in ("P_R12_neg", "P_m_lt_5pct", "P_DDm_gt15", "P_DDm_gt20",
                  "P_DDm_gt25", "P_DDc_gt15", "P_DDc_gt20", "P_DDc_gt25"):
            assert 0.0 <= b[k] <= 1.0, (strat, k, b[k])
        assert b["m_p5"] <= b["m_med"] <= b["m_p95"]
        assert b["R12_p5"] <= b["R12_med"] <= b["R12_p95"]


def test_empirical_matches_v411():
    d = json.loads((OC / "results.json").read_text())
    exp_m = {"R2B1D17BF": [2.831, 3.505, 4.669, 11.27, 5.06],
             "R2B1D16": [2.012, 3.716, 4.522, 10.788, 4.853]}
    exp_dd = {"R2B1D17BF": [12.42, 16.23, 18.33, 8.26, 12.81],
              "R2B1D16": [15.16, 16.12, 17.33, 7.85, 12.68]}
    for strat in exp_m:
        ys = d["strategies"][strat]["years_empirical"]
        for y, e in enumerate(exp_m[strat]):
            assert abs(ys[y]["m_geo"] * 100 - e) < 1e-3, (strat, y)
        for y, e in enumerate(exp_dd[strat]):
            assert abs(ys[y]["DD_marked"] * 100 - e) < 0.01, (strat, y)


def test_stationary_blocks_deterministic_and_valid():
    mod = _load()
    rng = np.random.default_rng(0)
    a = mod.stationary_indices(1825, 365, rng, 0.05)
    rng = np.random.default_rng(0)
    b = mod.stationary_indices(1825, 365, rng, 0.05)
    assert a.tolist() == b.tolist()
    assert a.min() >= 0 and a.max() < 1825 and len(a) == 365
    # block structure: count segment starts; mean length near 20 (loose)
    starts = 1 + int(np.sum(np.diff(a) != 1))
    assert 5 <= starts <= 60


def test_reset_chaining_synthetic():
    mod = _load()
    idx = [str(x) for x in
           __import__("pandas").date_range("2021-09-24 08:00", periods=8, freq="4h", tz="UTC")]
    runs = {}
    for s in range(4):
        runs[s] = {"R2B1D17BF": {"t": idx, "eq": [1.0] * 8, "eq_min": [1.0] * 8}}
    D, E, M, segs = mod.chained_mix(runs, "R2B1D17BF")
    assert abs(E[0] - 1.0) < 1e-12 and abs(E[-1] - 1.0) < 1e-12
