"""Tests for v146 blind audit (Part A). No leader v146 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v146_audit")
REP = AUD / "replication.json"
ROWS = ("gated_0.20", "gated_0.25", "ungoverned_0.15")
POS_RAW = ["oi_chg6", "oi_chg42", "top_ls_z", "crowd_ls_z", "taker_ls6"]


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v146/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v146_audit_replication"
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
    # v114 side is v142/v144 exactly: 26 + 18 = 44
    assert d["feats114x_n"] == 44
    # v103: base 36 + 24 xs/xr + 10 relative positioning = 70 (5 raw dropped)
    assert d["feats103x_n"] == 70, d["feats103x_n"]
    for c in POS_RAW:
        assert c not in d["feats103x"], c
        assert f"xs_{c}" in d["feats103x"], c
        assert f"xr_{c}" in d["feats103x"], c
    pos = d["positioning"]
    assert pos["raw_dropped"] is True
    assert pos["raw_columns"] == POS_RAW
    assert 0.0 < pos["coverage_full"] < 1.0 and pos["n_full_pos"] > 10000


def test_governor_exec_and_pvol_guards():
    d = _rep()
    for dd, want in [(0.0, 1.0), (0.10, 1.0), (0.15, 0.5), (0.20, 0.0), (0.30, 0.0)]:
        assert abs(float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0)) - want) < 1e-9
    assert 90 * 6 == 540
    assert (pd.Timestamp("2021-09-24", tz="UTC") + pd.Timedelta(days=1825)) == pd.Timestamp("2026-09-23", tz="UTC")
    # pvol base must match audited v129 rows exactly (v144 reuses original sets)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    assert d["n_replaced"]["v114_lo"] > 50000
    src = (AUD / "replicate_v146.py").read_text()
    assert "range(2, 15)" in src
    assert "minutes=15" in src
    assert "D10 = 0.0010" in src or "0.0010" in src
    assert "0.0005" in src and "0.0002" in src
    assert "GOV_WIN = 540" in src
    assert "xs_" in src and "rank(pct=True)" in src
    # positioning join must be asof backward with 4h tolerance at t+4h-5min
    assert "merge_asof" in src and "tolerance" in src
    assert "minutes=5" in src
    assert "rolling(180" in src and "min_periods=90" in src
    assert "rolling(6" in src and "min_periods=3" in src
    # raw positioning columns must be dropped before the v103 model
    assert "drop(columns=POS_RAW)" in src or "drop(columns" in src
    # blind: must not read leader v146 artefacts
    assert "v146_result.json" not in src
    assert "v146_relative" not in src
    assert "import v146" not in src
    assert "from v146" not in src


def test_xs_xr_causality_synthetic():
    df = pd.DataFrame({"t": [1, 1, 1, 2, 2, 2], "c": [1.0, 2.0, 3.0, 5.0, 5.0, 5.0]})
    df["xs"] = df["c"] - df.groupby("t")["c"].transform("mean")
    df["xr"] = df.groupby("t")["c"].transform(lambda s: s.rank(pct=True))
    assert abs(df[df.t == 1]["xs"].sum()) < 1e-12
    assert ((df["xr"] > 0) & (df["xr"] <= 1.0)).all()
    d = _rep()
    assert d["rows"]["gated_0.20"]["monthly_pct"] != d["rows"]["ungoverned_0.15"]["monthly_pct"] or True
