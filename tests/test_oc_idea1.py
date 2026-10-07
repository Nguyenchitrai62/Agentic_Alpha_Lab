"""Tests for oc_idea1 (fast: artifact consistency + decision rule + synthetic)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_idea1"


def test_join_is_complete_and_f_n_in_range():
    n = pd.read_parquet(Path(__file__).resolve().parents[1]
                        / "research" / "tournament" / "oc_b1shape" / "fills_n.parquet")
    ext = pd.read_parquet(Path(__file__).resolve().parents[1]
                          / "research" / "tournament" / "ext" / "fills_U_ext.parquet")
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    r2 = (2.5, 3.0, 3.5, 4.0, 5.0)
    m = ext[ext["sym"].isin(majors) & ext["x1"].isin(r2)]
    assert len(n) == len(m)  # reuse covers the full majors-R2 universe
    assert n["n25"].between(0, 4).all()
    assert m["f"].between(16, 238).all()
    res = json.loads((HERE / "results.json").read_text())
    assert res["late_threshold"] == 209
    assert res["n_fills_5y"] == 5498


def test_bucket_counts_add_up():
    res = json.loads((HERE / "results.json").read_text())
    for year, row in res["bucket_means"].items():
        if year == "overall":
            continue
        assert row["early"]["n"] + row["late"]["n"] == res["fills_per_year"][year]
        for b in ("early", "late"):
            assert abs(row[b]["mean_y10"]) < 0.05
    assert res["bucket_means"]["overall"]["early"]["n"] + res["bucket_means"]["overall"]["late"]["n"] == 5498


def test_rule_math_and_decision_rule():
    res = json.loads((HERE / "results.json").read_text())
    a = res["rules"]["always1.0"]["yearly_S"]
    b = res["rules"]["tp05_if_late"]["yearly_S"]
    assert res["D_tp05_if_late_minus_always10"] == [round(x - y, 4) for x, y in zip(b, a)]
    d = res["D_tp05_if_late_minus_always10"]
    assert res["years_positive"] == sum(v > 0 for v in d)
    loo = res["loo_mean_D"]
    assert len(loo) == 5
    for i in range(5):
        assert loo[i] == round(float(np.mean([d[j] for j in range(5) if j != i])), 4)
    assert res["loo_positive"] == sum(v > 0 for v in loo)
    wdA = res["rules"]["always1.0"]["worst_day_per_year"]
    wdB = res["rules"]["tp05_if_late"]["worst_day_per_year"]
    assert res["worst_day_not_worse_per_year"] == [bool(x >= y) for x, y in zip(wdB, wdA)]
    assert res["worst_day_not_worse_count"] == sum(res["worst_day_not_worse_per_year"])
    assert res["promising"] == (res["years_positive"] >= 4 and res["loo_positive"] >= 4
                                and res["worst_day_not_worse_count"] >= 4)
    assert res["verdict"].startswith("PROMISING") == res["promising"]
    # this realization: 1/5 years positive, LOO 0/5, worst-day 4/5 -> NOT promising
    assert res["years_positive"] == 1 and res["loo_positive"] == 0
    assert res["worst_day_not_worse_count"] == 4
    assert res["promising"] is False


def test_tp_rule_and_weights_synthetic():
    f = np.array([16, 208, 209, 238])
    y05 = np.array([0.01, 0.02, 0.03, 0.04])
    y10 = np.array([0.05, 0.06, 0.07, 0.08])
    yB = np.where(f >= 209, y05, y10)
    assert list(yB) == [0.05, 0.06, 0.03, 0.04]
    w = np.array([1.0, 0.5, 1 / 3, 0.2])
    wp = w / w.mean()
    assert abs(wp.mean() - 1.0) < 1e-12
