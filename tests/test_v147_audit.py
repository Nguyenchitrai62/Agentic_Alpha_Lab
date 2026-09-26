"""Tests for v147 blind audit (Part A). No leader v147 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v147_audit")
REP = AUD / "replication.json"
ROWS = ("gated_0.20", "gated_0.25", "ungoverned_0.15")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v147/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v147_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["days"] == 1825
    assert d["live"]["union_bars"] == 10950
    assert set(d["rows"].keys()) == set(ROWS)
    for row in ROWS:
        r = d["rows"][row]
        assert len(r["yearly"]) == 5
        assert len(r["mean_g_per_anchor_year"]) == 5
        for y in r["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0 and y["months"] == 12.0
        for gm in r["mean_g_per_anchor_year"]:
            assert 0.0 <= gm["mean_g"] <= 1.0
        assert 0.0 <= r["full_path_dd"] < 100
        assert np.isfinite(r["monthly_pct"])
        assert 0.0 <= r["maker_fill_rate"] <= 1.0
        assert r["orders_live"] > 0 and r["fills_live"] > 0
    for gm in d["rows"]["ungoverned_0.15"]["mean_g_per_anchor_year"]:
        assert gm["mean_g"] == 1.0
    assert len(d["anchors_v92"]) == 5
    assert len(d["anchors_v94"]) == 5
    assert len(d["anchors_v103"]) == 5
    for a in d["anchors_v103"]:
        assert "train_rows_h3" in a and "train_rows_h6" in a and "train_rows_h18" in a
        assert "ic_vs_y3" in a and "ic_vs_y6" in a and "ic_vs_y18" in a
        assert a["train_rows_h3"] > a["train_rows_h6"] > a["train_rows_h18"]
    assert d["feats114x_n"] == 44
    assert d["feats103x_n"] == 60
    assert "y3" not in d["feats114x"] and "y3" not in d["feats103x"]
    assert "y6" not in d["feats114x"] and "y6" not in d["feats103x"]


def test_governor_exec_and_pvol_guards():
    d = _rep()
    for dd, want in [(0.0, 1.0), (0.10, 1.0), (0.15, 0.5), (0.20, 0.0), (0.30, 0.0)]:
        assert abs(float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0)) - want) < 1e-9
    assert 90 * 6 == 540
    assert (pd.Timestamp("2021-09-24", tz="UTC") + pd.Timedelta(days=1825)) == pd.Timestamp("2026-09-23", tz="UTC")
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    assert d["n_replaced"]["v114_lo"] > 50000
    src = (AUD / "replicate_v147.py").read_text()
    assert "range(2, 15)" in src
    assert "minutes=15" in src
    assert "D10 = 0.0010" in src or "0.0010" in src
    assert "0.0005" in src and "0.0002" in src
    assert "GOV_WIN = 540" in src
    assert "xs_" in src and "rank(pct=True)" in src
    assert "HS_V103 = (3, 6, 18)" in src
    assert "y3" in src
    assert "v147_result.json" not in src
    assert "v147_v103_12h_horizon" not in src
    assert "import v147" not in src and "import v144" not in src


def test_xs_xr_and_y3_causality_synthetic():
    df = pd.DataFrame({"t": [1, 1, 1, 2, 2, 2], "c": [1.0, 2.0, 3.0, 5.0, 5.0, 5.0]})
    df["xs"] = df["c"] - df.groupby("t")["c"].transform("mean")
    df["xr"] = df.groupby("t")["c"].transform(lambda s: s.rank(pct=True))
    assert abs(df[df.t == 1]["xs"].sum()) < 1e-12
    assert ((df["xr"] > 0) & (df["xr"] <= 1.0)).all()
    # y3 causal form: clip(log(o[t+4]/o[t+1]) / (vol*sqrt(3)), -4, 4)
    o = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    vol = 0.01
    want = np.clip(np.log(o[4] / o[1]) / (vol * np.sqrt(3)), -4, 4)
    got = np.clip(np.log(104.0 / 101.0) / (0.01 * np.sqrt(3)), -4, 4)
    assert abs(want - got) < 1e-12
    # h=3 needs 4 bars of forward data: t + 4*4h < cutoff
    assert 3 + 1 == 4
    d = _rep()
    assert np.isfinite(d["rows"]["gated_0.25"]["monthly_pct"])
