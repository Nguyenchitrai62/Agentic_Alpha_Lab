"""v302 + v303 blind audit tests (fast, no full replay; heavy replay lives in v302_v303_audit/replicate_v302_v303.py)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v302_v303_audit/replicate_v302_v303.py")
AUD = Path("research/parallel/rounds/parallel-20260906-r2/v302_v303_audit")
REP = AUD / "replication.json"
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
P302 = Path("research/parallel/rounds/parallel-20260906-r2/v302/v302_flush_breadth.py")
P303 = Path("research/parallel/rounds/parallel-20260906-r2/v303/v303_breadth_seeds.py")
P301 = Path("research/parallel/rounds/parallel-20260906-r2/v301/v301_return_first_budget.py")
P296 = Path("research/parallel/rounds/parallel-20260906-r2/v296/v296_joint_dip_agent.py")
P294 = Path("research/parallel/rounds/parallel-20260906-r2/v294/v294_wide_pool_exit_agent.py")
P293 = Path("research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py")
P286 = Path("research/parallel/rounds/parallel-20260906-r2/v286/v286_coinbase_member_upgrade.py")
REPV302 = Path("research/parallel/rounds/parallel-20260906-r2/v302/v302_result.json")
REPV303 = Path("research/parallel/rounds/parallel-20260906-r2/v303/v303_result.json")
V302_KEYS = ("G2_ref", "H1_breadth_both", "H2_breadth_size")
V303_KEYS = tuple(f"{n}_s{s}" for n in ("G2", "H1") for s in (0, 1, 2, 3, 4))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading version folders"
    return json.loads(REP.read_text())


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v302v303_cfg")
    assert dict(aud.C4R) == dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0)
    assert abs(float(aud.BUDGET) - 0.26) < 1e-12
    assert tuple(aud.MAJORS) == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert tuple(aud.RUNGS) == (2.5, 3.0, 3.5, 4.0)
    assert abs(float(aud.REF_G2_DEV4) - 6.527) < 1e-9
    assert abs(float(aud.REF_G2_DEVDD) - 17.33) < 1e-9
    assert abs(float(aud.MAKER) - 0.0002) < 1e-12
    assert abs(float(aud.TAKER) - 0.00055) < 1e-12
    assert abs(float(aud.MARGIN_TP) - 0.0010) < 1e-12
    assert aud.EMBARGO == __import__("pandas").Timedelta(days=7)
    assert tuple(aud.SEEDS) == (0, 1, 2, 3, 4)
    assert dict(aud.V302_ROWS) == {"G2_ref": (tuple(range(7)), tuple(range(7))),
                                   "H1_breadth_both": (tuple(range(10)), tuple(range(10))),
                                   "H2_breadth_size": (tuple(range(10)), tuple(range(7)))}
    s302 = P302.read_text()
    assert "G2_ref" in s302 and "H1_breadth_both" in s302 and "H2_breadth_size" in s302
    assert "breadth_arrays" in s302 and "sleeve_fill_size" in s302 and "sleeve_tp" in s302
    assert "sleeve_risk_budget" in s302 and "0.26" in s302
    assert "6.527" in s302 and "17.33" in s302
    assert "drawdown-first" in s302
    s303 = P303.read_text()
    assert "SEEDS" in s303 and "G2_s0" in s303 and "1000 * seed" in s303
    assert "median" in s303 and "6.527" in s303
    s294 = P294.read_text()
    assert "volume_2020_12.csv" in s294 and "head(30)" in s294


def test_fidelity_and_leakage_source_guards():
    src = AUD_MOD.read_text()
    assert "t_exit < a0 - EMBARGO" in src
    assert "universe()" in src and "volume_2020_12" in src
    assert "rung_stats" in src and "dev_rungs" in src
    assert "kk = j * 240 + f - 1" in src or "k = j * 240 + f - 1" in src
    assert "risk_open = sum(t[7] * (m_sleeve_sl * t[6] + gap)" in src
    assert "own_breadth" in src and "breadth_arrays" in src
    assert "runmin" in src and "lowf[:, :SLEEVE_START]" in src  # own impl masks minutes before 16 its own way
    assert "2 * mu" in src and "MARGIN_TP" in src
    d = _rep()
    for k in ("feature_timing", "label_windows", "fit_windows", "fill_timing"):
        assert k in d["leakage"]
    assert len(d["universe"]) == 30
    assert d["pool_fills"] >= 37000
    assert d["breadth_check"]["flush_exact"] is True
    assert d["breadth_check"]["max_abs_dmean"] < 1e-9
    assert d["breadth_check"]["max_abs_dmin"] < 1e-9


def test_engine_and_selection_guards():
    eu = _load(ENG, "engine_user_iso_check302303")
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
    v286 = _load(P286, "audit_v286_sel302303")
    aud = _load(AUD_MOD, "audit_v302v303_sel")
    assert inspect.getsource(v286.dev_dd) == inspect.getsource(aud.dev_dd)
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel302303")
    assert 'r["yearly"][:4]' in inspect.getsource(v204.worst_month)
    assert 'r["yearly"][:4]' in inspect.getsource(v286.dev_dd)

    def row(dev4, worst, nets, dd=10.0):
        return {"monthly_dev4": dev4, "worst_dev_month_pct": worst,
                "dev_dd": dd, "yearly": [{"net_pct": n, "dd_1m_pct": dd} for n in nets]}

    ref = row(6.527, 3.618, [50.0, 50.0, 50.0, 50.0], dd=17.33)
    h1 = row(6.527, 3.346, [50.0, 50.0, 50.0, 50.0], dd=16.49)
    h2 = row(6.423, 3.129, [50.0, 50.0, 50.0, 50.0], dd=17.38)
    # v302 drawdown-first shape: pool needs dev4 >= ref-0.15, worst >= ref worst-0.15, no losing year
    pool = {k: v for k, v in {"H1_breadth_both": h1, "H2_breadth_size": h2}.items()
            if v["monthly_dev4"] >= ref["monthly_dev4"] - 0.15
            and v["worst_dev_month_pct"] >= ref["worst_dev_month_pct"] - 0.15
            and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    assert pool == {}
    # v303 median shape: DD gate met, dev4 gate met, worst gate 3.346 >= 3.618-0.2 fails
    g_med = {"monthly_dev4": 6.601, "worst_dev_month_pct": 3.618, "dev_dd": 17.33}
    h_med = {"monthly_dev4": 6.582, "worst_dev_month_pct": 3.346, "dev_dd": 16.49}
    assert h_med["dev_dd"] <= g_med["dev_dd"] - 0.4
    assert h_med["monthly_dev4"] >= g_med["monthly_dev4"] - 0.15
    assert not (h_med["worst_dev_month_pct"] >= g_med["worst_dev_month_pct"] - 0.2)
    asrc = AUD_MOD.read_text()
    assert "1000 * seed" in asrc or "1000*seed" in asrc
    assert "sleeve_risk_budget" in asrc and "0.26" in asrc


def test_replication_structure_and_redaction():
    d = _rep()
    assert d["version"] == "v302_v303_audit_replication"
    assert d["blind"] == "did_not_open_results_nor_execution_outputs_until_this_file_saved"
    assert set(d["v302"]["rows"].keys()) == set(V302_KEYS)
    assert set(d["v303"]["rows"].keys()) == set(V303_KEYS)
    assert d["v302"]["selected"] is None
    assert d["v303"]["selected"] is None
    assert abs(d["v302"]["rows"]["G2_ref"]["monthly_dev4"] - 6.527) < 0.002
    assert abs(d["v302"]["rows"]["G2_ref"]["dev_dd"] - 17.33) < 0.02
    assert abs(d["v303"]["rows"]["G2_s0"]["monthly_dev4"] - 6.527) < 0.002
    assert abs(d["v303"]["rows"]["H1_s0"]["monthly_dev4"] - d["v302"]["rows"]["H1_breadth_both"]["monthly_dev4"]) < 1e-9
    for k in V302_KEYS:
        r = d["v302"]["rows"][k]
        assert "monthly_dev4" in r and "dev_dd" in r
        assert "dev_rungs" in r and "worst_dev_month_pct" in r
        assert "dev trade win" not in r
        assert d["v302"]["trades"][k]["dev"]["win_rate"] > 0
    for k in V303_KEYS:
        r = d["v303"]["rows"][k]
        assert "monthly_dev4" in r and "dev_dd" in r and "worst_dev_month_pct" in r
        assert d["v303"]["trades"][k]["dev"]["win_rate"] > 0
    # redaction: nothing selected -> every row carries dev years only
    for sec, keys in (("v302", V302_KEYS), ("v303", V303_KEYS)):
        for k in keys:
            r = d[sec]["rows"][k]
            assert "monthly_last_year" not in r and "monthly_5y" not in r
            assert len(r["yearly"]) == 4
            assert "_hidden" not in d[sec]["trades"][k]
    assert "no row meets the drawdown-first rule" in d["v302"]["final_score_selected"]
    assert "not selected (median rule)" in d["v303"]["final_score_selected"]
    assert set(d["v303"]["summary"].keys()) == {"G2", "H1"}
    assert d["fills"] and sum(d["fills"].values()) >= 37000


def test_replication_matches_reported_within_thresholds():
    d = _rep()
    assert REPV302.exists() and REPV303.exists()
    rep302 = json.loads(REPV302.read_text())
    rep303 = json.loads(REPV303.read_text())
    for key in V302_KEYS:
        assert abs(float(d["v302"]["rows"][key]["monthly_dev4"]) - float(rep302["rows"][key]["monthly_dev4"])) <= 1.0, key
        assert abs(float(d["v302"]["rows"][key]["dev_dd"]) - float(rep302["rows"][key]["dev_dd"])) <= 0.5, key
        assert d["v302"]["trades"][key] == rep302["trades"][key], key
    for key in V303_KEYS:
        assert abs(float(d["v303"]["rows"][key]["monthly_dev4"]) - float(rep303["rows"][key]["monthly_dev4"])) <= 1.0, key
        assert abs(float(d["v303"]["rows"][key]["dev_dd"]) - float(rep303["rows"][key]["dev_dd"])) <= 0.5, key
        assert d["v303"]["trades"][key] == rep303["trades"][key], key
    assert d["v302"]["selected"] == rep302["selected"]
    assert d["v303"]["selected"] == rep303["selected"]
    assert d["v302"]["final_score_selected"] == rep302["final_score_selected"]
    assert d["v303"]["final_score_selected"] == rep303["final_score_selected"]
    assert (AUD / "COMPARISON.md").exists()
    comp = (AUD / "COMPARISON.md").read_text()
    assert "## Verdict" in comp
    assert "v302: PASS" in comp and "v303: PASS" in comp


def test_blind_and_leakage_guards():
    src = AUD_MOD.read_text()
    assert "did_not_open_results_nor_execution_outputs_until_this_file_saved" in src
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    cleaned = body.replace("research/parallel/rounds/parallel-20260906-r2/v302/v302_flush_breadth.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v303/v303_breadth_seeds.py", "")
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
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v302_v303_audit", "")
    cleaned = cleaned.replace("v302_v303_audit", "")
    cleaned = cleaned.replace("replicate_v302_v303", "")
    cleaned = cleaned.replace("audit302303", "")
    assert "v302_result" not in cleaned
    assert "v303_result" not in cleaned
    assert "run.log" not in body and "run.err.log" not in body
    assert "win_start" in src and "sleeve_fill_size" in src and "sleeve_tp" in src
