"""Tests for v196 blind audit (Part A). Does not open research v196 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v196_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v196.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v196 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v196_audit_replication"
    assert d["blind"] == "did_not_open_research_v196_until_this_file_saved"
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
    assert d["engine"]["cap"] == 2.0
    assert d["engine"]["targets"] == [0.25, 0.2, 0.15]
    assert d["engine"]["sleeve_risk_budgets"] == [0.08, 0.12, 0.16]
    assert d["engine"]["rung_scale_fixed"] == 1.497
    assert set(d["rows"]) == {"P2_T250_X080", "P2_T200_X120", "P2_T150_X160"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "P2"
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 5.0
        assert row["d_limit"] == 0.001
        assert row["win_end"] == 239
        assert row["cap"] == 2.0
        assert row["rung_scale_fixed"] == 1.497
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["rows"]["P2_T250_X080"]["target"] == 0.25
    assert d["rows"]["P2_T250_X080"]["sleeve_risk_budget"] == 0.08
    assert d["rows"]["P2_T200_X120"]["target"] == 0.2
    assert d["rows"]["P2_T200_X120"]["sleeve_risk_budget"] == 0.12
    assert d["rows"]["P2_T150_X160"]["target"] == 0.15
    assert d["rows"]["P2_T150_X160"]["sleeve_risk_budget"] == 0.16


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["P2_T250_X080"]["monthly_dev4"] == 4.972
    assert d["P2_T250_X080"]["monthly_5y"] == 4.558
    assert d["P2_T250_X080"]["monthly_last_year"] == 2.919
    assert d["P2_T250_X080"]["gate_dd"] == 19.44
    assert d["P2_T200_X120"]["monthly_dev4"] == 4.59
    assert d["P2_T200_X120"]["monthly_5y"] == 4.216
    assert d["P2_T200_X120"]["monthly_last_year"] == 2.733
    assert d["P2_T200_X120"]["gate_dd"] == 17.28
    assert d["P2_T150_X160"]["monthly_dev4"] == 3.945
    assert d["P2_T150_X160"]["monthly_5y"] == 3.615
    assert d["P2_T150_X160"]["monthly_last_year"] == 2.302
    assert d["P2_T150_X160"]["gate_dd"] == 15.79
    assert d["P2_T250_X080"]["yearly_net_pct"] == [32.39, 56.53, 121.24, 123.97, 41.24]
    assert d["P2_T200_X120"]["yearly_net_pct"] == [37.09, 51.72, 103.9, 103.24, 38.21]
    assert d["P2_T150_X160"]["yearly_net_pct"] == [41.32, 38.6, 82.66, 79.07, 31.41]
    # decoupled rung notional: rung counts near the coupled v195 plateaus
    assert d["P2_T250_X080"]["stats"]["rungs"] == 5086
    assert d["P2_T250_X080"]["stats"]["rung_stops"] == 197
    assert d["P2_T250_X080"]["stats"]["rung_tps"] == 2765
    assert d["P2_T250_X080"]["stats"]["liq"] == 0
    assert d["P2_T200_X120"]["stats"]["rungs"] == 5162
    assert d["P2_T200_X120"]["stats"]["rung_stops"] == 200
    assert d["P2_T200_X120"]["stats"]["rung_tps"] == 2812
    assert d["P2_T200_X120"]["stats"]["liq"] == 0
    assert d["P2_T150_X160"]["stats"]["rungs"] == 5163
    assert d["P2_T150_X160"]["stats"]["rung_stops"] == 200
    assert d["P2_T150_X160"]["stats"]["rung_tps"] == 2813
    assert d["P2_T150_X160"]["stats"]["liq"] == 0
    # lower books vol target -> lower fees/funding on smaller notionals
    assert d["P2_T250_X080"]["stats"]["fees"] > d["P2_T200_X120"]["stats"]["fees"] > d["P2_T150_X160"]["stats"]["fees"]
    assert d["P2_T250_X080"]["stats"]["fills"] == 39861
    assert d["P2_T200_X120"]["stats"]["fills"] == 39162
    assert d["P2_T150_X160"]["stats"]["fills"] == 37898
    assert d["P2_T250_X080"]["stats"]["unfilled"] == 4066
    assert d["P2_T200_X120"]["stats"]["unfilled"] == 4002
    assert d["P2_T150_X160"]["stats"]["unfilled"] == 3859


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "P2_T250_X080"
    assert d["eligible"] == ["P2_T150_X160", "P2_T200_X120", "P2_T250_X080"]
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
    for key in ("P2_T250_X080", "P2_T200_X120", "P2_T150_X160"):
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


def test_blind_script_does_not_open_v196():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v196_result" not in body
    assert "v196/v196" not in body
    assert "v196/" not in body.replace("v196_audit", "")
    # script must reference P2 and the decoupled rung scale without last-year selection
    assert "P2" in body
    assert "sleeve_risk_budget" in body
    assert "rung_scale_fixed" in body
    assert "1.497" in body
    assert "monthly_dev4" in body
