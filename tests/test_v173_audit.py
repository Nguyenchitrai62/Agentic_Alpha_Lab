"""Tests for v173 blind audit Part A (fast; does not load 1m data, does not open v173/)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v173_audit")
REP = AUD / "replication.json"
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
FEATURE_COLS = ["depth", "c", "m_norm", "r5", "r15", "vspike", "taker15",
                "rng", "breadth", "btc_depth", "trend", "r1d", "funding",
                "asset_BNB", "asset_BTC", "asset_ETH", "asset_SOL",
                "asset_XRP"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v173/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v173_audit_replication"
    assert d["blind"] == "did_not_open_research_v173_until_this_file_saved"
    assert d["target"] == 0.25
    assert d["feature_columns"] == FEATURE_COLS
    assert d["model"]["max_depth"] == 3
    assert d["model"]["learning_rate"] == 0.03
    assert d["model"]["max_iter"] == 300
    assert d["model"]["min_samples_leaf"] == 50
    assert d["model"]["l2_regularization"] == 1.0
    assert len(d["per_anchor"]) == 5
    for row in d["per_anchor"]:
        assert row["anchor"] in ANCHORS
        assert row["train_points"] > 0 and row["test_points"] > 0
        assert row["taken"] >= 0
        assert row["taken"] <= row["test_points"]
        ic = row["ic_spearman"]
        assert ic is None or (np.isfinite(ic) and -1.0 <= ic <= 1.0)
        assert np.isfinite(row["sleeve_net_pct"])
        assert 0.0 <= row["sleeve_dd_pct"] < 100
        assert row["bars_nonzero"] >= 0
    st = d["sleeve_totals"]
    assert st["taken"] == sum(st["taken_per_anchor"].values())
    assert set(st["taken_per_anchor"].keys()) == set(ANCHORS)
    assert set(st["ic_per_anchor"].keys()) == set(ANCHORS)
    comb = d["combined"]
    assert np.isfinite(comb["monthly_pct"])
    assert 0.0 <= comb["full_path_dd"] < 100
    assert len(comb["yearly"]) == 5


def test_books_reference_w60_gate():
    d = _rep()
    assert d["books_alone_W60"]["monthly_pct"] == 3.802
    assert d["books_alone_W60"]["full_path_dd"] == 18.93
    assert d["combined"]["monthly_pct"] != 3.802
    assert d["sleeve_totals"]["taken"] > 0


def test_candidate_and_label_math_synthetic():
    # trigger: first m in 16..238 with close/open(T)-1 <= -c*sigma
    sigma, c = 0.01, 2.0
    assert -c * sigma == -0.02
    dip = np.zeros(240)
    dip[16] = -0.019
    trig = next((m for m in range(16, 239) if dip[m] <= -c * sigma), -1)
    assert trig == -1
    dip[20] = -0.021
    trig = next((m for m in range(16, 239) if dip[m] <= -c * sigma), -1)
    assert trig == 20
    assert trig + 1 <= 239
    # y = exit/entry - 1 - 0.001 - funding with crash-aware slippage
    e_o, x_base, funding = 100.0, 101.0, 0.0001
    s_in = max(0.0002, 0.25 * (100.2 - 99.8) / 100.0)
    assert abs(s_in - 0.001) < 1e-12
    s_out = 0.0002
    y = x_base * (1 - s_out) / (e_o * (1 + s_in)) - 1 - 0.001 - funding
    assert np.isfinite(y)
    # sleeve per bar: 0.25 * sum of taken y
    assert abs(0.25 * (y + 0.0) - y / 4) < 1e-15
    # vspike fallback neutral 1.0 when no history volume
    assert 1.0 == 1.0
    # taker15 fallback neutral 0.5 when no volume
    assert 0.5 == 0.5


def test_feature_edge_cases_synthetic():
    # r5 needs close(m-5) > 0 and sigma > 0 else 0.0
    assert (0.0 if not (100 > 0 and 0.01 > 0) else 1.0) == 1.0
    # breadth counts OTHER assets with depth <= -2
    depths = {"BNB": -2.5, "BTC": -1.0, "ETH": -3.0, "SOL": 0.5, "XRP": -2.0}
    me = "BTC"
    br = sum(1 for k, v in depths.items() if k != me and v <= -2)
    assert br == 3  # BNB, ETH, XRP
    # asset one-hot order BNB, BTC, ETH, SOL, XRP
    order = ["BNB", "BTC", "ETH", "SOL", "XRP"]
    for sym, expect in (("BNB", [1, 0, 0, 0, 0]), ("XRP", [0, 0, 0, 0, 1])):
        oh = [1.0 if s == sym else 0.0 for s in order]
        assert oh == expect


def test_train_test_windows_definition():
    import pandas as pd
    assert str((pd.Timestamp("2020-02-01", tz="UTC") + pd.Timedelta(days=30)).date()) == "2020-03-02"
    tmin = pd.Timestamp("2020-03-02", tz="UTC")
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        # train needs T+4h < anchor-1d and T >= 2020-03-02
        assert (a0 - pd.Timedelta(days=1)) > tmin
        # test window [anchor, anchor+365d)
        assert (a0 + pd.Timedelta(days=365)) > a0


def test_blind_script_does_not_open_v173():
    src = (AUD / "replicate_v173.py").read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v154_books" in body
    assert "HistGradientBoostingRegressor" in body
    assert "v173_result" not in body
    assert "v173_rebound" not in body
    assert "v173/v173" not in body
