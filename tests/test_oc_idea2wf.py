"""Tests for oc_idea2wf (fast: artifact consistency + decision rule + synthetic)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_idea2wf"
IDEA2 = ROOT / "research" / "tournament" / "oc_idea2"
sys.path.insert(0, str(HERE))
from analyze_idea2wf import ANCHOR_ISO, CUTOFFS, outcome_m


def _res():
    return json.loads((HERE / "results.json").read_text())


def _choice():
    return json.loads((HERE / "choice.json").read_text())


def test_choice_format_and_sign_rule():
    ch = _choice()
    res = _res()
    assert list(ch.keys()) == ANCHOR_ISO
    for a in ANCHOR_ISO:
        assert set(ch[a].keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
        for sym, m in ch[a].items():
            assert m in (4.0, 5.5)
            tr = res["train"][a][sym]
            assert tr["choice"] == m
            assert (m == 5.5) == (tr["sum_V_minus_U"] > 0)
    # registered-engine shape: exactly {anchor_iso: {SYMBOL: m}}
    assert res["choice"] == ch


def test_anchors_are_literal_365d():
    import pandas as pd
    a0 = pd.Timestamp("2021-09-24", tz="UTC")
    assert ANCHOR_ISO == [(a0 + pd.Timedelta(days=365 * k)).date().isoformat() for k in range(5)]
    assert ANCHOR_ISO == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-23", "2025-09-23"]


def test_cutoffs_are_anchor_minus_7d():
    import pandas as pd
    for k, a in enumerate(ANCHOR_ISO):
        assert CUTOFFS[k] == pd.Timestamp(a, tz="UTC") - pd.Timedelta(days=7)


def test_decision_rule_math():
    res = _res()
    U = [r["sum"] for r in res["per_year"]["U"]]
    W = [r["sum"] for r in res["per_year"]["WF"]]
    D = [round(w - u, 6) for u, w in zip(U, W)]
    assert res["D_WF_minus_U"] == D
    assert res["years_positive"] == sum(v > 0 for v in D)
    loo = res["loo_mean_D"]
    assert len(loo) == 5
    Draw = [w - u for u, w in zip(U, W)]
    for i in range(5):
        assert loo[i] == round(float(np.mean([Draw[j] for j in range(5) if j != i])), 6)
    assert res["loo_positive"] == sum(v > 0 for v in loo)
    wdU = [r["worst_day"] for r in res["per_year"]["U"]]
    wdW = [r["worst_day"] for r in res["per_year"]["WF"]]
    assert res["worst_day_not_worse_per_year"] == [bool(b >= a) for a, b in zip(wdU, wdW)]
    assert res["worst_day_not_worse_count"] == sum(res["worst_day_not_worse_per_year"])
    assert res["promising"] == (res["years_positive"] >= 4 and res["loo_positive"] >= 4
                                and res["worst_day_not_worse_count"] >= 4)
    assert res["verdict"].startswith("PROMISING") == res["promising"]
    # this realization: 5/5 years, LOO 5/5, worst-day 1/5 -> NOT PROMISING
    assert res["years_positive"] == 5 and res["loo_positive"] == 5
    assert res["worst_day_not_worse_count"] == 1
    assert res["promising"] is False
    assert res["verdict"].startswith("NOT PROMISING")


def test_uniform_reproduces_idea2_on_shared_windows():
    res = _res()
    d2 = json.loads((IDEA2 / "results.json").read_text())
    # anchors 0..2 windows coincide exactly; 3..4 shift 1 day (leap) by design
    for yi in range(3):
        assert abs(res["per_year"]["U"][yi]["sum"] - d2["per_year"]["U"][yi]["sum"]) < 1e-9
        assert res["per_year"]["U"][yi]["n"] == d2["per_year"]["U"][yi]["n"]


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    C = np.full(n, o)
    return O, H, Lw, C


def test_wider_stop_avoids_close_stop_hit():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl4 = lv * (1 - 4 * sg)
    C[29] = sl4 - 0.01
    assert (29 + 1) % 5 == 0
    O[30] = 95.0
    r4, x4, h4 = outcome_m(H, Lw, C, O, f, lv, sg, 4.0, 101.0, False)
    r55, x55, h55 = outcome_m(H, Lw, C, O, f, lv, sg, 5.5, 101.0, False)
    assert h4 == "stop" and x4 == 30
    assert h55 == "time"
    assert r55 > r4


def test_stop_first_kept_with_wide_stop():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[29] = tp + 0.01
    C[29] = lv * (1 - 5.5 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = outcome_m(H, Lw, C, O, f, lv, sg, 5.5, 99.0, False)
    assert how == "stop"
