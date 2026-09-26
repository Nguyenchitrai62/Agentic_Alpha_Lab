"""Tests for v145 blind audit (Part A). No leader v145 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v145_audit")
REP = AUD / "replication.json"
SCENS = ("normal", "fee_stress", "execution_stress")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v145/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v145_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["live"]["days"] == 1825
    assert d["live"]["union_bars"] == 10950
    assert set(d["scenarios"].keys()) == set(SCENS)
    for sc in SCENS:
        r = d["scenarios"][sc]
        assert len(r["yearly"]) == 5
        for y in r["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0 and y["months"] == 12.0
        assert 0.0 <= r["full_path_dd"] < 100
        assert np.isfinite(r["monthly_pct"])
    assert len(d["anchors_v92"]) == 5
    assert len(d["anchors_v94"]) == 5
    assert len(d["anchors_v103"]) == 5
    # extended lists: v114 26+40=66, v103 36+60=96
    assert d["feats114x_n"] == 66
    assert d["feats103x_n"] == 96
    assert len(d["xs_spec"]["xs_v114"]) == 20
    assert len(d["xs_spec"]["xs_v103"]) == 30
    for c in ("asset", "rib"):
        assert c not in d["xs_spec"]["xs_v114"]
        assert c not in d["xs_spec"]["xs_v103"]
    assert not any(c.startswith("btc_") for c in d["xs_spec"]["xs_v114"])
    assert not any(c.startswith("btc_") for c in d["xs_spec"]["xs_v103"])
    # every xs col has xs_ and xr_ features
    for c in d["xs_spec"]["xs_v114"]:
        assert f"xs_{c}" in d["feats114x"] and f"xr_{c}" in d["feats103x"] or f"xs_{c}" in d["feats114x"]
    for c in d["xs_spec"]["xs_v103"]:
        assert f"xs_{c}" in d["feats103x"] and f"xr_{c}" in d["feats103x"]


def test_literal_pipeline_and_pvol_guards():
    d = _rep()
    assert d["scenarios_spec"]["normal"] == {"fee": 0.0002, "slip": 0.0, "target": 0.15, "governed": False}
    assert d["scenarios_spec"]["fee_stress"]["fee"] == 0.0006
    assert d["scenarios_spec"]["execution_stress"]["slip"] == 0.0005
    # pvol base must match audited v129 rows exactly (original sets)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    assert d["n_replaced"]["v114_lo"] > 50000
    src = (AUD / "replicate_v145.py").read_text()
    assert "rank(pct=True)" in src and "xs_" in src
    assert "0.0006" in src and "0.0005" in src
    assert "TARGET = 0.15" in src or "target" in src.lower()
    assert "v145_result.json" not in src
    assert "v145_xs_all_features" not in src
    assert "import v145" not in src and "import v142" not in src and "import v141" not in src


def test_xs_xr_causality_synthetic():
    df = pd.DataFrame({"t": [1, 1, 1, 2, 2, 2], "c": [1.0, 2.0, 3.0, 5.0, 5.0, 5.0]})
    df["xs"] = df["c"] - df.groupby("t")["c"].transform("mean")
    df["xr"] = df.groupby("t")["c"].transform(lambda s: s.rank(pct=True))
    assert abs(df[df.t == 1]["xs"].sum()) < 1e-12
    assert ((df["xr"] > 0) & (df["xr"] <= 1.0)).all()
    d = _rep()
    assert np.isfinite(d["scenarios"]["normal"]["monthly_pct"])
