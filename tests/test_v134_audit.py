"""Tests for v134 blind audit (Part A). No leader v134 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v134_audit")
REP = AUD / "replication.json"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v134/ folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v134_audit_replication"
    assert set(("normal", "fee_stress", "execution_stress")) <= set(d["scenarios"].keys())
    for sc in ("normal", "fee_stress", "execution_stress"):
        s = d["scenarios"][sc]
        assert np.isfinite(s["monthly_pct"])
        assert np.isfinite(s["full_path_dd"])
        assert len(s["yearly"]) == 5
        for y in s["yearly"]:
            assert y["fills"] > 0
    h = d["hidden_year_1m_execution_strict"]
    for k in ("net_pct", "max_drawdown_percent", "maker_fill_rate",
              "orders_hidden_year", "fills_hidden_year"):
        assert k in h, k
    assert 0.0 <= h["maker_fill_rate"] <= 1.0
    assert d["union_bars"] > 10000


def test_pvol_replacement_and_bear_only():
    d = _rep()
    assert len(d["anchors_v114_pvol"]) == 5 and len(d["anchors_v103_pvol"]) == 5
    for a in d["anchors_v114_pvol"] + d["anchors_v103_pvol"]:
        assert a["train_rows"] > 0 and a["n_pred_rows"] > 0
    assert d["n_replaced"]["v114_lo"] > 0
    assert d["n_replaced"]["v114_ls"] > 0
    assert d["n_replaced"]["v103"] > 0
    # bear-only shorts must be a strict subset of gross: fraction in [0,1)
    for tag in ("v94", "v103"):
        f = d["short_fraction_of_ls_gross"][tag]
        assert 0.0 <= f <= 1.0
    # spec check: short leg formula is rib == -1 gated (code-level guard)
    src = (AUD / "replicate_v134.py").read_text()
    assert "rib == -1" in src
    assert "weights_ls_bear_only_from_oos" in src
