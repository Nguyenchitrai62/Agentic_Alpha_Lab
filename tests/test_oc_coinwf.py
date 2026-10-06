"""Tests for oc_coinwf (synthetic + embargo/causality; no outcome tuning)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_coinwf"))
from compute_coinwf import (ANCHORS, DEV_END, EMBARGO, HIST_START, MAJORS, R2,  # noqa: E402
                            load_main, weights_for_anchor)

RES = json.load(open(ROOT / "research" / "tournament" / "oc_coinwf" / "results.json"))
PER_YEAR = [990, 1045, 1330, 989, 1144]


def test_weight_formula_synthetic():
    hist = pd.DataFrame({
        "sym": ["BTCUSDT"] * 40 + ["ETHUSDT"] * 40 + ["SOLUSDT"] * 40
               + ["BNBUSDT"] * 40 + ["XRPUSDT"] * 40,
        "y1.0": ([0.01] * 20 + [0.0] * 20) + ([0.02] * 20 + [0.01] * 20)
                + ([0.02] * 20 + [-0.01] * 20) + ([0.015] * 20 + [0.0] * 20)
                + ([0.01] * 20 + [0.0] * 20),
    })
    w, scores, fallback, _ = weights_for_anchor(hist)
    assert not fallback
    assert abs(sum(w[c] for c in MAJORS) / 5 - 1.0) < 1e-12
    assert all(np.isfinite(w[c]) and w[c] > 0 for c in MAJORS)
    # ETH best score -> largest raw; SOL worst -> clipped floor region
    assert w["ETHUSDT"] > w["SOLUSDT"]
    # NaN-score coin gets 1.0 pre-renormalisation: single-row universe
    tiny = pd.DataFrame({"sym": ["BTCUSDT"], "y1.0": [0.01]})
    w2, _, fb2, _ = weights_for_anchor(tiny)
    assert fb2 and all(v == 1.0 for v in w2.values())


def test_fallback_nonpositive_mean():
    hist = pd.DataFrame({
        "sym": [c for c in MAJORS for _ in range(40)],
        "y1.0": [-0.01] * 200,
    })
    w, _, fallback, _ = weights_for_anchor(hist)
    assert fallback and all(v == 1.0 for v in w.values())


def test_universe_and_years():
    d = load_main()
    assert set(d.sym.unique()) <= set(MAJORS)
    assert set(d.x1.unique()) <= set(R2)
    assert ((d.f >= 16) & (d.f <= 238)).all()
    assert ((d["T"].dt.hour % 4 == 0) & (d["T"].dt.minute == 0)).all()
    assert (d.t_fill < DEV_END).all()
    for k, a0 in enumerate(ANCHORS):
        n = int(((d.t_fill >= a0) & (d.t_fill < a0 + pd.Timedelta(days=365))).sum())
        assert n == PER_YEAR[k]
    # disjoint years
    masks = [(d.t_fill >= a) & (d.t_fill < a + pd.Timedelta(days=365)) for a in ANCHORS]
    assert sum(int(m.sum()) for m in masks) == int(pd.concat(
        [d[m] for m in masks]).shape[0])


def test_history_embargo_and_recompute():
    d = load_main()
    for k, a0 in enumerate(ANCHORS):
        hist = d[(d.t_fill > HIST_START) & (d.t_fill < a0 - EMBARGO)]
        assert (hist.t_fill < a0 - EMBARGO).all()
        assert (hist.t_fill > HIST_START).all()
        te = d[(d.t_fill >= a0) & (d.t_fill < a0 + pd.Timedelta(days=365))]
        assert len(pd.merge(hist[["t_fill", "sym", "x1"]], te[["t_fill", "sym", "x1"]],
                            on=["t_fill", "sym", "x1"])) == 0
        w, _, _, _ = weights_for_anchor(hist)
        stored = RES["years"][k]["weights"]
        for c in MAJORS:
            assert abs(w[c] - stored[c]) < 1e-6
        assert abs(sum(stored[c] for c in MAJORS) / 5 - 1.0) < 1e-6


def test_no_peek():
    d = load_main()
    a0 = ANCHORS[2]
    hist = d[(d.t_fill > HIST_START) & (d.t_fill < a0 - EMBARGO)]
    w0, _, _, _ = weights_for_anchor(hist)
    d2 = d.copy()
    m = d2.t_fill >= a0 - EMBARGO
    d2.loc[m, "y1.0"] = 999.0
    hist2 = d2[(d2.t_fill > HIST_START) & (d2.t_fill < a0 - EMBARGO)]
    w2, _, _, _ = weights_for_anchor(hist2)
    for c in MAJORS:
        assert w0[c] == w2[c]


def test_winrate_equality_and_rule_counts():
    d = load_main()
    for k, a0 in enumerate(ANCHORS):
        te = d[(d.t_fill >= a0) & (d.t_fill < a0 + pd.Timedelta(days=365))]
        y = te["y1.0"].to_numpy(float)
        w = np.array([RES["years"][k]["weights"][c] for c in te.sym], float)
        assert ((w > 0).all())
        assert float(np.mean(y > 0)) == float(np.mean((w * y) > 0))
    assert RES["rule"]["pass_dd_years"] == sum(1 for r in RES["years"] if r["pass_dd"])
    assert RES["rule"]["pass_sum95_years"] == sum(1 for r in RES["years"] if r["pass_sum95"])
    assert RES["rule"]["promising"] is False
