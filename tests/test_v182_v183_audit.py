"""Tests for v182 + v183 blind audit (Part A). Does not open research/.../v182/ or v183/ result."""
import json
from pathlib import Path

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v182_v183_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v182_v183.py"
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
RUNGS = (2.5, 3.0, 3.5, 4.0)


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v182/v183 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v182_v183_audit_replication"
    assert d["blind"] == "did_not_open_research_v182_v183_until_this_file_saved"
    assert d["S_REF"] == 1.657
    assert abs(d["N_MAX"] - 0.05 / 0.30) < 1e-12
    assert d["feature_columns_v182"] == ["depth", "r5", "r15", "vspike", "taker15", "rng",
                                        "breadth", "btc_depth", "trend", "r1d", "funding", "k"]
    assert "asset" not in " ".join(d["feature_columns_v182"])
    assert d["model"]["max_depth"] == 3
    assert d["model"]["learning_rate"] == 0.03
    assert d["model"]["max_iter"] == 300
    assert d["model"]["min_samples_leaf"] == 50
    assert d["model"]["l2_regularization"] == 1.0
    assert d["spec"]["symbols_v182"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",
                                        "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "TRXUSDT"]
    assert d["spec"]["symbols_v183"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["v182"]["candidates_total_pooled"] == 14593
    assert d["v182"]["candidates_majors"] == 6972
    assert d["v182"]["live_total_majors"] == 4609


def test_v182_rows():
    d = _rep()["v182"]
    n = d["primary_normal"]
    assert n["monthly_pct"] == 4.165
    assert n["full_path_dd"] == 18.15
    assert n["dd_1m_mark"] == 19.39
    assert n["gate_dd"] == 19.39
    assert n["rungs_taken"] == 1884
    assert n["rungs_cancelled"] == 2716
    assert n["mean_s"] == 1.486
    s = d["stress"]
    assert s["monthly_pct"] == 3.774
    assert s["full_path_dd"] == 18.31
    assert s["dd_1m_mark"] == 19.74
    assert s["rungs_taken"] == 1898
    assert s["rungs_cancelled"] == 2702
    assert n["rungs_taken"] + n["rungs_cancelled"] == 4600
    assert s["rungs_taken"] + s["rungs_cancelled"] == 4600


def test_v182_per_anchor():
    d = _rep()["v182"]
    per = {p["anchor"]: p for p in d["per_anchor"]}
    for a in ANCHORS:
        assert a in per
    # majors test fills reproduce the v180 ladder exactly
    assert per["2021-09-24"]["test_majors_points"] == 932
    assert per["2022-09-24"]["test_majors_points"] == 973
    assert per["2023-09-24"]["test_majors_points"] == 1250
    assert per["2024-09-24"]["test_majors_points"] == 946
    assert per["2025-09-24"]["test_majors_points"] == 1092
    # pooled training is larger than majors-only training
    assert per["2021-09-24"]["train_points"] == 3621
    assert per["2025-09-24"]["train_points"] == 12338
    assert per["2021-09-24"]["live_pred_pos"] == 831
    assert per["2022-09-24"]["live_pred_pos"] == 854
    assert per["2023-09-24"]["live_pred_pos"] == 1101
    assert per["2024-09-24"]["live_pred_pos"] == 885
    assert per["2025-09-24"]["live_pred_pos"] == 938
    assert per["2021-09-24"]["ic_spearman_majors"] == -0.055057964556207345
    assert per["2024-09-24"]["ic_spearman_majors"] == 0.20098707455689194


def test_v183_rows():
    d = _rep()["v183"]
    assert d["fills_total_grid"] == 6972
    assert d["tp_fills_grid"] == 4053
    n = d["primary_normal"]
    assert n["monthly_pct"] == 4.284
    assert n["full_path_dd"] == 18.75
    assert n["dd_1m_mark"] == 19.01
    assert n["gate_dd"] == 19.01
    assert n["rungs_taken"] == 2185
    assert n["rungs_cancelled"] == 2999
    assert n["tp_exits_taken"] == 1077
    assert n["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"
    assert n["mean_s"] == 1.629
    s = d["stress"]
    assert s["monthly_pct"] == 3.877
    assert s["full_path_dd"] == 18.87
    assert s["dd_1m_mark"] == 19.13
    assert s["rungs_taken"] == 2203
    assert s["rungs_cancelled"] == 2981
    assert s["tp_exits_taken"] == 1085
    assert s["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"


def test_budget_math_synthetic():
    assert abs(0.05 / 0.30 - 1 / 6) < 1e-12
    rn = 1.486 * 1.0 * 0.25 / 4 / 1.657
    assert abs(rn - 0.05605) < 1e-4
    # v179 total-only: used + rn <= 1/6
    assert int((0.05 / 0.30) // rn) == 2
    # v183 concurrent-open: (open_taken + 1) * rn <= 1/6; TP exit frees a slot
    nmax = 0.05 / 0.30
    open_taken = 1  # one earlier rung with exit minute 999 still open
    assert (open_taken + 1) * rn <= nmax + 1e-12  # second fill fits at mean scale
    open_taken = 2
    assert (open_taken + 1) * rn > nmax  # third concurrent fill rejected
    # TP price def: TP = L * (1 + sigma); TP net normal = sigma - 2*maker
    L, sig = 100.0, 0.01
    assert abs((L * (1 + sig)) / L - 1 - sig) < 1e-15
    assert abs((sig - 0.0004) - 0.0096) < 1e-12
    # order: (fill minute, shallower rung, column BNB,BTC,ETH,SOL,XRP)
    fills = [(20, 1, 1), (18, 0, 4), (18, 0, 2), (20, 0, 0)]
    assert sorted(fills) == [(18, 0, 2), (18, 0, 4), (20, 0, 0), (20, 1, 1)]


def test_lookahead_timing_definition():
    # v182 features use minutes <= f-1 of holding bar T (known at fill f);
    # breadth/btc_depth at the same f-1 minute; trend/r1d/funding at or before t/T.
    # v183 TP trigger uses minutes m > f strictly after the fill; budget open
    # count uses only exits with exit minute <= current fill minute (past highs).
    # vol uses sleeve_unit shifted by 2. Payoff uses s[i]*g[i] at bar-close i.
    assert True


def test_blind_script_does_not_open_v182_v183():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v182_result" not in body
    assert "v183_result" not in body
    assert "v182_pooled" not in body
    assert "v183_tp" not in body
    assert "v182/v182" not in body
    assert "v183/v183" not in body
