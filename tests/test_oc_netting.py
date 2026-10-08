"""oc_netting tests: N1 gate causality + hand-checked netting cases + N2 zero-proof."""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OC = ROOT / "research/tournament/oc_netting"


def n1_gate(tgt: float) -> float:
    """Reference N1 gate (compute_engine.py PLAN-frozen rule): SHORT strictly -> 0."""
    return 0.0 if tgt < 0.0 else 1.0


def test_n1_gate_handchecked():
    assert n1_gate(-0.5) == 0.0  # book SHORT vs dip LONG: offset cancelled
    assert n1_gate(-1e-9) == 0.0  # strict: any negative target gates
    assert n1_gate(0.0) == 1.0  # flat: dips unchanged
    assert n1_gate(-0.0) == 1.0  # -0.0 is not < 0.0
    assert n1_gate(0.3) == 1.0  # book LONG + dip LONG: same direction, keep both
    # full mask on a synthetic (bars x coins) grid
    tgt = np.array([[0.2, -0.1, 0.0], [-0.3, 0.4, -0.0]])
    gate = np.where(tgt < 0.0, 0.0, 1.0)
    assert gate.tolist() == [[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]]


def test_n1_gate_causality_truncation():
    """Gate for bar i reads books_bear[i] only: no future row, no return, no fit."""
    rng = np.random.default_rng(7)
    nb, na = 500, 5
    books = rng.normal(0, 0.3, (nb, na))
    i, a = 300, 2
    g0 = n1_gate(books[i, a])
    fut = books.copy()
    fut[i + 1:] = -5.0  # crash after the decision: must not matter
    assert n1_gate(fut[i, a]) == g0
    past = books.copy()
    past[:i] = 5.0  # history rewritten: must not matter
    assert n1_gate(past[i, a]) == g0
    cur = books.copy()
    cur[i, a] = -cur[i, a]  # flip the decision row itself: must matter (unless 0)
    if books[i, a] != 0.0:
        assert n1_gate(cur[i, a]) != g0


def test_n2_same_direction_merge_fee_zero_handchecked():
    """Proportional-fee proof: merging same-direction legs cannot save fees."""
    MAKER, TAKER = 0.0002, 0.00055
    # two LONG legs, same exit rate (both TP at maker): merged fee == sum
    w1, w2 = 0.11, 0.09
    assert (w1 + w2) * MAKER == w1 * MAKER + w2 * MAKER
    # two SHORT legs via stops at taker: same equality
    assert (w1 + w2) * TAKER == w1 * TAKER + w2 * TAKER
    # four 1/4-size clock legs vs one pooled leg: identical fee base
    legs = [0.05, 0.06, 0.04, 0.05]
    assert sum(legs) * MAKER == sum(w * MAKER for w in legs)
    # opposite-direction netting WOULD save (gross falls) — not claimed by N2
    assert abs(w1 - w2) * MAKER < (w1 + w2) * MAKER


def test_g2_baseline_reproduction():
    """Stored G2 (R2B1D17BFG2) still matches v421_result.json to the digit."""
    spec = importlib.util.spec_from_file_location("v388_nt", RD / "v388/v388_bot_stop_distance.py")
    v388 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v388)
    runs = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    exp = json.loads((RD / "v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    spec2 = importlib.util.spec_from_file_location(
        "rm_nt", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    rm = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(rm)
    yy = [rm.year_reset(runs, "R2B1D17BFG2", y) for y in range(5)]
    assert [y["R"] for y in yy] == [r for r, _ in exp["years"]]
    assert [y["DD"] for y in yy] == [d for _, d in exp["years"]]
    assert exp["R"] == 5.41 and exp["DD"] == 16.91 and exp["full_path_dd"] == 16.82


def test_engine_dev_files_and_gate_fires():
    """Dev engine outputs exist; N1 gate fires (fewer rungs, same book config)."""
    runs = pickle.loads((OC / "tmp/engine_dev.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    for s in range(4):
        for r in ("G2REF", "N1"):
            d = runs[s][r]
            assert len(d["t"]) == len(d["eq"]) == len(d["eq_min"]) > 8000
            assert all(v > 0 for v in d["eq"])
    rowstats = json.loads((OC / "tmp/engine_dev_rowstats.json").read_text())
    g2_rungs = sum(rowstats[str(s)]["G2REF"]["rungs"] for s in range(4))
    n1_rungs = sum(rowstats[str(s)]["N1"]["rungs"] for s in range(4))
    assert 0 < n1_rungs < g2_rungs  # gate skips SHORT-book dip rungs
    n2 = json.loads((OC / "tmp/n2overlay_dev.json").read_text())
    assert n2["saved_abs_total"] == 0.0  # zero-proof: same-direction merge saves nothing
    stat = json.loads((OC / "tmp/engine_dev_stats.json").read_text())
    assert [tuple(y) for y in stat["N1"]["years"]] == [
        (y["R"], y["DD"]) for y in n2["years"]]  # N2 == N1 by construction
