"""Tests for oc_idea2 (fast: artifact consistency + decision rule + synthetic)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_idea2"
sys.path.insert(0, str(HERE))
from analyze_idea2 import outcome_m


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_uniform_reproduces_d0_and_counts():
    res = _res()
    d0 = json.loads((ROOT / "research" / "tournament" / "oc_dipexit" / "results.json").read_text())
    assert res["n_rungs"] == 5498 == d0["n_rungs"]
    assert res["config"]["uniform_vs_D0_max_abs_sum_diff"] == 0.0
    for yi in range(5):
        assert abs(res["per_year"]["U"][yi]["sum"] - d0["per_year"]["D0"][yi]["sum"]) < 1e-9
        assert res["per_year"]["U"][yi]["n"] == d0["per_year"]["D0"][yi]["n"]
    assert res["fills_per_coin"] == d0["fills_per_coin"]


def test_decision_rule_math():
    res = _res()
    U = [r["sum"] for r in res["per_year"]["U"]]
    V = [r["sum"] for r in res["per_year"]["V"]]
    D = [round(v - u, 6) for u, v in zip(U, V)]
    assert res["D_V_minus_U"] == D
    assert res["years_positive"] == sum(v > 0 for v in D)
    loo = res["loo_mean_D"]
    assert len(loo) == 5
    for i in range(5):
        assert loo[i] == round(float(np.mean([D[j] for j in range(5) if j != i])), 6)
    assert res["loo_positive"] == sum(v > 0 for v in loo)
    wdU = [r["worst_day"] for r in res["per_year"]["U"]]
    wdV = [r["worst_day"] for r in res["per_year"]["V"]]
    assert res["worst_day_not_worse_per_year"] == [bool(b >= a) for a, b in zip(wdU, wdV)]
    assert res["worst_day_not_worse_count"] == sum(res["worst_day_not_worse_per_year"])
    assert res["promising"] == (res["years_positive"] >= 4 and res["loo_positive"] >= 4
                                and res["worst_day_not_worse_count"] >= 4)
    assert res["verdict"].startswith("PROMISING") == res["promising"]
    # this realization: 4/5 years, LOO 5/5, worst-day 4/5 -> PROMISING
    assert res["years_positive"] == 4 and res["loo_positive"] == 5
    assert res["worst_day_not_worse_count"] == 4
    assert res["promising"] is True


def test_non_xrp_coincide_and_xrp_drives_effect():
    res = _res()
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"):
        for row in res["per_coin"][sym]:
            assert row["sum_U"] == row["sum_V"]
            assert row["stop_rate_U"] == row["stop_rate_V"]
    tot = round(sum(r["sum_V"] - r["sum_U"] for sym in res["per_coin"]
                    for r in res["per_coin"][sym]), 6)
    assert abs(tot - round(sum(res["D_V_minus_U"]), 6)) < 1e-6


def _flat(n=240, o=100.0):
    O = np.full(n, o)
    H = np.full(n, o)
    Lw = np.full(n, o)
    C = np.full(n, o)
    return O, H, Lw, C


def test_wider_stop_avoids_close_stop_hit():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    sl4 = lv * (1 - 4 * sg)  # 96.0
    C[29] = sl4 - 0.01  # clock minute below the 4sg stop
    assert (29 + 1) % 5 == 0
    O[30] = 95.0
    r4, x4, h4 = outcome_m(H, Lw, C, O, f, lv, sg, 4.0, 101.0, False)
    r55, x55, h55 = outcome_m(H, Lw, C, O, f, lv, sg, 5.5, 101.0, False)
    assert h4 == "stop" and x4 == 30  # exit at open(30)
    assert abs(r4 - (95.0 / lv - 1 - 0.0002 - 0.00055)) < 1e-12
    assert h55 == "time"  # 5.5sg sl = 94.5 < close 95.99... no fire
    assert r55 > r4


def test_stop_first_and_backstop_priority_kept_with_wide_stop():
    O, H, Lw, C = _flat()
    lv, sg, f = 100.0, 0.01, 20
    tp = lv * (1 + sg)
    H[29] = tp + 0.01
    C[29] = lv * (1 - 5.5 * sg) - 0.01
    assert (29 + 1) % 5 == 0
    _, _, how = outcome_m(H, Lw, C, O, f, lv, sg, 5.5, 99.0, False)
    assert how == "stop"  # same-minute TP loses to the stop
    Lw[25] = lv * (1 - 8 * sg) - 0.01
    H[25] = tp + 0.01
    _, x, how = outcome_m(H, Lw, C, O, f, lv, sg, 5.5, 99.0, False)
    assert how == "backstop" and x == 25
