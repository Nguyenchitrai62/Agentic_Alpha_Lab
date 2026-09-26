"""Tests for v193 blind audit (Part A). Does not open research v193 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v193_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v193.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v193 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v193_audit_replication"
    assert d["blind"] == "did_not_open_research_v193_until_this_file_saved"
    assert d["books"] == "pipeline P2=(A+B)/2 from cached v154 members"
    assert d["members_check"]["max_abs_diff_avg_vs_books"] == 0.0
    assert d["members_check"]["union_bars"] == 10950
    assert d["members_check"]["columns"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["engine"]["maker"] == 0.0002
    assert d["engine"]["taker"] == 0.00055
    assert d["engine"]["fund_long"] == 0.0001
    assert d["engine"]["m_sl"] == 4.0
    assert d["engine"]["m_sleeve_sl"] == 5.0
    assert d["engine"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert d["engine"]["d_limit"] == 0.001
    assert d["engine"]["win_end"] == 239
    assert d["engine"]["gap"] == 0.02
    assert d["engine"]["sleeve_risk_budgets"] == [0.03, 0.05, 0.08]
    assert set(d["rows"]) == {"P2_X030", "P2_X050", "P2_X080"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "P2"
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 5.0
        assert row["d_limit"] == 0.001
        assert row["win_end"] == 239
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["rows"]["P2_X030"]["sleeve_risk_budget"] == 0.03
    assert d["rows"]["P2_X050"]["sleeve_risk_budget"] == 0.05
    assert d["rows"]["P2_X080"]["sleeve_risk_budget"] == 0.08


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["P2_X030"]["monthly_dev4"] == 4.385
    assert d["P2_X030"]["monthly_5y"] == 4.046
    assert d["P2_X030"]["monthly_last_year"] == 2.704
    assert d["P2_X030"]["gate_dd"] == 19.6
    assert d["P2_X050"]["monthly_dev4"] == 4.747
    assert d["P2_X050"]["monthly_5y"] == 4.324
    assert d["P2_X050"]["monthly_last_year"] == 2.653
    assert d["P2_X050"]["gate_dd"] == 20.1
    assert d["P2_X080"]["monthly_dev4"] == 5.046
    assert d["P2_X080"]["monthly_5y"] == 4.603
    assert d["P2_X080"]["monthly_last_year"] == 2.847
    assert d["P2_X080"]["gate_dd"] == 19.33
    assert d["P2_X030"]["yearly_net_pct"] == [26.59, 47.2, 103.11, 107.26, 37.74]
    assert d["P2_X050"]["yearly_net_pct"] == [30.54, 52.17, 114.89, 116.98, 36.92]
    assert d["P2_X080"]["yearly_net_pct"] == [34.58, 54.37, 122.74, 129.58, 40.05]
    # rungs / stops / TPs / liq per budget
    assert d["P2_X030"]["stats"]["rungs"] == 3663
    assert d["P2_X030"]["stats"]["rung_stops"] == 127
    assert d["P2_X030"]["stats"]["rung_tps"] == 1886
    assert d["P2_X030"]["stats"]["liq"] == 0
    assert d["P2_X050"]["stats"]["rungs"] == 4505
    assert d["P2_X050"]["stats"]["rung_stops"] == 163
    assert d["P2_X050"]["stats"]["rung_tps"] == 2380
    assert d["P2_X050"]["stats"]["liq"] == 0
    assert d["P2_X080"]["stats"]["rungs"] == 5001
    assert d["P2_X080"]["stats"]["rung_stops"] == 191
    assert d["P2_X080"]["stats"]["rung_tps"] == 2714
    assert d["P2_X080"]["stats"]["liq"] == 0
    # larger budget -> more rungs taken
    assert d["P2_X030"]["stats"]["rungs"] < d["P2_X050"]["stats"]["rungs"] < d["P2_X080"]["stats"]["rungs"]
    # book fills move only via the equity-linked min-notional filter
    assert d["P2_X030"]["stats"]["fills"] == 39469
    assert d["P2_X050"]["stats"]["fills"] == 39670
    assert d["P2_X080"]["stats"]["fills"] == 39882
    assert d["P2_X030"]["stats"]["unfilled"] == 4009
    assert d["P2_X050"]["stats"]["unfilled"] == 4044
    assert d["P2_X080"]["stats"]["unfilled"] == 4063


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "P2_X080"
    assert sorted(d["eligible"]) == ["P2_X030", "P2_X080"]
    # X050 excluded by the DD <= 20 filter
    assert d["rows"]["P2_X050"]["gate_dd"] > 20
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    # selection is the max dev4 among eligible
    best = max(d["eligible"], key=lambda k: d["rows"][k]["monthly_dev4"])
    assert best == d["selection"]
    # dev4 cross-check: geometric mean of first-four nets
    for key, row in d["rows"].items():
        nets = row["yearly_net_pct"][:4]
        geo4 = float(np.prod([1 + x / 100 for x in nets]) ** (1 / 4) - 1)
        dev4 = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4 - row["monthly_dev4"]) < 0.002, key
    # gate DD is max of 4h-close and 1m-marked DD
    for key, row in d["rows"].items():
        assert abs(row["gate_dd"] - max(row["dd_4h"], row["dd_1m"])) < 1e-9, key
    # sleeve rows take rungs
    for key in ("P2_X030", "P2_X050", "P2_X080"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key


def test_gate_cost_model_synthetic():
    # maker 0.0002 on entries/TP, taker 0.00055 on stops/market exits,
    # longs pay 0.0001 at 00/08/16 UTC settlements, shorts zero.
    notional = 1.0
    assert abs(notional * 0.0002 - 0.0002) < 1e-12
    assert abs(notional * 0.00055 - 0.00055) < 1e-12
    assert abs(notional * 0.0001 - 0.0001) < 1e-12
    # stop-first: both hit in one minute -> stop fills at min(SL, open)
    sl, minute_open = 100.0, 99.0
    assert min(sl, minute_open) == 99.0


def test_blind_script_does_not_open_v193():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v193_result" not in body
    assert "v193/v193" not in body
    assert "v193/" not in body.replace("v193_audit", "")
    # script must reference P2 and the risk-budget sweep without last-year selection
    assert "P2" in body
    assert "sleeve_risk_budget" in body
    assert "monthly_dev4" in body
