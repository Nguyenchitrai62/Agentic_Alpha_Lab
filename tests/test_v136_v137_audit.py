"""Tests for v136+v137 blind audit (Part A). No leader v136/v137 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v136_v137_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v136/ or v137/ folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v136_v137_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    v136 = d["v136"]
    assert set(v136["scenarios"].keys()) == {"normal", "fee_stress", "execution_stress"}
    for sc in ("normal", "fee_stress", "execution_stress"):
        r = v136["scenarios"][sc]
        assert len(r["yearly"]) == 5
        for y in r["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0 and y["months"] == 12.0
        assert 0.0 <= r["full_path_dd"] < 100 and np.isfinite(r["monthly_pct"])
    assert v136["feats114_n"] == 26 and v136["feats103_n"] == 36
    assert v136["union_bars"] > 10000
    for k in ("v92", "v94_h18", "v94_h42", "v94_h84", "v103_h6", "v103_h18"):
        assert k in v136["kept_counts"], k
        assert len(v136["kept_counts"][k]) == 5, k
        for n in v136["kept_counts"][k]:
            assert 5 <= n <= 36, (k, n)
    v137 = d["v137"]
    assert v137["d_bps"] == 10
    assert set(v137["per_target"].keys()) == {"0.15", "0.17", "0.19", "0.21"}
    for t, r in v137["per_target"].items():
        assert len(r["yearly"]) == 5, t
        for y in r["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0
        assert 0.0 <= r["full_path_dd"] < 100 and np.isfinite(r["monthly_pct"])
        assert 0.0 <= r["maker_fill_rate"] <= 1.0
        h = r["hidden_year"]
        for kk in ("net_pct", "max_drawdown_percent", "maker_fill_rate",
                   "orders_hidden_year", "fills_hidden_year"):
            assert kk in h, (t, kk)
    assert v137["union_bars"] > 10000


def test_pvol_matches_v129_and_target015_equals_v135_10bps():
    d = _rep()
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    v135 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v135_audit/replication.json").read_text())
    ref = v135["offsets"]["10"]
    got = d["v137"]["per_target"]["0.15"]
    assert abs(got["monthly_pct"] - ref["monthly_pct"]) < 1e-9
    assert abs(got["full_path_dd"] - ref["full_path_dd"]) < 1e-9
    for yg, yr in zip(got["yearly"], ref["yearly"]):
        assert abs(yg["net_pct"] - yr["net_pct"]) < 1e-9
        assert abs(yg["max_drawdown_percent"] - yr["max_drawdown_percent"]) < 1e-9
    assert abs(got["hidden_year"]["net_pct"] - ref["hidden_year"]["net_pct"]) < 1e-9
    assert got["hidden_year"]["orders_hidden_year"] == ref["hidden_year"]["orders_hidden_year"]
    assert d["v137"]["n_replaced"]["v114_lo"] > 50000


def test_selection_guards_in_code():
    src = (AUD / "replicate_v136_v137.py").read_text()
    assert "permutation_importance" in src
    assert "make_scorer" in src
    assert "sample(20000, random_state=0)" in src
    assert "n_repeats=3" in src and "random_state=0" in src
    assert "Timedelta(days=730)" in src
    assert "range(2, 15)" in src
    assert "minutes=15" in src
    assert "0.0005" in src and "0.0002" in src
    assert "v136_result.json" not in src and "v137_result.json" not in src
    assert "import v136" not in src and "import v137" not in src
    assert "from v136" not in src and "from v137" not in src
