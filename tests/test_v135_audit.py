"""Tests for v135 blind audit (Part A). No leader v135 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v135_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v135/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v135_audit_replication"
    assert d["anchors"] == ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["offsets_bps"] == [0, 5, 10, 20]
    assert set(d["offsets"].keys()) == {"0", "5", "10", "20"}
    for k, o in d["offsets"].items():
        assert len(o["yearly"]) == 5, k
        for y in o["yearly"]:
            assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
            assert y["fills"] > 0 and y["months"] == 12.0
        assert 0.0 <= o["full_path_dd"] < 100
        assert np.isfinite(o["monthly_pct"]) and np.isfinite(o["mean_net_first4"])
        assert 0.0 <= o["maker_fill_rate"] <= 1.0
        assert o["orders_live"] > 0 and o["fills_live"] > 0
        assert o["fills_live"] <= o["orders_live"]
        h = o["hidden_year"]
        for kk in ("net_pct", "max_drawdown_percent", "maker_fill_rate",
                   "orders_hidden_year", "fills_hidden_year"):
            assert kk in h, (k, kk)
        assert 0.0 <= h["maker_fill_rate"] <= 1.0
    assert d["chosen_d_bps"] in (0, 5, 10, 20)
    assert d["chosen"] == d["offsets"][str(d["chosen_d_bps"])]
    assert d["union_bars"] > 10000


def test_chosen_is_max_first4_and_pvol_matches_v129():
    d = _rep()
    means = {k: v["mean_net_first4"] for k, v in d["offsets"].items()}
    best = max(means, key=lambda k: means[k])
    assert str(d["chosen_d_bps"]) == best
    # base Wt must reuse audited v129 pvol method exactly
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["anchors_v114_pvol"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["anchors_v103_pvol"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    assert d["n_replaced"]["v114_lo"] > 50000
    # d=0 must reproduce the v133 hidden strict baseline (same Wt + v104 fill)
    v133 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v132_v133_audit/replication.json").read_text())
    h0 = d["offsets"]["0"]["hidden_year"]
    href = v133["v133"]["hidden_year_1m_execution_strict"]
    assert abs(h0["net_pct"] - href["net_pct"]) < 1e-9
    assert abs(h0["maker_fill_rate"] - href["maker_fill_rate"]) < 1e-9
    assert h0["orders_hidden_year"] == href["orders_hidden_year"]


def test_spec_guards_in_code():
    src = (AUD / "replicate_v135.py").read_text()
    # execution bar, fill window 2..14, fallback 15, offsets, fees
    assert "t + 4h" in src or "Timedelta(hours=4)" in src
    assert "range(2, 15)" in src
    assert "minutes=15" in src
    assert "OFFSETS_BPS = (0, 5, 10, 20)" in src
    assert "0.0005" in src and "0.0002" in src
    assert "v135_result.json" not in src and "v135_limit_offset" not in src
    assert "import v135" not in src and "from v135" not in src
    # weight base guard: original LS gate rib != 1 must be present, bear-only gate absent
    assert "rib != 1" in src
    assert "weights_ls_from_oos" in src
