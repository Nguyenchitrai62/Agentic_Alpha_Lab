"""Tests for oc_tpbyn (fast: artifact consistency + decision rule + synthetic)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_tpbyn"


def test_join_is_complete_and_n_in_range():
    n = pd.read_parquet(Path(__file__).resolve().parents[1]
                        / "research" / "tournament" / "oc_b1shape" / "fills_n.parquet")
    ext = pd.read_parquet(Path(__file__).resolve().parents[1]
                          / "research" / "tournament" / "ext" / "fills_U_ext.parquet")
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    r2 = (2.5, 3.0, 3.5, 4.0, 5.0)
    m = ext[ext["sym"].isin(majors) & ext["x1"].isin(r2)]
    assert len(n) == len(m)  # reuse covers the full majors-R2 universe
    assert n["n25"].between(0, 4).all()


def test_bucket_counts_add_up_and_means_ordered():
    res = json.loads((HERE / "results.json").read_text())
    assert res["n_fills_5y"] == 5498
    for year, row in res["bucket_means"].items():
        if year == "overall":
            continue
        assert sum(row[b]["n"] for b in ("0", "1", "2+")) == res["fills_per_year"][year]
        # y1.0 means are finite and within +-5% per rung (sanity bound)
        for b in ("0", "1", "2+"):
            assert abs(row[b]["mean_y10"]) < 0.05


def test_rule_math_and_decision_rule():
    res = json.loads((HERE / "results.json").read_text())
    a = res["rules"]["always1.0"]["yearly_S"]
    b = res["rules"]["tp15_if_n2"]["yearly_S"]
    assert res["D_tp15_if_n2_minus_always10"] == [round(x - y, 4) for x, y in zip(b, a)]
    d = res["D_tp15_if_n2_minus_always10"]
    assert res["years_positive"] == sum(v > 0 for v in d)
    loo = res["loo_mean_D"]
    assert len(loo) == 5
    for i in range(5):
        assert loo[i] == round(float(np.mean([d[j] for j in range(5) if j != i])), 4)
    assert res["loo_positive"] == sum(v > 0 for v in loo)
    assert res["promising"] == (res["years_positive"] >= 4 and res["loo_positive"] >= 4)
    assert res["verdict"].startswith("PROMISING") == res["promising"]
    # this realization: 3/5 years positive, LOO 5/5 -> NOT promising
    assert res["years_positive"] == 3 and res["loo_positive"] == 5
    assert res["promising"] is False


def test_equal_exposure_weights_synthetic():
    w = np.array([1.0, 0.5, 1 / 3])
    wp = w / w.mean()
    assert abs(wp.mean() - 1.0) < 1e-12
    y = np.array([0.01, 0.02, 0.03])
    assert abs(float((wp * y).sum()) - float((w / w.mean() * y).sum())) < 1e-12
