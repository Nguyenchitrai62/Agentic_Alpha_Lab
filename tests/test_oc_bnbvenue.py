"""Tests for oc_bnbvenue: pure-helper hand checks + own-results schema (light)."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "research" / "tournament" / "oc_bnbvenue" / "compute_bnbvenue.py"


def _load():
    spec = importlib.util.spec_from_file_location("bnbvenue_mod", str(MOD))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod


M = _load()


def test_share_handchecked():
    # 0.348 / 0.516 ~= 0.674 (BNB share of net B1 gap)
    assert abs(M.bnb_share_net(0.348, 0.516) - 0.6744186) < 1e-4
    # share can exceed 1 (XRP-like carrier) — must not be clipped
    assert M.bnb_share_net(0.553, 0.516) > 1.0
    # zero-total guard is NaN, never zero
    import math
    assert math.isnan(M.bnb_share_net(1.0, 0.0))


def test_monthly_geo_handchecked():
    # 26.3874x over 60 anchor-months ~= 5.6 %/month
    r = M.monthly_geo(26.3874, 60.0)
    assert 0.05 < r < 0.06
    # doubling over 12 months ~= 5.95 %/month
    assert abs(M.monthly_geo(2.0, 12.0) - 0.059463) < 1e-4


def test_additive_and_scenario_a():
    assert abs(M.additive_share(39.332, 287.278) - 0.136913) < 1e-4
    # proportional illustration is exact multiplication (labelled, not a conversion)
    assert M.scenario_a_illustration(0.6739458, -0.153) == \
        0.6739458 * -0.153
    assert M.scenario_a_illustration(0.5, -0.484) == -0.242


def test_results_schema_and_bands():
    res = json.loads((ROOT / "research" / "tournament" / "oc_bnbvenue"
                      / "results.json").read_text())
    for key in ("topbook_spreads_bps", "dip_leg_b1_replica_rungy",
                "divergent_tp_b1", "book_leg_deployment_engine",
                "deployment_g2", "bnb_pnl_share_contrib", "dd_episodes_bnb",
                "scenarios_hypothesis_only"):
        assert key in res, key
    # topbook: only BNB is ~10x, others ~1x
    assert 9.0 < res["topbook_spreads_bps"]["BNBUSDT"]["ratio"] < 11.0
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"):
        assert 0.95 < res["topbook_spreads_bps"][sym]["ratio"] < 1.05
    # BNB dip gap positive, 4/5 years, small vs Bybit rung P&L
    d = res["dip_leg_b1_replica_rungy"]
    assert d["bnb_gap"] > 0 and d["bnb_pos_years_of_5"] == 4
    assert res["scenarios_hypothesis_only"]["a_rungy_context"][
        "bnb_over_byb_rungpnl"] < 0.05
    # book leg: deployment dip dominates book in both phases
    for sh in ("0", "2"):
        leg = res["book_leg_deployment_engine"][sh]
        assert abs(leg["dip_eff_m"]) > abs(leg["book_eff_m"])
    # deployment gate DD and BNB additive share bands
    assert res["deployment_g2"]["full_path"]["DD_gate"] == 16.82
    assert 0.10 < res["bnb_pnl_share_contrib"]["bnb_share_additive"] < 0.20
    # boundary: assignment market-data cap respected in config
    assert "2026-09-24" in res["config"]["boundary"]
