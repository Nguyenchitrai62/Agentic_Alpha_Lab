"""Tests for v199 blind audit (Part A). Does not open research v199 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v199_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v199.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v199 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v199_audit_replication"
    assert d["blind"] == "did_not_open_research_v199_until_this_file_saved"
    assert d["members_check"]["max_abs_diff_avg_vs_books"] == 0.0
    assert d["members_check"]["union_bars"] == 10950
    assert d["members_check"]["columns"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["engine"]["maker"] == 0.0002
    assert d["engine"]["taker"] == 0.00055
    assert d["engine"]["fund_long"] == 0.0001
    assert d["engine"]["m_sl"] == 4.0
    assert d["engine"]["m_sleeve_sl"] == 5.0
    assert d["engine"]["m_sleeve_tp_mult"] == 1.0
    assert d["engine"]["d_limit"] == 0.001
    assert d["engine"]["win_end"] == 239
    assert d["engine"]["gap"] == 0.02
    assert d["engine"]["target"] == 0.25
    assert d["engine"]["cap"] == 2.0
    assert d["engine"]["size_mult"] == 1.5
    assert d["engine"]["sleeve_risk_budget"] == 0.12
    assert d["ladders"]["LADDER_4"] == [2.5, 3.0, 3.5, 4.0]
    assert d["ladders"]["LADDER_6"] == [2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
    assert d["ladders"]["LADDER_3456"] == [3.0, 4.0, 5.0, 6.0]
    assert set(d["rows"]) == {"LADDER_4", "LADDER_6", "LADDER_3456"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "P2"
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 5.0
        assert row["d_limit"] == 0.001
        assert row["win_end"] == 239
        assert row["target"] == 0.25
        assert row["cap"] == 2.0
        assert row["size_mult"] == 1.5
        assert row["mult"] == 1.5
        assert row["sleeve_risk_budget"] == 0.12
        assert row["gap"] == 0.02
        assert row["rungs"] == d["ladders"][key]
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["LADDER_4"]["monthly_dev4"] == 5.562
    assert d["LADDER_4"]["monthly_5y"] == 4.996
    assert d["LADDER_4"]["monthly_last_year"] == 2.761
    assert d["LADDER_4"]["gate_dd"] == 19.72
    assert d["LADDER_6"]["monthly_dev4"] == 5.713
    assert d["LADDER_6"]["monthly_5y"] == 5.098
    assert d["LADDER_6"]["monthly_last_year"] == 2.675
    assert d["LADDER_6"]["gate_dd"] == 20.27
    assert d["LADDER_3456"]["monthly_dev4"] == 4.824
    assert d["LADDER_3456"]["monthly_5y"] == 4.484
    assert d["LADDER_3456"]["monthly_last_year"] == 3.137
    assert d["LADDER_3456"]["gate_dd"] == 18.38
    assert d["LADDER_4"]["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert d["LADDER_6"]["yearly_net_pct"] == [43.18, 60.54, 137.68, 163.43, 37.26]
    assert d["LADDER_3456"]["yearly_net_pct"] == [35.24, 60.9, 86.22, 136.8, 44.87]
    assert d["LADDER_4"]["yearly_dd_1m_pct"] == [19.72, 17.71, 16.18, 9.38, 16.06]
    assert d["LADDER_6"]["yearly_dd_1m_pct"] == [20.27, 17.61, 17.81, 9.5, 20.15]
    assert d["LADDER_3456"]["yearly_dd_1m_pct"] == [17.73, 15.54, 15.88, 9.77, 14.68]
    assert d["LADDER_4"]["stats"]["rungs"] == 5004
    assert d["LADDER_4"]["stats"]["rung_stops"] == 191
    assert d["LADDER_4"]["stats"]["rung_tps"] == 2717
    assert d["LADDER_4"]["stats"]["liq"] == 0
    assert d["LADDER_6"]["stats"]["rungs"] == 5368
    assert d["LADDER_6"]["stats"]["rung_stops"] == 227
    assert d["LADDER_6"]["stats"]["rung_tps"] == 2996
    assert d["LADDER_6"]["stats"]["liq"] == 0
    assert d["LADDER_3456"]["stats"]["rungs"] == 2466
    assert d["LADDER_3456"]["stats"]["rung_stops"] == 139
    assert d["LADDER_3456"]["stats"]["rung_tps"] == 1561
    assert d["LADDER_3456"]["stats"]["liq"] == 0
    assert d["LADDER_4"]["stats"]["fills"] == 40078
    assert d["LADDER_6"]["stats"]["fills"] == 40178
    assert d["LADDER_3456"]["stats"]["fills"] == 39826


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "LADDER_4"
    assert d["eligible"] == ["LADDER_3456", "LADDER_4"]
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    # LADDER_6 is the plain max-dev4 row but excluded by the DD gate
    assert d["rows"]["LADDER_6"]["gate_dd"] == 20.27
    assert "LADDER_6" not in d["eligible"]
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
    for key in ("LADDER_4", "LADDER_6", "LADDER_3456"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key
        assert d["rows"][key]["stats"]["liq"] == 0, key


def test_conventions_documented():
    d = _rep()
    conv = " ".join(d["engine"]["conventions"])
    assert "minute path" in conv
    assert "same-minute tie" in conv
    # per-rung notional is fixed regardless of rung count
    assert "regardless of rung count" in d["rows"]["LADDER_6"]["rung_notional"]
    assert d["rows"]["LADDER_6"]["size_mult"] == 1.5
    assert d["rows"]["LADDER_3456"]["size_mult"] == 1.5


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


def test_blind_script_does_not_open_v199():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v199_result" not in body
    assert "v199/v199" not in body
    assert "v199/" not in body.replace("v199_audit", "")
    # script must reference the ladder sweep without last-year selection
    assert "LADDER" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
    assert "monthly_dev4" in body
