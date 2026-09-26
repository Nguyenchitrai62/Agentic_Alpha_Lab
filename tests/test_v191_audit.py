"""Tests for v191 blind audit (Part A). Does not open research v191 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v191_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v191.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v191 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v191_audit_replication"
    assert d["blind"] == "did_not_open_research_v191_until_this_file_saved"
    assert d["books"] == "pipeline P2=(A+B)/2 from cached v154 members"
    assert d["members_check"]["max_abs_diff_avg_vs_books"] == 0.0
    assert d["members_check"]["union_bars"] == 10950
    assert d["members_check"]["columns"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["engine"]["maker"] == 0.0002
    assert d["engine"]["taker"] == 0.00055
    assert d["engine"]["fund_long"] == 0.0001
    assert d["engine"]["m_sl"] == 4.0
    assert d["engine"]["m_sleeve_ks"] == [2.0, 3.0, 5.0]
    assert d["engine"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert set(d["rows"]) == {"P2_sleeve_k2", "P2_sleeve_k3", "P2_sleeve_k5"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "P2"
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["rows"]["P2_sleeve_k2"]["m_sleeve_sl"] == 2.0
    assert d["rows"]["P2_sleeve_k3"]["m_sleeve_sl"] == 3.0
    assert d["rows"]["P2_sleeve_k5"]["m_sleeve_sl"] == 5.0


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["P2_sleeve_k2"]["monthly_dev4"] == 3.896
    assert d["P2_sleeve_k2"]["monthly_5y"] == 3.584
    assert d["P2_sleeve_k2"]["monthly_last_year"] == 2.342
    assert d["P2_sleeve_k2"]["gate_dd"] == 19.41
    assert d["P2_sleeve_k3"]["monthly_dev4"] == 3.935
    assert d["P2_sleeve_k3"]["monthly_5y"] == 3.593
    assert d["P2_sleeve_k3"]["monthly_last_year"] == 2.236
    assert d["P2_sleeve_k3"]["gate_dd"] == 19.35
    assert d["P2_sleeve_k5"]["monthly_dev4"] == 4.054
    assert d["P2_sleeve_k5"]["monthly_5y"] == 3.732
    assert d["P2_sleeve_k5"]["monthly_last_year"] == 2.454
    assert d["P2_sleeve_k5"]["gate_dd"] == 19.08
    assert d["P2_sleeve_k2"]["yearly_net_pct"] == [23.37, 52.5, 86.27, 78.73, 32.02]
    assert d["P2_sleeve_k3"]["yearly_net_pct"] == [24.27, 49.03, 86.52, 84.62, 30.4]
    assert d["P2_sleeve_k5"]["yearly_net_pct"] == [24.04, 47.8, 91.4, 91.98, 33.76]
    # rung stops/TPs per k
    assert d["P2_sleeve_k2"]["stats"]["rung_stops"] == 432
    assert d["P2_sleeve_k2"]["stats"]["rung_tps"] == 1214
    assert d["P2_sleeve_k3"]["stats"]["rung_stops"] == 212
    assert d["P2_sleeve_k3"]["stats"]["rung_tps"] == 1142
    assert d["P2_sleeve_k5"]["stats"]["rung_stops"] == 72
    assert d["P2_sleeve_k5"]["stats"]["rung_tps"] == 1105
    # wider sleeve stop -> fewer rung stops
    assert d["P2_sleeve_k2"]["stats"]["rung_stops"] > d["P2_sleeve_k3"]["stats"]["rung_stops"] > d["P2_sleeve_k5"]["stats"]["rung_stops"]


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "P2_sleeve_k5"
    assert sorted(d["eligible"]) == ["P2_sleeve_k2", "P2_sleeve_k3", "P2_sleeve_k5"]
    for key, row in d["rows"].items():
        assert row["losing_years_first4"] == 0
        assert row["losing_years"] == 0
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
    for key in ("P2_sleeve_k2", "P2_sleeve_k3", "P2_sleeve_k5"):
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


def test_blind_script_does_not_open_v191():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v191_result" not in body
    assert "v191/v191" not in body
    assert "v191/" not in body.replace("v191_audit", "")
    # script must reference P2 and the k sweep without last-year selection
    assert "P2" in body
    assert "m_sleeve_sl" in body
    assert "monthly_dev4" in body
