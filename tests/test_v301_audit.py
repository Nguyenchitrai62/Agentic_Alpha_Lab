"""v301 blind audit tests (fast, no full replay; heavy replay lives in v301_audit/replicate_v301.py)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v301_audit/replicate_v301.py")
AUD = Path("research/parallel/rounds/parallel-20260906-r2/v301_audit")
REP = AUD / "replication.json"
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
P301 = Path("research/parallel/rounds/parallel-20260906-r2/v301/v301_return_first_budget.py")
P296 = Path("research/parallel/rounds/parallel-20260906-r2/v296/v296_joint_dip_agent.py")
P294 = Path("research/parallel/rounds/parallel-20260906-r2/v294/v294_wide_pool_exit_agent.py")
P293 = Path("research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py")
P286 = Path("research/parallel/rounds/parallel-20260906-r2/v286/v286_coinbase_member_upgrade.py")
REPV301 = Path("research/parallel/rounds/parallel-20260906-r2/v301/v301_result.json")
G2_DIR = Path("research/diagnostics/g2_robustness")
G2_JSON = G2_DIR / "g2_robustness.json"
KEYS = ("J1_ref", "G1_b22", "G2_b26", "G3_size5tp_b22")
CANDS = ("G1_b22", "G2_b26", "G3_size5tp_b22")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading version folders"
    return json.loads(REP.read_text())


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v301_cfg")
    assert dict(aud.C4R) == dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0)
    assert tuple(aud.MAJORS) == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert tuple(aud.RUNGS) == (2.5, 3.0, 3.5, 4.0)
    assert abs(float(aud.REF_J1_DEV4) - 6.268) < 1e-9
    assert abs(float(aud.MAKER) - 0.0002) < 1e-12
    assert abs(float(aud.TAKER) - 0.00055) < 1e-12
    assert abs(float(aud.MARGIN_TP) - 0.0010) < 1e-12
    assert aud.EMBARGO == __import__("pandas").Timedelta(days=7)
    assert aud.BUDGETS == {"J1_ref": 0.18, "G1_b22": 0.22, "G2_b26": 0.26, "G3_size5tp_b22": 0.22}
    s301 = P301.read_text()
    assert "G1_b22" in s301 and "G2_b26" in s301 and "G3_size5tp_b22" in s301
    assert "J1_ref" in s301
    assert "sleeve_fill_size" in s301 and "sleeve_tp" in s301
    assert "sleeve_risk_budget" in s301 and "0.26" in s301
    assert "6.268" in s301
    assert "return-first" in s301 or "RETURN-FIRST" in s301
    s294 = P294.read_text()
    assert "volume_2020_12.csv" in s294 and "head(30)" in s294


def test_fidelity_and_leakage_source_guards():
    src = AUD_MOD.read_text()
    assert "t_exit < a0 - EMBARGO" in src
    assert "universe()" in src and "volume_2020_12" in src
    assert "rung_stats" in src and "dev_rungs" in src
    assert "kk = j * 240 + f - 1" in src
    assert "risk_open = sum(t[7] * (m_sleeve_sl * t[6] + gap)" in src
    d = _rep()
    for k in ("feature_timing", "label_windows", "fit_windows", "fill_timing"):
        assert k in d["leakage"]
    assert len(d["universe"]) == 30 and len(d["universe_with_data"]) == 30
    assert d["pool_fills"] >= 37000


def test_engine_and_selection_guards():
    eu = _load(ENG, "engine_user_iso_check301")
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    import inspect
    src = inspect.getsource(eu.simulate)
    assert "win_start" in src and "FUND_LONG" in src
    assert "sleeve_fill_size" in src and "sleeve_tp" in src
    assert "sleeve_fill_size(i, a, r, f)" in src
    assert "sleeve_tp(i, a, r, f)" in src
    assert src.index("sleeve_fill_size(i, a, r, f)") < src.index("sleeve_risk_budget is None")
    assert "if rn <= 0:" in src
    assert "risk_open = sum(t[7] * (_msl(t[2]) * t[6] + gap)" in src
    assert "rn * (_msl(a) * sg + gap) > sleeve_risk_budget" in src
    v286 = _load(P286, "audit_v286_sel301")
    aud = _load(AUD_MOD, "audit_v301_sel")
    assert inspect.getsource(v286.dev_dd) == inspect.getsource(aud.dev_dd)
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel301")
    assert 'r["yearly"][:4]' in inspect.getsource(v204.worst_month)
    assert 'r["yearly"][:4]' in inspect.getsource(v286.dev_dd)

    def row(dev4, worst, nets, dd=10.0):
        return {"monthly_dev4": dev4, "worst_dev_month_pct": worst,
                "dev_dd": dd, "yearly": [{"net_pct": n, "dd_1m_pct": dd} for n in nets]}

    ref = row(6.268, 3.577, [50.0, 50.0, 50.0, 50.0], dd=17.84)
    g_lo = row(6.60, 3.60, [50.0, 50.0, 50.0, 50.0], dd=17.33)
    g_bad = row(6.70, 2.50, [50.0, 50.0, 50.0, 50.0], dd=17.33)
    # stepwise return-first shape: pool needs devDD <= ref+0.5, worst >= 3.0, no losing year
    pool = {k: v for k, v in {"G_lo": g_lo, "G_bad": g_bad}.items()
            if v["dev_dd"] <= ref["dev_dd"] + 0.5 and v["worst_dev_month_pct"] >= 3.0
            and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    assert set(pool) == {"G_lo"}
    sel = max(pool, key=lambda k: (pool[k]["monthly_dev4"], pool[k]["worst_dev_month_pct"]))
    assert sel == "G_lo"
    assert pool[sel]["monthly_dev4"] >= ref["monthly_dev4"] + 0.05
    asrc = AUD_MOD.read_text()
    assert "pa > 4 * mu" in asrc and "pa < -mu" in asrc
    assert "0.0010" in asrc or "MARGIN_TP" in asrc
    assert "sleeve_risk_budget=budget" in asrc or "sleeve_risk_budget" in asrc


def test_replication_structure_and_redaction():
    d = _rep()
    assert d["version"] == "v301_audit_replication"
    assert d["blind"] == "did_not_open_results_nor_execution_outputs_until_this_file_saved"
    assert set(d["rows"].keys()) == set(KEYS)
    assert d["selected"] in CANDS
    assert isinstance(d["replaces_j1"], bool)
    assert abs(d["rows"]["J1_ref"]["monthly_dev4"] - 6.268) < 0.002
    for k in KEYS:
        assert "monthly_dev4" in d["rows"][k] and "dev_dd" in d["rows"][k]
        assert "dev_rungs" in d["rows"][k] and "worst_dev_month_pct" in d["rows"][k]
        assert d["rows"][k]["budget"] == {"J1_ref": 0.18, "G1_b22": 0.22, "G2_b26": 0.26, "G3_size5tp_b22": 0.22}[k]
    for k in KEYS:
        ag = d["rows"][k]["agents"]["sleeve_fill_size"]
        assert ag["asked"] > 0
        assert set(ag) == {"asked", "x0", "x0.5", "x1.5", "x2"}
        assert "sleeve_tp" in d["rows"][k]["agents"]
        assert d["rows"][k]["agents"]["sleeve_tp"]["asked"] > 0
    for key in KEYS:
        r = d["rows"][key]
        if key == d["selected"]:
            assert "monthly_last_year" in r and "monthly_5y" in r and len(r["yearly"]) == 5
            assert "hidden_year_trades" in d["final_score_selected"]
        else:
            assert "monthly_last_year" not in r and "monthly_5y" not in r
            assert len(r["yearly"]) == 4
    for key in KEYS:
        if key != d["selected"]:
            assert "_hidden" not in d["trades"][key]
    assert d["final_score_selected"]["yearly"][0][0] == "2021"
    assert "hidden_year_trades" in d["final_score_selected"]
    assert d["fills"] and sum(d["fills"].values()) >= 37000


def test_replication_matches_reported_within_thresholds():
    d = _rep()
    assert REPV301.exists()
    rep_json = json.loads(REPV301.read_text())
    for key in KEYS:
        assert abs(float(d["rows"][key]["monthly_dev4"]) - float(rep_json["rows"][key]["monthly_dev4"])) <= 1.0, key
        assert abs(float(d["rows"][key]["dev_dd"]) - float(rep_json["rows"][key]["dev_dd"])) <= 0.5, key
    assert d["selected"] == rep_json["selected"]
    assert d["final_score_selected"]["hidden_year_trades"] == rep_json["final_score_selected"]["hidden_year_trades"]
    assert (AUD / "COMPARISON.md").exists()
    comp = (AUD / "COMPARISON.md").read_text()
    assert "## Verdict" in comp and ("PASS" in comp or "FAIL" in comp)


def test_blind_and_leakage_guards():
    src = AUD_MOD.read_text()
    assert "did_not_open_results_nor_execution_outputs_until_this_file_saved" in src
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    cleaned = body.replace("research/parallel/rounds/parallel-20260906-r2/v301/v301_return_first_budget.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v296/v296_joint_dip_agent.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v294/v294_wide_pool_exit_agent.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v286/v286_coinbase_member_upgrade.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v221/v221_grid_hysteresis.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v216/v216_trade_grid.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v213/v213_trade_exits.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py", "")
    cleaned = cleaned.replace("data/raw/um_universe_20260930/volume_2020_12.csv", "")
    cleaned = cleaned.replace("data/raw/alts_intraday_20260926", "")
    cleaned = cleaned.replace("data/raw/alts2020_intraday_20260930", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v301_audit", "")
    cleaned = cleaned.replace("v301_audit", "")
    cleaned = cleaned.replace("replicate_v301", "")
    cleaned = cleaned.replace("audit301", "")
    assert "v301_result" not in cleaned
    assert "run.log" not in body and "run.err.log" not in body
    assert "win_start" in src and "sleeve_fill_size" in src and "sleeve_tp" in src


def test_g2_robustness_guards():
    assert G2_JSON.exists()
    d = json.loads(G2_JSON.read_text())
    rows = d["rows"]
    assert abs(rows["CB_base"]["monthly_dev4"] - 5.864) < 0.01
    assert abs(rows["G2_base"]["monthly_dev4"] - 6.527) < 0.01
    assert abs(rows["G2_base"]["monthly_5y"] - 6.318) < 0.005
    assert abs(rows["G2_base"]["monthly_last_year"] - 5.486) < 0.005
    assert abs(rows["G2_base"]["gate_dd"] - 17.52) < 0.05
    shared = ["cost_stress", "latency_15", "latency_30", "latency_60", "band_lo", "band_hi",
              "cool_3", "cool_12", "sleeve_0.22", "sleeve_0.30", "offset_0.15", "offset_0.40",
              "outage_backstop_only", "close_1m"]
    for name in shared:
        assert rows[f"G2_{name}"]["monthly_dev4"] > rows[f"CB_{name}"]["monthly_dev4"], name
    assert "G2_bar_open" in rows and "G2_size_only_bar_open" in rows
    assert rows["G2_bar_open"]["monthly_dev4"] >= rows["G2_size_only_bar_open"]["monthly_dev4"]
    assert (G2_DIR / "SUMMARY.md").exists()
    summ = (G2_DIR / "SUMMARY.md").read_text()
    assert len(summ.splitlines()) <= 25
    assert "at least as robust" in summ or "robust" in summ
