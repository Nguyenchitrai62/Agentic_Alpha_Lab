"""v304 blind audit tests (fast, no full replay; heavy replay lives in v304_audit/replicate_v304.py)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v304_audit/replicate_v304.py")
AUD = Path("research/parallel/rounds/parallel-20260906-r2/v304_audit")
REP = AUD / "replication.json"
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
P304 = Path("research/parallel/rounds/parallel-20260906-r2/v304/v304_ladder_depth.py")
P301 = Path("research/parallel/rounds/parallel-20260906-r2/v301/v301_return_first_budget.py")
P296 = Path("research/parallel/rounds/parallel-20260906-r2/v296/v296_joint_dip_agent.py")
P294 = Path("research/parallel/rounds/parallel-20260906-r2/v294/v294_wide_pool_exit_agent.py")
P293 = Path("research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py")
P286 = Path("research/parallel/rounds/parallel-20260906-r2/v286/v286_coinbase_member_upgrade.py")
REPV304 = Path("research/parallel/rounds/parallel-20260906-r2/v304/v304_result.json")
KEYS = ("G2_ref", "R1_shallow", "R2_deep", "R3_wide")
SETS = {
    "G2_ref": (2.5, 3.0, 3.5, 4.0),
    "R1_shallow": (2.0, 2.5, 3.0, 3.5, 4.0),
    "R2_deep": (2.5, 3.0, 3.5, 4.0, 5.0),
    "R3_wide": (2.0, 2.5, 3.0, 3.5, 4.0, 5.0),
}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading version folders"
    return json.loads(REP.read_text())


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v304_cfg")
    assert abs(float(aud.BUDGET) - 0.26) < 1e-12
    assert dict(aud.SETS) == {k: tuple(v) for k, v in SETS.items()}
    assert tuple(aud.MAJORS) == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert abs(float(aud.REF_G2_DEV4) - 6.527) < 1e-9
    assert abs(float(aud.REF_G2_DEVDD) - 17.33) < 1e-9
    assert abs(float(aud.MAKER) - 0.0002) < 1e-12
    assert abs(float(aud.TAKER) - 0.00055) < 1e-12
    assert abs(float(aud.MARGIN_TP) - 0.0010) < 1e-12
    assert aud.EMBARGO == __import__("pandas").Timedelta(days=7)
    s304 = P304.read_text()
    assert "G2_ref" in s304 and "R1_shallow" in s304 and "R2_deep" in s304 and "R3_wide" in s304
    assert "v293.RUNGS = rungs" in s304 and "rungs=rungs" in s304
    assert "build_hooks" in s304 and "sleeve_fill_size" in s304 and "sleeve_tp" in s304
    assert "sleeve_risk_budget" in s304 and "0.26" in s304
    assert "6.527" in s304 and "17.33" in s304
    assert "return-first" in s304 or "RETURN-FIRST" in s304
    assert "0.15" in s304
    s301 = P301.read_text()
    assert "v293.RUNGS[r]" in s301 and "sleeve_fill_size" in s301 and "sleeve_tp" in s301
    s294 = P294.read_text()
    assert "volume_2020_12.csv" in s294 and "head(30)" in s294


def test_fidelity_and_leakage_source_guards():
    src = AUD_MOD.read_text()
    assert "t_exit < a0 - EMBARGO" in src
    assert "universe()" in src and "volume_2020_12" in src
    assert "rung_stats" in src and "dev_rungs" in src
    assert "kk = j * 240 + f - 1" in src
    assert "v293.RUNGS[r]" in src
    assert "rung=float(rungs[r])" in src
    assert "risk_open = sum(t[7] * (m_sleeve_sl * t[6] + gap)" in src
    assert "SIZE / 4 / S_REF" in src
    assert src.count("/ len(rungs)") == 1  # only the guard assert itself, no size divisor
    assert "no division by len(rungs)" in src or "NOT shrink" in src
    d = _rep()
    for k in ("feature_timing", "label_windows", "fit_windows", "fill_timing"):
        assert k in d["leakage"]
    assert len(d["universe"]) == 30 and len(d["universe_with_data"]) == 30
    assert d["budget"] == 0.26
    assert d["sets"] == {k: list(v) for k, v in SETS.items()}
    for k in KEYS:
        assert d["fills"][k]["_total"] >= 37000
        assert d["fidelity"][k]["share_best_within_1e4"] >= 0.97
        assert d["fidelity"][k]["mad_best"] < 2e-4


def test_engine_and_selection_guards():
    eu = _load(ENG, "engine_user_iso_check304")
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert abs(float(eu.SIZE) - 0.25) < 1e-12 and abs(float(eu.S_REF) - 1.657) < 1e-12
    import inspect
    src = inspect.getsource(eu.simulate)
    assert "win_start" in src and "FUND_LONG" in src
    assert "sleeve_fill_size" in src and "sleeve_tp" in src
    assert "sleeve_fill_size(i, a, r, f)" in src
    assert "sleeve_tp(i, a, r, f)" in src
    assert src.index("sleeve_fill_size(i, a, r, f)") < src.index("sleeve_risk_budget is None")
    assert "if rn <= 0:" in src
    assert "for r, k in enumerate(rungs)" in src
    assert "SIZE / 4 / S_REF" in src
    assert "/ len(rungs)" not in src
    assert "risk_open = sum(t[7] * (_msl(t[2]) * t[6] + gap)" in src
    assert "rn * (_msl(a) * sg + gap) > sleeve_risk_budget" in src
    assert "rung=float(rungs[r])" in src
    v286 = _load(P286, "audit_v286_sel304")
    aud = _load(AUD_MOD, "audit_v304_sel")
    assert inspect.getsource(v286.dev_dd) == inspect.getsource(aud.dev_dd)
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel304")
    assert 'r["yearly"][:4]' in inspect.getsource(v204.worst_month)
    assert 'r["yearly"][:4]' in inspect.getsource(v286.dev_dd)

    def row(dev4, worst, nets, dd=10.0):
        return {"monthly_dev4": dev4, "worst_dev_month_pct": worst,
                "dev_dd": dd, "yearly": [{"net_pct": n, "dd_1m_pct": dd} for n in nets]}

    ref = row(6.527, 3.618, [50.0, 50.0, 50.0, 50.0], dd=17.33)
    r1 = row(7.807, 3.696, [50.0, 50.0, 50.0, 50.0], dd=20.25)
    # return-first shape: pool needs devDD <= ref+0.5, worst >= 3.0, no losing year
    pool = {k: v for k, v in {"R1_shallow": r1}.items()
            if v["dev_dd"] <= ref["dev_dd"] + 0.5 and v["worst_dev_month_pct"] >= 3.0
            and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    assert pool == {}
    asrc = AUD_MOD.read_text()
    assert "pa > 2 * mu" in asrc and "pa < 0 and pb < 0" in asrc
    assert "0.0010" in asrc or "MARGIN_TP" in asrc
    assert "sleeve_risk_budget" in asrc and "0.26" in asrc
    assert "v293.RUNGS = rungs" in asrc or "v293.RUNGS" in asrc


def test_replication_structure_and_redaction():
    d = _rep()
    assert d["version"] == "v304_audit_replication"
    assert d["blind"] == "did_not_open_results_nor_execution_outputs_until_this_file_saved"
    assert set(d["rows"].keys()) == set(KEYS)
    assert d["selected"] is None
    assert d["replaces_g2"] is False
    assert abs(d["rows"]["G2_ref"]["monthly_dev4"] - 6.527) < 0.002
    assert abs(d["rows"]["G2_ref"]["dev_dd"] - 17.33) < 0.02
    assert "no row meets the return-first rule" in d["final_score_selected"]
    for k in KEYS:
        assert "monthly_dev4" in d["rows"][k] and "dev_dd" in d["rows"][k]
        assert "dev_rungs" in d["rows"][k] and "worst_dev_month_pct" in d["rows"][k]
        assert d["rows"][k]["budget"] == 0.26
        assert d["rows"][k]["rungs"] == list(SETS[k])
        ag = d["rows"][k]["agents"]["sleeve_fill_size"]
        assert ag["asked"] > 0
        assert "sleeve_tp" in d["rows"][k]["agents"]
        assert d["rows"][k]["agents"]["sleeve_tp"]["asked"] > 0
    # redaction: nothing selected -> every row carries dev years only
    for k in KEYS:
        r = d["rows"][k]
        assert "monthly_last_year" not in r and "monthly_5y" not in r
        assert len(r["yearly"]) == 4
        assert "_hidden" not in d["trades"][k]
    assert d["pool"] == []
    for k in KEYS:
        assert d["trades"][k]["dev"]["win_rate"] > 0
    assert d["fills"]["G2_ref"]["_total"] == 37741
    assert "consequence" in d["size_consequence"] or "NOT shrink" in d["size_consequence"]


def test_replication_matches_reported_within_thresholds():
    d = _rep()
    assert REPV304.exists()
    rep_json = json.loads(REPV304.read_text())
    for key in KEYS:
        assert abs(float(d["rows"][key]["monthly_dev4"]) - float(rep_json["rows"][key]["monthly_dev4"])) <= 1.0, key
        assert abs(float(d["rows"][key]["dev_dd"]) - float(rep_json["rows"][key]["dev_dd"])) <= 0.5, key
        assert d["rows"][key]["dev_rungs"] == rep_json["rows"][key]["dev_rungs"], key
        assert d["trades"][key] == rep_json["trades"][key], key
    assert d["selected"] == rep_json["selected"]
    assert d["final_score_selected"] == rep_json["final_score_selected"]
    assert (AUD / "COMPARISON.md").exists()
    comp = (AUD / "COMPARISON.md").read_text()
    assert "## Verdict" in comp and ("PASS" in comp or "FAIL" in comp)


def test_blind_and_leakage_guards():
    src = AUD_MOD.read_text()
    assert "did_not_open_results_nor_execution_outputs_until_this_file_saved" in src
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    cleaned = body.replace("research/parallel/rounds/parallel-20260906-r2/v304/v304_ladder_depth.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v301/v301_return_first_budget.py", "")
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
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v304_audit", "")
    cleaned = cleaned.replace("v304_audit", "")
    cleaned = cleaned.replace("replicate_v304", "")
    cleaned = cleaned.replace("audit304", "")
    assert "v304_result" not in cleaned
    assert "run.log" not in body and "run.err.log" not in body
    assert "win_start" in src and "sleeve_fill_size" in src and "sleeve_tp" in src
