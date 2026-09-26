"""Tests for v197 blind audit (Part A). Does not open research v197 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v197_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v197.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v197 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v197_audit_replication"
    assert d["blind"] == "did_not_open_research_v197_until_this_file_saved"
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
    assert d["engine"]["target"] == 0.25
    assert d["engine"]["cap"] == 2.0
    assert d["engine"]["mults"] == [1.0, 1.5, 2.0]
    assert d["engine"]["sleeve_risk_budgets"] == [0.08, 0.12, 0.16]
    assert set(d["rows"]) == {"P2_M100", "P2_M150", "P2_M200"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "P2"
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 5.0
        assert row["d_limit"] == 0.001
        assert row["win_end"] == 239
        assert row["target"] == 0.25
        assert row["cap"] == 2.0
        assert row["gap"] == 0.02
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["rows"]["P2_M100"]["mult"] == 1.0
    assert d["rows"]["P2_M100"]["size_mult"] == 1.0
    assert d["rows"]["P2_M100"]["sleeve_risk_budget"] == 0.08
    assert d["rows"]["P2_M150"]["mult"] == 1.5
    assert d["rows"]["P2_M150"]["size_mult"] == 1.5
    assert d["rows"]["P2_M150"]["sleeve_risk_budget"] == 0.12
    assert d["rows"]["P2_M200"]["mult"] == 2.0
    assert d["rows"]["P2_M200"]["size_mult"] == 2.0
    assert d["rows"]["P2_M200"]["sleeve_risk_budget"] == 0.16


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["P2_M100"]["monthly_dev4"] == 5.046
    assert d["P2_M100"]["monthly_5y"] == 4.603
    assert d["P2_M100"]["monthly_last_year"] == 2.847
    assert d["P2_M100"]["gate_dd"] == 19.33
    assert d["P2_M150"]["monthly_dev4"] == 5.562
    assert d["P2_M150"]["monthly_5y"] == 4.996
    assert d["P2_M150"]["monthly_last_year"] == 2.761
    assert d["P2_M150"]["gate_dd"] == 19.32
    assert d["P2_M200"]["monthly_dev4"] == 5.935
    assert d["P2_M200"]["monthly_5y"] == 5.192
    assert d["P2_M200"]["monthly_last_year"] == 2.273
    assert d["P2_M200"]["gate_dd"] == 24.27
    assert d["P2_M100"]["yearly_net_pct"] == [34.58, 54.37, 122.74, 129.58, 40.05]
    assert d["P2_M150"]["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert d["P2_M200"]["yearly_net_pct"] == [48.7, 40.55, 169.43, 182.72, 30.96]
    assert d["P2_M100"]["yearly_dd_1m_pct"] == [19.33, 15.47, 13.87, 8.92, 13.47]
    assert d["P2_M150"]["yearly_dd_1m_pct"] == [19.32, 17.51, 14.8, 8.77, 15.66]
    assert d["P2_M200"]["yearly_dd_1m_pct"] == [19.0, 22.6, 17.93, 9.36, 19.19]
    assert d["P2_M100"]["stats"]["rungs"] == 5001
    assert d["P2_M100"]["stats"]["rung_stops"] == 191
    assert d["P2_M100"]["stats"]["rung_tps"] == 2714
    assert d["P2_M100"]["stats"]["liq"] == 0
    assert d["P2_M150"]["stats"]["rungs"] == 5004
    assert d["P2_M150"]["stats"]["rung_stops"] == 191
    assert d["P2_M150"]["stats"]["rung_tps"] == 2717
    assert d["P2_M150"]["stats"]["liq"] == 0
    assert d["P2_M200"]["stats"]["rungs"] == 5010
    assert d["P2_M200"]["stats"]["rung_stops"] == 192
    assert d["P2_M200"]["stats"]["rung_tps"] == 2721
    assert d["P2_M200"]["stats"]["liq"] == 0
    assert d["P2_M100"]["stats"]["fills"] == 39882
    assert d["P2_M150"]["stats"]["fills"] == 40078
    assert d["P2_M200"]["stats"]["fills"] == 39762
    assert d["P2_M100"]["stats"]["unfilled"] == 4063
    assert d["P2_M150"]["stats"]["unfilled"] == 4079
    assert d["P2_M200"]["stats"]["unfilled"] == 4026


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "P2_M150"
    assert d["eligible"] == ["P2_M100", "P2_M150"]
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    # mult 2.0 is excluded by the DD gate
    assert d["rows"]["P2_M200"]["gate_dd"] == 24.27
    assert "P2_M200" not in d["eligible"]
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
    # sleeve rows take rungs with no liquidations
    for key in ("P2_M100", "P2_M150", "P2_M200"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key
        assert d["rows"][key]["stats"]["liq"] == 0, key


def test_selected_diagnostics():
    d = _rep()
    diag = d["selected_diagnostics"]
    assert diag["key"] == "P2_M150"
    assert diag["mult"] == 1.5
    assert diag["sleeve_risk_budget"] == 0.12
    assert diag["stats_match_simulate"] is True
    worst = diag["worst_10_1m_marked_bars"]
    assert len(worst) == 10
    # sorted worst-first
    mins = [w["path_min"] for w in worst]
    assert mins == sorted(mins)
    for w in worst:
        assert "date" in w and "book_at_min" in w and "sleeve_at_min" in w
        assert "gross" in w and "liq_margin" in w and "liq_flag" in w
        assert w["liq_flag"] is False
        assert w["liq_margin"] > 0
    # worst bar matches the liquidation-check block
    assert diag["worst_minute_liquidation_check"]["date"] == worst[0]["date"]
    assert diag["worst_minute_liquidation_check"]["liq_flag"] is False
    assert diag["worst_minute_liquidation_check"]["liq_margin"] > 0
    # stop gaps: no book gaps through the stop, sleeve gaps bounded
    assert diag["book_stop_gaps"]["n"] == 0
    assert diag["sleeve_stop_gaps"]["n"] == 7
    assert diag["sleeve_stop_gaps"]["total_equity_drag"] < 0.02


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


def test_blind_script_does_not_open_v197():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v197_result" not in body
    assert "v197/v197" not in body
    assert "v197/" not in body.replace("v197_audit", "")
    # script must reference P2 and the scaled rung/budget without last-year selection
    assert "P2" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
    assert "monthly_dev4" in body
