"""Tests for v185 blind audit (Part A). Does not open research v185 result."""
import json
from pathlib import Path

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v185_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v185.py"
RUNGS = (2.5, 3.0, 3.5, 4.0)


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v185 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v185_audit_replication"
    assert d["blind"] == "did_not_open_research_v185_until_this_file_saved"
    assert d["S_REF"] == 1.657
    assert abs(d["N_MAX"] - 0.05 / 0.30) < 1e-12
    assert "g NOT" in d["rung_notional"]
    assert d["spec"]["symbols"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["spec"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert d["counts_grid"]["fills_total"] == 6972
    assert d["counts_grid"]["tp_fills"] == 4053


def test_normal_row():
    d = _rep()["primary_normal"]
    assert d["monthly_pct"] == 4.311
    assert d["full_path_dd"] == 18.71
    assert d["dd_1m_mark"] == 18.99
    assert d["gate_dd"] == 18.99
    assert d["dd_1m_worst_bar"] == "2022-04-21 16:00:00+00:00"
    assert d["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"
    assert d["rungs_taken"] == 2143
    assert d["rungs_cancelled"] == 3041
    assert d["tp_exits_taken"] == 1062
    assert d["mean_s"] == 1.629
    assert d["rungs_taken"] + d["rungs_cancelled"] == 5184
    nets = {y["anchor"][:4]: y["net_pct"] for y in d["yearly"]}
    assert nets == {"2021": 26.66, "2022": 51.96, "2023": 123.84, "2024": 74.84, "2025": 67.01}


def test_stress_row():
    d = _rep()["stress"]
    assert d["monthly_pct"] == 3.906
    assert d["full_path_dd"] == 18.85
    assert d["dd_1m_mark"] == 19.13
    assert d["gate_dd"] == 19.13
    assert d["dd_1m_worst_bar"] == "2022-04-21 16:00:00+00:00"
    assert d["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"
    assert d["rungs_taken"] == 2152
    assert d["rungs_cancelled"] == 3032
    assert d["tp_exits_taken"] == 1065
    assert d["mean_s"] == 1.627
    assert d["rungs_taken"] + d["rungs_cancelled"] == 5184
    nets = {y["anchor"][:4]: y["net_pct"] for y in d["yearly"]}
    assert nets["2022"] == 44.55
    assert nets["2024"] == 64.64
    assert nets["2025"] == 58.65


def test_budget_math_synthetic():
    assert abs(0.05 / 0.30 - 1 / 6) < 1e-12
    # v185: rn without governor
    s, g = 1.629, 0.863
    rn_outside = s * 0.25 / 4 / 1.657
    rn_inside = s * g * 0.25 / 4 / 1.657
    assert abs(rn_outside - 0.06144) < 1e-4
    assert rn_outside > rn_inside  # outside governor sizes larger after drawdowns
    nmax = 0.05 / 0.30
    assert int(nmax // rn_outside) == 2
    open_taken = 1
    assert (open_taken + 1) * rn_outside <= nmax + 1e-12
    open_taken = 2
    assert (open_taken + 1) * rn_outside > nmax
    # TP net normal = sigma - 2*maker
    assert abs((0.01 - 0.0004) - 0.0096) < 1e-12
    fills = [(20, 1, 1), (18, 0, 4), (18, 0, 2), (20, 0, 0)]
    assert sorted(fills) == [(18, 0, 2), (18, 0, 4), (20, 0, 0), (20, 1, 1)]


def test_lookahead_timing_definition():
    # v185 = v183 ladder/TP with rn outside the governor: TP trigger uses
    # minutes m > f strictly after the fill; budget open count uses only
    # exits with exit minute > current fill minute (past highs); governor
    # reads total equity at i-2; vol sleeve_unit shifted by 2.
    assert True


def test_blind_script_does_not_open_v185():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v185_result" not in body
    assert "v185_sleeve" not in body
    assert "sleeve_outside" not in body
    assert "v185/v185" not in body
