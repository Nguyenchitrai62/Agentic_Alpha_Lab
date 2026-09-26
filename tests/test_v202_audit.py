"""Tests for v202 blind audit (Part A). Does not open research v202 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v202_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v202.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v202 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v202_audit_replication"
    assert d["blind"] == "did_not_open_research_v202_until_this_file_saved"
    assert len(d["quarterly_anchors"]) == 20
    assert d["quarterly_anchors"][0] == "2021-09-24"
    assert d["quarterly_anchors"][1] == "2021-12-24"
    assert d["quarterly_anchors"][-1] == "2026-06-24"
    assert d["quarterly_next"]["2021-09-24"] == "2021-12-24"
    assert d["quarterly_next"]["2026-06-24"] == "2026-09-24"
    assert d["cutoffs"]["v92_embargo_bars"] == 102
    assert d["cutoffs"]["v94_embargo_bars"] == 144
    assert d["cutoffs"]["v103_embargo_bars"] == 78
    assert d["cutoffs"]["vol_embargo_bars"] == 102
    for member in ("A", "B"):
        r = d["rebuild"][member]
        assert r["rebuild_anchors"] == ["2021-09-24", "2021-12-24"]
        assert r["common_bars"] == 1086
        assert r["max_abs_diff_vs_cache"] == 0.0
        assert r["mean_abs_diff_vs_cache"] == 0.0
        assert r["match"] is True
    assert d["members_check"]["annual_shape"] == [10950, 15]
    assert d["members_check"]["quarterly_shape"] == [10956, 10]
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
    assert set(d["rows"]) == {"annual_(A+B)/2", "quarterly_(Aq+Bq)/2"}
    for key, row in d["rows"].items():
        assert row["sleeve"] is True
        assert row["m_sl"] == 4.0
        assert row["m_sleeve_sl"] == 5.0
        assert row["d_limit"] == 0.001
        assert row["win_end"] == 239
        assert row["target"] == 0.25
        assert row["cap"] == 2.0
        assert row["size_mult"] == 1.5
        assert row["sleeve_risk_budget"] == 0.12
        assert row["gap"] == 0.02
        assert row["rungs"] == [2.5, 3.0, 3.5, 4.0]
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_pipeline_rows():
    d = _rep()["rows"]
    ann = d["annual_(A+B)/2"]
    assert ann["monthly_dev4"] == 5.562
    assert ann["monthly_5y"] == 4.996
    assert ann["monthly_last_year"] == 2.761
    assert ann["gate_dd"] == 19.72
    assert ann["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert ann["yearly_dd_1m_pct"] == [19.72, 17.71, 16.18, 9.38, 16.06]
    assert ann["stats"]["fills"] == 40078
    assert ann["stats"]["rungs"] == 5004
    assert ann["stats"]["rung_stops"] == 191
    assert ann["stats"]["rung_tps"] == 2717
    assert ann["stats"]["liq"] == 0
    q = d["quarterly_(Aq+Bq)/2"]
    # blind native-index evaluation (6 extra quarterly bars vs driver alignment)
    assert q["monthly_dev4"] == 5.29
    assert q["monthly_5y"] == 5.094
    assert q["monthly_last_year"] == 4.314
    assert q["gate_dd"] == 22.47
    assert q["yearly_net_pct"] == [49.6, 61.63, 95.59, 151.09, 66.0]
    assert q["yearly_dd_1m_pct"] == [17.37, 18.1, 22.47, 11.19, 15.31]
    assert q["stats"]["stops"] == 90
    assert q["stats"]["tps"] == 43
    assert q["stats"]["rungs"] == 5007
    assert q["stats"]["rung_stops"] == 193
    assert q["stats"]["liq"] == 0
    # annual anchors the v197/v199 reference row
    assert ann["stats"]["unfilled"] == 4079
    assert ann["stats"]["stops"] == 76
    assert ann["stats"]["tps"] == 48


def test_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("best monthly_dev4")
    assert d["selection"] == "annual_(A+B)/2"
    assert d["eligible"] == ["annual_(A+B)/2"]
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    # quarterly is excluded by the DD gate despite higher 5y
    assert d["rows"]["quarterly_(Aq+Bq)/2"]["gate_dd"] == 22.47
    assert "quarterly_(Aq+Bq)/2" not in d["eligible"]
    best = max(d["eligible"], key=lambda k: d["rows"][k]["monthly_dev4"])
    assert best == d["selection"]
    for key, row in d["rows"].items():
        nets = row["yearly_net_pct"][:4]
        geo4 = float(np.prod([1 + x / 100 for x in nets]) ** (1 / 4) - 1)
        dev4 = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4 - row["monthly_dev4"]) < 0.002, key
    for key, row in d["rows"].items():
        assert abs(row["gate_dd"] - max(row["dd_4h"], row["dd_1m"])) < 1e-9, key
    for key in ("annual_(A+B)/2", "quarterly_(Aq+Bq)/2"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key
        assert d["rows"][key]["stats"]["liq"] == 0, key


def test_conventions_documented():
    d = _rep()
    conv = " ".join(d["engine"]["conventions"])
    assert "minute path" in conv
    assert "same-minute tie" in conv
    assert "1.5" in d["engine"]["v197_rules"]
    assert d["rows"]["annual_(A+B)/2"]["size_mult"] == 1.5
    assert d["rows"]["quarterly_(Aq+Bq)/2"]["size_mult"] == 1.5


def test_gate_cost_model_synthetic():
    notional = 1.0
    assert abs(notional * 0.0002 - 0.0002) < 1e-12
    assert abs(notional * 0.00055 - 0.00055) < 1e-12
    assert abs(notional * 0.0001 - 0.0001) < 1e-12
    sl, minute_open = 100.0, 99.0
    assert min(sl, minute_open) == 99.0


def test_blind_script_does_not_open_v202():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v202_result" not in body
    assert "members_quarterly" in body
    assert "members_v154" in body
    assert "v202/" not in body.replace("v202_audit", "")
    assert "quarterly" in body
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
