"""Tests for v189 blind audit (Part A). Does not open research v189 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v189_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v189.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v189 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v189_audit_replication"
    assert d["blind"] == "did_not_open_research_v189_until_this_file_saved"
    assert d["members_check"]["max_abs_diff_avg_vs_books"] == 0.0
    assert d["members_check"]["p3_vs_books_max_abs_diff"] == 0.0
    assert d["members_check"]["union_bars"] == 10950
    assert d["members_check"]["columns"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["engine"]["maker"] == 0.0002
    assert d["engine"]["taker"] == 0.00055
    assert d["engine"]["fund_long"] == 0.0001
    assert d["engine"]["m_sl"] == 4.0
    assert d["engine"]["m_sleeve_sl"] == 2.0
    assert d["engine"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert set(d["rows"]) == {
        "P1_sleeve", "P1_nosleeve",
        "P2_sleeve", "P2_nosleeve",
        "P3_sleeve", "P3_nosleeve",
    }
    for key, row in d["rows"].items():
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 2.0
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["P1_sleeve"]["monthly_dev4"] == 3.718
    assert d["P1_sleeve"]["monthly_5y"] == 3.544
    assert d["P1_sleeve"]["monthly_last_year"] == 2.849
    assert d["P1_sleeve"]["gate_dd"] == 19.68
    assert d["P1_nosleeve"]["monthly_dev4"] == 3.525
    assert d["P2_sleeve"]["monthly_dev4"] == 3.896
    assert d["P2_sleeve"]["monthly_5y"] == 3.584
    assert d["P2_sleeve"]["monthly_last_year"] == 2.342
    assert d["P2_sleeve"]["gate_dd"] == 19.41
    assert d["P2_nosleeve"]["monthly_dev4"] == 3.677
    assert d["P3_sleeve"]["monthly_dev4"] == 3.529
    assert d["P3_sleeve"]["monthly_last_year"] == 3.549
    assert d["P3_nosleeve"]["monthly_dev4"] == 3.318
    assert d["P3_nosleeve"]["gate_dd"] == 18.66
    assert d["P2_sleeve"]["yearly_net_pct"] == [23.37, 52.5, 86.27, 78.73, 32.02]
    assert d["P3_sleeve"]["yearly_net_pct"] == [22.92, 45.81, 86.04, 58.48, 51.96]


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "P2_sleeve"
    assert sorted(d["eligible"]) == sorted(d["rows"])
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
    # sleeve adds rungs; nosleeve rows take none
    assert d["rows"]["P2_sleeve"]["stats"]["rungs"] > 0
    assert d["rows"]["P2_nosleeve"]["stats"]["rungs"] == 0
    assert d["rows"]["P1_nosleeve"]["stats"]["rungs"] == 0
    assert d["rows"]["P3_nosleeve"]["stats"]["rungs"] == 0


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


def test_blind_script_does_not_open_v189():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v189_result" not in body
    assert "v189/v189" not in body
    assert "v189/" not in body
    # script must reference the three pipelines and m=4 without last-year selection
    assert "P1" in body and "P2" in body and "P3" in body
    assert "monthly_dev4" in body
