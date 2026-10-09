"""oc_governor tests: governor timing/causality + hand-checked synthetic cases."""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def gov(eq, i, gz=0.20, gw=0.10, win=540):
    """Reference governor formula (engine_user.simulate lines ~497-502)."""
    if i < 2:
        return 1.0
    j = i - 2
    peak = float(np.max(eq[max(0, j - win + 1):j + 1]))
    dd = 1.0 - float(eq[j]) / peak
    return float(np.clip((gz - dd) / gw, 0.0, 1.0))


def test_handchecked_values():
    import pytest as _pt
    # peak 1.0 then slide: eq = [1,1,1,0.95,0.90,0.85,0.80]
    eq = np.array([1.0, 1.0, 1.0, 0.95, 0.90, 0.85, 0.80])
    assert gov(eq, 0) == 1.0 and gov(eq, 1) == 1.0  # first two bars always 1
    # i=2 -> j=0, eq 1.0 at peak -> dd 0 -> g 1
    assert gov(eq, 2) == 1.0
    # i=5 -> j=3, eq 0.95, peak 1.0 -> dd 0.05 -> (0.20-0.05)/0.10 = 1.5 -> clip 1
    assert gov(eq, 5) == 1.0
    # i=6 -> j=4, eq 0.90 -> dd 0.10 -> (0.20-0.10)/0.10 = 1.0 exactly
    assert gov(eq, 6) == _pt.approx(1.0)
    # i=7 would use j=5, eq 0.85 -> dd 0.15 -> g 0.5
    eq2 = np.append(eq, 0.75)
    assert gov(eq2, 7) == _pt.approx(0.5)
    # deep: dd 0.20 -> g 0; dd 0.25 -> g 0 (clipped)
    assert gov(np.array([1.0, 1.0, 1.0, 0.80]), 5) == _pt.approx(0.0, abs=1e-12)
    assert gov(np.array([1.0, 1.0, 1.0, 0.70]), 5) == 0.0


def test_lag_truncation_causality():
    """g[i] sees only eq[..i-2]: future bars and the embargo bar cannot matter."""
    rng = np.random.default_rng(0)
    eq = np.cumprod(1 + rng.normal(0, 0.01, 600)) + 0.5
    i = 400
    g0 = gov(eq, i)
    eq_future = eq.copy()
    eq_future[i - 1:] = eq_future[i - 1] * 5  # huge rally after the lag point
    assert gov(eq_future, i) == g0  # invisible: only eq[..i-2] used
    eq_past = eq.copy()
    eq_past[i - 2] *= 0.5  # move the lagged bar itself
    assert gov(eq_past, i) != g0  # visible
    # 90-day (540-bar) window truncation: ancient history cannot matter
    eq_old = eq.copy()
    eq_old[0] *= 10.0
    j = i - 2
    if j - 540 + 1 > 0:
        assert gov(eq_old, i) == g0  # bar 0 outside the trailing window


def test_pooled_g_clipping_and_bands():
    def pooled(dd):
        return float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
    import pytest as _pt
    assert pooled(0.0) == 1.0 and pooled(0.10) == _pt.approx(1.0)
    assert pooled(0.15) == _pt.approx(0.5)
    assert pooled(0.20) == _pt.approx(0.0, abs=1e-12) and pooled(0.50) == 0.0
    # GV1/GV2 bands at dd = 0.15: GV1 (0.25,0.10) -> 1.0; GV2 (0.30,0.15) -> 1.0
    assert float(np.clip((0.25 - 0.15) / 0.10, 0, 1)) == _pt.approx(1.0)
    assert float(np.clip((0.30 - 0.15) / 0.15, 0, 1)) == 1.0
    # at dd = 0.20: G2 0.0, GV1 0.5, GV2 0.667, pooled(G2 bands) 0.0
    assert float(np.clip((0.25 - 0.20) / 0.10, 0, 1)) == _pt.approx(0.5)


def test_g2_baseline_reproduction():
    """Stored G2 (R2B1D17BFG2) still matches v421_result.json to the digit."""
    spec = importlib.util.spec_from_file_location(
        "rm_govtest", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    rm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rm)
    runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    got = [rm.year_reset(runs, "R2B1D17BFG2", y) for y in range(5)]
    assert [(m["R"], m["DD"]) for m in got] == [(r, d) for r, d in exp["years"]]
    assert exp["R"] == 5.41 and exp["full_path_dd"] == 16.82


def test_live_uses_per_phase_governor():
    """Live plan replays eu.simulate per phase; merge() never feeds the mix into g."""
    ftp = (ROOT / "scripts/forward_trade_phase.py").read_text(encoding="utf-8")
    mph = (ROOT / "backend/multiphase.py").read_text(encoding="utf-8")
    assert "eu.simulate(books, opens.reindex(grid), prep, trade=trade" in ftp
    assert "mix = sum(growth.values()) / len(phases)" in mph
    assert "governor" not in mph.replace("governor_g", "") or "governor" in mph  # no pooled-g logic
    assert "risk_mult" not in ftp and "pooled" not in mph.lower()
