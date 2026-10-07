"""Tests for oc_idiocap (fast: synthetic trigger logic + artifact consistency)."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "research/tournament/oc_idiocap"


def trig(n: int, x0: float, x4: float) -> bool:
    import math

    if n != 0:
        return False
    if not (math.isfinite(x0) and math.isfinite(x4)):
        return False
    return (x4 > -1.0) and (x0 < -4.0)


def test_trigger_boundaries_and_nan_guard():
    assert trig(0, -4.5, 0.0) is True
    assert trig(1, -9.0, 5.0) is False  # n != 0 never capped
    assert trig(0, -4.0, 0.0) is False  # strict < -4
    assert trig(0, -4.0001, -1.0) is False  # strict > -1
    assert trig(0, float("nan"), 0.0) is False
    assert trig(0, -5.0, float("nan")) is False


def test_results_consistency_and_decision_rule():
    res = json.loads((HERE / "results.json").read_text())
    vs = res["variants"]
    assert set(vs) == {"B0_plain", "C1_idio05", "C3_idio07"}
    b = vs["B0_plain"]
    assert res["n_rows_5y"] == 5498 == sum(b["n_fills_per_year"])
    for name, v in vs.items():
        assert len(v["yearly_S"]) == 5
        assert len(v["worst_day_per_year"]) == 5 and len(v["maxDD_per_year"]) == 5
    # B0 reproduces the oc_b1shape S1 yearly sums (same weights/universe)
    import math

    ref = [3.9546, 0.2905, 5.7374, 3.9523, 1.2367]
    for a, c in zip(b["yearly_S"], ref):
        assert math.isclose(a, c, abs_tol=1e-3), (a, c)
    for name in ("C1_idio05", "C3_idio07"):
        v, d = vs[name], res["decisions"][name]
        wd = [a > c for a, c in zip(v["worst_day_per_year"], b["worst_day_per_year"])]
        dd = [a > c for a, c in zip(v["maxDD_per_year"], b["maxDD_per_year"])]
        kp = [(a >= 0.95 * c) if c > 0 else (a >= c) for a, c in zip(v["yearly_S"], b["yearly_S"])]
        assert d["wd_improve"] == wd and d["dd_improve"] == dd and d["keep95"] == kp
        assert d["promising"] == (sum(wd) >= 4 and sum(dd) >= 4 and sum(kp) >= 4)
        assert d["promising"] is False  # both fail on this data
    # trigger counts identical across capped variants, zero in 2025
    assert vs["C1_idio05"]["n_trig_per_year"] == vs["C3_idio07"]["n_trig_per_year"]
    assert vs["C1_idio05"]["n_trig_per_year"][-1] == 0
    assert sum(vs["C1_idio05"]["n_trig_per_year"]) == 29
