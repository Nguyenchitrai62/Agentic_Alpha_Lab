"""Tests for v132+v133 blind audit (Part A). No leader v132/v133 code imported."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v132_v133_audit")
REP = AUD / "replication.json"
SYMS8 = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
         "DOGEUSDT", "TRXUSDT", "ADAUSDT")


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v132/ or v133/ folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v132_v133_audit_replication"
    assert set(("v132", "v133", "meta")) <= set(d.keys())
    v132 = d["v132"]
    assert set(v132["phases"].keys()) == {str(p) for p in range(6)}
    for p in range(6):
        for sc in ("normal", "fee_stress", "execution_stress"):
            r = v132["phases"][str(p)][sc]
            assert len(r["yearly"]) == 5
            for y in r["yearly"]:
                assert np.isfinite(y["net_pct"]) and np.isfinite(y["max_drawdown_percent"])
                assert y["fills"] > 0 and y["months"] == 12.0
            assert 0.0 <= r["full_path_dd"] < 100 and np.isfinite(r["monthly_pct"])
    for sc in ("normal", "fee_stress", "execution_stress"):
        s = v132["phase_summary"][sc]
        monthlies = [v132["phases"][str(p)][sc]["monthly_pct"] for p in range(6)]
        assert abs(s["monthly_pct_mean"] - float(np.mean(monthlies))) < 1e-3
    # per-asset ICs cover all 8 assets per book
    for k in ("v92_lo_vs_y", "v94_ls_vs_y42", "v103_ls_vs_y6", "v103_ls_vs_y18"):
        assert k in v132["ic_per_asset"], k
        for s in SYMS8:
            assert s in v132["ic_per_asset"][k], (k, s)
    assert len(v132["feats114"]) == 26
    assert len(v132["feats103"]) == 36
    v133 = d["v133"]
    assert set(v133["scenarios"].keys()) == {"normal", "fee_stress", "execution_stress"}
    for sc in ("normal", "fee_stress", "execution_stress"):
        r = v133["scenarios"][sc]
        assert len(r["yearly"]) == 5
        assert 0.0 <= r["full_path_dd"] < 100
    h = v133["hidden_year_1m_execution_strict"]
    for k in ("net_pct", "max_drawdown_percent", "maker_fill_rate",
              "orders_hidden_year", "fills_hidden_year"):
        assert k in h, k
    assert 0.0 <= h["maker_fill_rate"] <= 1.0
    assert h["orders_hidden_year"] > 0 and h["fills_hidden_year"] > 0
    assert h["fills_hidden_year"] <= h["orders_hidden_year"]


def test_v132_uses_8_assets_and_v133_pvol_matches_v129():
    d = _rep()
    v132 = d["v132"]
    # 8-asset OOS: 8*2190 bars/year = 17520 pred rows per anchor year
    for a in v132["anchors_v92"]:
        assert a["n_pred_rows"] == 8 * 2190, a
        assert a["train_rows"] > 50000
    for a in v132["anchors_v103"]:
        assert a["n_pred_rows"] == 8 * 2190, a
    # v133 pvol quality must match audited v129 (5-asset, same method)
    v129 = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v129_v131_audit/replication.json").read_text())
    for b, r in zip(d["v133"]["anchors_v114"], v129["v129"]["anchors_v114"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    for b, r in zip(d["v133"]["anchors_v103"], v129["v129"]["anchors_v103"]):
        assert b["train_rows"] == r["train_rows"]
        assert abs(b["spearman_pvol_realized"] - r["spearman_pvol_realized"]) < 1e-9
    # v133 replacement counts cover full OOS
    assert d["v133"]["n_replaced"]["v114_lo"] > 50000
    assert d["v133"]["n_replaced"]["v103"] > 50000


def test_phases_differ_and_hidden_sane():
    d = _rep()
    monthlies = [d["v132"]["phases"][str(p)]["normal"]["monthly_pct"] for p in range(6)]
    assert len(set(monthlies)) > 1
    h = d["v133"]["hidden_year_1m_execution_strict"]
    assert h["orders_hidden_year"] < 20000
