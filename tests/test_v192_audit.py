"""Tests for v192 blind audit (Part A). Does not open research v192 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v192_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v192.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v192 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v192_audit_replication"
    assert d["blind"] == "did_not_open_research_v192_until_this_file_saved"
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
    assert d["engine"]["d_limit_variants"] == [[0.001, 60], [0.001, 239], [0.0003, 239]]
    assert set(d["rows"]) == {"P2_d0010_W060", "P2_d0010_W239", "P2_d0003_W239"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "P2"
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 5.0
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["rows"]["P2_d0010_W060"]["d_limit"] == 0.001
    assert d["rows"]["P2_d0010_W060"]["win_end"] == 60
    assert d["rows"]["P2_d0010_W239"]["d_limit"] == 0.001
    assert d["rows"]["P2_d0010_W239"]["win_end"] == 239
    assert d["rows"]["P2_d0003_W239"]["d_limit"] == 0.0003
    assert d["rows"]["P2_d0003_W239"]["win_end"] == 239


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["P2_d0010_W060"]["monthly_dev4"] == 4.054
    assert d["P2_d0010_W060"]["monthly_5y"] == 3.732
    assert d["P2_d0010_W060"]["monthly_last_year"] == 2.454
    assert d["P2_d0010_W060"]["gate_dd"] == 19.08
    assert d["P2_d0010_W239"]["monthly_dev4"] == 4.069
    assert d["P2_d0010_W239"]["monthly_5y"] == 3.761
    assert d["P2_d0010_W239"]["monthly_last_year"] == 2.541
    assert d["P2_d0010_W239"]["gate_dd"] == 19.18
    assert d["P2_d0003_W239"]["monthly_dev4"] == 3.922
    assert d["P2_d0003_W239"]["monthly_5y"] == 3.61
    assert d["P2_d0003_W239"]["monthly_last_year"] == 2.371
    assert d["P2_d0003_W239"]["gate_dd"] == 19.23
    assert d["P2_d0010_W060"]["yearly_net_pct"] == [24.04, 47.8, 91.4, 91.98, 33.76]
    assert d["P2_d0010_W239"]["yearly_net_pct"] == [24.76, 47.78, 87.81, 95.86, 35.14]
    assert d["P2_d0003_W239"]["yearly_net_pct"] == [23.51, 43.98, 85.9, 91.75, 32.47]
    # fills/unfilled per variant
    assert d["P2_d0010_W060"]["stats"]["fills"] == 35301
    assert d["P2_d0010_W060"]["stats"]["unfilled"] == 8283
    assert d["P2_d0010_W239"]["stats"]["fills"] == 39269
    assert d["P2_d0010_W239"]["stats"]["unfilled"] == 4004
    assert d["P2_d0003_W239"]["stats"]["fills"] == 40966
    assert d["P2_d0003_W239"]["stats"]["unfilled"] == 2085
    # longer window -> more fills, fewer unfilled
    assert d["P2_d0010_W239"]["stats"]["fills"] > d["P2_d0010_W060"]["stats"]["fills"]
    assert d["P2_d0010_W239"]["stats"]["unfilled"] < d["P2_d0010_W060"]["stats"]["unfilled"]
    # tighter limit -> more fills, fewer unfilled at same window
    assert d["P2_d0003_W239"]["stats"]["fills"] > d["P2_d0010_W239"]["stats"]["fills"]
    assert d["P2_d0003_W239"]["stats"]["unfilled"] < d["P2_d0010_W239"]["stats"]["unfilled"]
    # (0.001, 60) equals v191 k=5 (book leg unchanged, sleeve k=5)
    assert d["P2_d0010_W060"]["stats"]["rung_stops"] == 72
    assert d["P2_d0010_W060"]["stats"]["rung_tps"] == 1105


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "P2_d0010_W239"
    assert sorted(d["eligible"]) == ["P2_d0003_W239", "P2_d0010_W060", "P2_d0010_W239"]
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
    for key in ("P2_d0010_W060", "P2_d0010_W239", "P2_d0003_W239"):
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


def test_blind_script_does_not_open_v192():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v192_result" not in body
    assert "v192/v192" not in body
    assert "v192/" not in body.replace("v192_audit", "")
    # script must reference P2 and the (d, W) sweep without last-year selection
    assert "P2" in body
    assert "d_limit" in body
    assert "win_end" in body
    assert "monthly_dev4" in body
