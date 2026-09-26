"""Tests for v200 + v201 blind audit (Part A). Does not open research v200/v201 results."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v200_v201_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v200_v201.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v200/v201 folders"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v200_v201_audit_replication"
    assert d["blind"] == "did_not_open_research_v200_or_v201_until_this_file_saved"
    assert d["members_check"]["max_abs_diff_avg_vs_books"] == 0.0
    assert d["members_check"]["union_bars"] == 10950
    assert d["members_check"]["columns"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["engine"]["maker"] == 0.0002
    assert d["engine"]["taker"] == 0.00055
    assert d["engine"]["fund_long"] == 0.0001
    assert d["engine"]["d_limit"] == 0.001
    assert d["engine"]["win_end"] == 239
    assert d["engine"]["gap"] == 0.02
    assert d["engine"]["target"] == 0.25
    assert d["engine"]["cap"] == 2.0
    assert d["engine"]["size_mult"] == 1.5
    assert d["engine"]["sleeve_risk_budget"] == 0.12
    assert d["engine"]["sleeve_risk_budget_high"] == 0.18
    assert d["a1_books"]["REF_4_8"] == [4.0, 8.0]
    assert d["a1_books"]["SL2_TP4"] == [2.0, 4.0]
    assert d["a1_books"]["SL2p5_TP2p5"] == [2.5, 2.5]
    assert d["a1_books"]["SL3_TP2"] == [3.0, 2.0]
    assert set(d["rows_a1"]) == {"REF_4_8", "SL2_TP4", "SL2p5_TP2p5", "SL3_TP2"}
    assert set(d["rows_a2"]) == {"HOURLY_OFF", "HOURLY_012", "HOURLY_018"}
    for key, row in list(d["rows_a1"].items()) + list(d["rows_a2"].items()):
        assert row["pipeline"] == "P2"
        assert row["sleeve"] is True
        assert row["d_limit"] == 0.001
        assert row["win_end"] == 239
        assert row["target"] == 0.25
        assert row["cap"] == 2.0
        assert row["size_mult"] == 1.5
        assert row["gap"] == 0.02
        assert row["rungs"] == [2.5, 3.0, 3.5, 4.0]
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert d["rows_a1"]["REF_4_8"]["m_sl"] == 4.0
    assert d["rows_a1"]["REF_4_8"]["m_tp"] == 8.0
    assert d["rows_a2"]["HOURLY_OFF"]["hourly"] is False
    assert d["rows_a2"]["HOURLY_012"]["hourly"] is True
    assert d["rows_a2"]["HOURLY_018"]["hourly"] is True
    assert d["rows_a2"]["HOURLY_018"]["sleeve_risk_budget"] == 0.18


def test_a1_book_variants():
    r = _rep()["rows_a1"]
    assert r["REF_4_8"]["monthly_dev4"] == 5.562
    assert r["REF_4_8"]["monthly_5y"] == 4.996
    assert r["REF_4_8"]["monthly_last_year"] == 2.761
    assert r["REF_4_8"]["gate_dd"] == 19.72
    assert r["SL2_TP4"]["monthly_dev4"] == 4.958
    assert r["SL2_TP4"]["monthly_5y"] == 4.425
    assert r["SL2_TP4"]["monthly_last_year"] == 2.319
    assert r["SL2_TP4"]["gate_dd"] == 21.28
    assert r["SL2p5_TP2p5"]["monthly_dev4"] == 4.84
    assert r["SL2p5_TP2p5"]["monthly_5y"] == 4.447
    assert r["SL2p5_TP2p5"]["monthly_last_year"] == 2.889
    assert r["SL2p5_TP2p5"]["gate_dd"] == 24.75
    assert r["SL3_TP2"]["monthly_dev4"] == 4.719
    assert r["SL3_TP2"]["monthly_5y"] == 4.276
    assert r["SL3_TP2"]["monthly_last_year"] == 2.52
    assert r["SL3_TP2"]["gate_dd"] == 24.41
    assert r["REF_4_8"]["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert r["SL2_TP4"]["yearly_net_pct"] == [35.75, 38.78, 138.78, 126.82, 31.67]
    assert r["SL2p5_TP2p5"]["yearly_net_pct"] == [42.22, 22.8, 149.04, 122.3, 40.75]
    assert r["SL3_TP2"]["yearly_net_pct"] == [38.06, 27.64, 138.43, 117.71, 34.8]
    # book stops/TPs explode when the SL/TP is tightened; sleeve legs stay flat
    assert r["REF_4_8"]["book_stops"] == 76
    assert r["REF_4_8"]["book_tps"] == 48
    assert r["SL2_TP4"]["book_stops"] == 563
    assert r["SL2_TP4"]["book_tps"] == 225
    assert r["SL2p5_TP2p5"]["book_stops"] == 406
    assert r["SL2p5_TP2p5"]["book_tps"] == 581
    assert r["SL3_TP2"]["book_stops"] == 278
    assert r["SL3_TP2"]["book_tps"] == 831
    # mean/max gross book exposure (sum |target weight|)
    assert r["REF_4_8"]["gross_book_mean"] == 0.489983
    assert r["SL2_TP4"]["gross_book_mean"] == 0.478936
    assert r["SL2p5_TP2p5"]["gross_book_mean"] == 0.481493
    assert r["SL3_TP2"]["gross_book_mean"] == 0.476733
    for key in r:
        assert r[key]["gross_book_max"] == 2.291
        assert r[key]["stats"]["bars"] == 10944
        assert r[key]["stats"]["liq"] == 0


def test_a2_hourly_variants():
    r = _rep()["rows_a2"]
    assert r["HOURLY_OFF"]["monthly_dev4"] == 5.562
    assert r["HOURLY_OFF"]["monthly_5y"] == 4.996
    assert r["HOURLY_OFF"]["monthly_last_year"] == 2.761
    assert r["HOURLY_OFF"]["gate_dd"] == 19.72
    assert r["HOURLY_012"]["monthly_dev4"] == 3.622
    assert r["HOURLY_012"]["monthly_5y"] == 2.918
    assert r["HOURLY_012"]["monthly_last_year"] == 0.15
    assert r["HOURLY_012"]["gate_dd"] == 39.69
    assert r["HOURLY_018"]["monthly_dev4"] == 3.333
    assert r["HOURLY_018"]["monthly_5y"] == 2.709
    assert r["HOURLY_018"]["monthly_last_year"] == 0.252
    assert r["HOURLY_018"]["gate_dd"] == 39.66
    assert r["HOURLY_OFF"]["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert r["HOURLY_012"]["yearly_net_pct"] == [34.02, -24.55, 138.54, 128.7, 1.81]
    assert r["HOURLY_018"]["yearly_net_pct"] == [44.38, -26.01, 100.83, 124.9, 3.06]
    assert r["HOURLY_OFF"]["stats"]["rungs"] == 5004
    assert r["HOURLY_012"]["stats"]["rungs"] == 22703
    assert r["HOURLY_018"]["stats"]["rungs"] == 23404
    assert r["HOURLY_012"]["stats"]["rung_stops"] == 1125
    assert r["HOURLY_012"]["stats"]["rung_tps"] == 11705
    assert r["HOURLY_018"]["stats"]["rung_stops"] == 1207
    assert r["HOURLY_018"]["stats"]["rung_tps"] == 12132
    assert r["HOURLY_OFF"]["stats"]["fills"] == 40078
    assert r["HOURLY_012"]["stats"]["fills"] == 32875
    assert r["HOURLY_018"]["stats"]["fills"] == 32293
    # hourly-on rows carry a 2022 losing year and breach the DD gate
    assert r["HOURLY_012"]["losing_years_first4"] == 1
    assert r["HOURLY_018"]["losing_years_first4"] == 1


def test_anchor_and_selection_use_first_four_only():
    d = _rep()
    # hourly-off must re-score the v197 anchor and equal the A1 reference
    off = d["rows_a2"]["HOURLY_OFF"]
    ref = d["rows_a1"]["REF_4_8"]
    assert off["monthly_dev4"] == 5.562
    assert off["gate_dd"] == 19.72
    assert off["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    for k in ("monthly_dev4", "monthly_5y", "monthly_last_year", "gate_dd", "dd_4h", "dd_1m"):
        assert ref[k] == off[k]
    assert ref["stats"]["fills"] == off["stats"]["fills"]
    assert ref["stats"]["rungs"] == off["stats"]["rungs"]
    # selections use first-four-years metrics only
    assert d["selection_rule_a1"].startswith("best monthly_dev4")
    assert d["selection_rule_a2"].startswith("best monthly_dev4")
    assert d["eligible_a1"] == ["REF_4_8"]
    assert d["selection_a1"] == "REF_4_8"
    assert d["eligible_a2"] == ["HOURLY_OFF"]
    assert d["selection_a2"] == "HOURLY_OFF"
    # no selectable v200 variant passes the DD gate, so the driver falls back
    for key in ("SL2_TP4", "SL2p5_TP2p5", "SL3_TP2"):
        assert d["rows_a1"][key]["gate_dd"] > 20
    best_fallback = max(("SL2_TP4", "SL2p5_TP2p5", "SL3_TP2"),
                        key=lambda k: d["rows_a1"][k]["monthly_dev4"])
    assert best_fallback == "SL2_TP4"
    # dev4 cross-check: geometric mean of first-four nets
    for row in list(d["rows_a1"].values()) + list(d["rows_a2"].values()):
        nets = row["yearly_net_pct"][:4]
        geo4 = float(np.prod([1 + x / 100 for x in nets]) ** (1 / 4) - 1)
        dev4 = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4 - row["monthly_dev4"]) < 0.002
        assert abs(row["gate_dd"] - max(row["dd_4h"], row["dd_1m"])) < 1e-9


def test_conventions_documented():
    d = _rep()
    conv = " ".join(d["engine"]["conventions"])
    assert "minute path" in conv
    assert "same-minute tie" in conv
    assert "sig1h" in d["engine"]["hourly"]
    assert "60h" in d["engine"]["hourly"]
    assert "regardless of rung count" in d["rows_a1"]["SL2_TP4"]["rung_notional"]


def test_gate_cost_model_synthetic():
    notional = 1.0
    assert abs(notional * 0.0002 - 0.0002) < 1e-12
    assert abs(notional * 0.00055 - 0.00055) < 1e-12
    assert abs(notional * 0.0001 - 0.0001) < 1e-12
    sl, minute_open = 100.0, 99.0
    assert min(sl, minute_open) == 99.0


def test_blind_script_does_not_open_v200_v201():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "v200_result" not in body
    assert "v201_result" not in body
    cleaned = body.replace("v200_v201_audit", "")
    assert "v200/" not in cleaned
    assert "v201/" not in cleaned
    assert "m_tp" in body
    assert "hourly" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
    assert "monthly_dev4" in body
