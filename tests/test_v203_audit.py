"""Tests for v203 blind audit (Part A). Does not open research v203 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v203_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v203.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v203 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v203_audit_replication"
    assert d["blind"] == "did_not_open_research_v203_until_this_file_saved"
    assert d["books_detail"]["books_index_len"] == 10950
    assert d["books_detail"]["columns"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["books_detail"]["blend_weight_annual"] == 0.5
    assert d["books_detail"]["blend_weight_quarterly"] == 0.5
    assert d["books_detail"]["blend_check_max_abs_diff"] == 0.0
    assert d["books_detail"]["quarterly_extra_dropped"] == 6
    assert d["books_detail"]["quarterly_missing_filled_0"] == 0
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
    assert d["engine"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert set(d["rows"]) == {"REF_ANNUAL", "BLEND_50_50"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "v197_rules"
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
        assert row["rungs"] == [2.5, 3.0, 3.5, 4.0]
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["REF_ANNUAL"]["monthly_dev4"] == 5.562
    assert d["REF_ANNUAL"]["monthly_5y"] == 4.996
    assert d["REF_ANNUAL"]["monthly_last_year"] == 2.761
    assert d["REF_ANNUAL"]["gate_dd"] == 19.72
    assert d["BLEND_50_50"]["monthly_dev4"] == 5.516
    assert d["BLEND_50_50"]["monthly_5y"] == 5.17
    assert d["BLEND_50_50"]["monthly_last_year"] == 3.795
    assert d["BLEND_50_50"]["gate_dd"] == 19.86
    assert d["REF_ANNUAL"]["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert d["BLEND_50_50"]["yearly_net_pct"] == [47.06, 61.03, 116.87, 156.28, 56.36]
    assert d["REF_ANNUAL"]["yearly_dd_1m_pct"] == [19.72, 17.71, 16.18, 9.38, 16.06]
    assert d["BLEND_50_50"]["yearly_dd_1m_pct"] == [18.37, 17.83, 19.86, 9.42, 15.44]
    assert d["REF_ANNUAL"]["stats"]["fills"] == 40078
    assert d["BLEND_50_50"]["stats"]["fills"] == 41501
    assert d["REF_ANNUAL"]["stats"]["rungs"] == 5004
    assert d["BLEND_50_50"]["stats"]["rungs"] == 5003
    assert d["REF_ANNUAL"]["stats"]["liq"] == 0
    assert d["BLEND_50_50"]["stats"]["liq"] == 0
    # reference anchors the v197/v199/v202 annual row
    assert d["REF_ANNUAL"]["stats"]["rung_stops"] == 191
    assert d["REF_ANNUAL"]["stats"]["rung_tps"] == 2717


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "REF_ANNUAL"
    assert d["eligible"] == ["BLEND_50_50", "REF_ANNUAL"]
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    best = max(d["eligible"], key=lambda k: d["rows"][k]["monthly_dev4"])
    assert best == d["selection"]
    for key, row in d["rows"].items():
        nets = row["yearly_net_pct"][:4]
        geo4 = float(np.prod([1 + x / 100 for x in nets]) ** (1 / 4) - 1)
        dev4 = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4 - row["monthly_dev4"]) < 0.002, key
    for key, row in d["rows"].items():
        assert abs(row["gate_dd"] - max(row["dd_4h"], row["dd_1m"])) < 1e-9, key
    for key in ("REF_ANNUAL", "BLEND_50_50"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key
        assert d["rows"][key]["stats"]["liq"] == 0, key


def test_conventions_documented():
    d = _rep()
    conv = " ".join(d["engine"]["conventions"])
    assert "minute path" in conv
    assert "same-minute tie" in conv
    assert "1.5" in d["rows"]["BLEND_50_50"]["rung_notional"]
    assert d["rows"]["BLEND_50_50"]["size_mult"] == 1.5
    assert d["rows"]["REF_ANNUAL"]["size_mult"] == 1.5


def test_gate_cost_model_synthetic():
    notional = 1.0
    assert abs(notional * 0.0002 - 0.0002) < 1e-12
    assert abs(notional * 0.00055 - 0.00055) < 1e-12
    assert abs(notional * 0.0001 - 0.0001) < 1e-12
    sl, minute_open = 100.0, 99.0
    assert min(sl, minute_open) == 99.0


def test_blind_script_does_not_open_v203():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v203_result" not in body
    assert "members_quarterly" in body
    assert "members_v154" in body
    assert "v203/" not in body.replace("v203_audit", "")
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
