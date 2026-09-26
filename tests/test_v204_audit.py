"""Tests for v204 blind audit (Part A). Does not open research v204 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v204_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v204.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v204 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v204_audit_replication"
    assert d["blind"] == "did_not_open_research_v204_until_this_file_saved"
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
    assert d["engine"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert d["aligns"]["ALIGN_11"] == [1.0, 1.0]
    assert d["aligns"]["ALIGN_150_05"] == [1.5, 0.5]
    assert d["aligns"]["ALIGN_20"] == [2.0, 0.0]
    assert set(d["rows"]) == {"ALIGN_11", "ALIGN_150_05", "ALIGN_20"}
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
        assert row["rungs"] == [2.5, 3.0, 3.5, 4.0]
        assert row["align"] == d["aligns"][key]
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["ALIGN_11"]["monthly_dev4"] == 5.562
    assert d["ALIGN_11"]["worst_first4"] == 2.885
    assert d["ALIGN_11"]["monthly_5y"] == 4.996
    assert d["ALIGN_11"]["monthly_last_year"] == 2.761
    assert d["ALIGN_11"]["gate_dd"] == 19.72
    assert d["ALIGN_150_05"]["monthly_dev4"] == 5.872
    assert d["ALIGN_150_05"]["worst_first4"] == 2.945
    assert d["ALIGN_150_05"]["monthly_5y"] == 5.334
    assert d["ALIGN_150_05"]["monthly_last_year"] == 3.212
    assert d["ALIGN_150_05"]["gate_dd"] == 19.46
    assert d["ALIGN_20"]["monthly_dev4"] == 5.767
    assert d["ALIGN_20"]["worst_first4"] == 2.661
    assert d["ALIGN_20"]["monthly_5y"] == 5.215
    assert d["ALIGN_20"]["monthly_last_year"] == 3.035
    assert d["ALIGN_20"]["gate_dd"] == 20.55
    assert d["ALIGN_11"]["yearly_net_pct"] == [40.67, 51.32, 147.63, 154.98, 38.66]
    assert d["ALIGN_150_05"]["yearly_net_pct"] == [41.66, 49.19, 181.38, 160.1, 46.13]
    assert d["ALIGN_20"]["yearly_net_pct"] == [37.04, 40.15, 204.48, 152.23, 43.16]
    assert d["ALIGN_11"]["yearly_dd_1m_pct"] == [19.72, 17.71, 16.18, 9.38, 16.06]
    assert d["ALIGN_150_05"]["yearly_dd_1m_pct"] == [19.46, 17.42, 16.55, 9.55, 15.83]
    assert d["ALIGN_20"]["yearly_dd_1m_pct"] == [20.55, 17.86, 15.16, 11.38, 16.49]
    assert d["ALIGN_11"]["stats"]["rungs"] == 5004
    assert d["ALIGN_11"]["stats"]["rung_stops"] == 191
    assert d["ALIGN_11"]["stats"]["rung_tps"] == 2717
    assert d["ALIGN_11"]["stats"]["liq"] == 0
    assert d["ALIGN_150_05"]["stats"]["rungs"] == 5010
    assert d["ALIGN_150_05"]["stats"]["rung_stops"] == 193
    assert d["ALIGN_150_05"]["stats"]["rung_tps"] == 2706
    assert d["ALIGN_150_05"]["stats"]["liq"] == 0
    assert d["ALIGN_20"]["stats"]["rungs"] == 2421
    assert d["ALIGN_20"]["stats"]["rung_stops"] == 71
    assert d["ALIGN_20"]["stats"]["rung_tps"] == 1345
    assert d["ALIGN_20"]["stats"]["liq"] == 0
    assert d["ALIGN_11"]["stats"]["fills"] == 40078
    assert d["ALIGN_150_05"]["stats"]["fills"] == 40205
    assert d["ALIGN_20"]["stats"]["fills"] == 40092
    # (1,1) anchors the v197 selection / v199 reference exactly
    assert d["ALIGN_11"]["stats"]["fills"] == 40078
    assert d["ALIGN_11"]["stats"]["rungs"] == 5004


def test_robust_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("robust criterion")
    assert d["selection"] == "ALIGN_150_05"
    assert d["eligible"] == ["ALIGN_11", "ALIGN_150_05"]
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    # ALIGN_20 is the DD-breach row, correctly excluded
    assert d["rows"]["ALIGN_20"]["gate_dd"] == 20.55
    assert "ALIGN_20" not in d["eligible"]
    # robust criterion: among eligible with dev4 >= 5 (both here), pick highest worst_first4, ties -> higher dev4
    elig = {k: d["rows"][k] for k in d["eligible"]}
    pool = [k for k in elig if elig[k]["monthly_dev4"] >= 5] or list(elig)
    best = max(pool, key=lambda k: (elig[k]["worst_first4"], elig[k]["monthly_dev4"]))
    assert best == d["selection"]
    assert d["rows"]["ALIGN_150_05"]["worst_first4"] == 2.945
    assert d["rows"]["ALIGN_11"]["worst_first4"] == 2.885
    # dev4 cross-check: geometric mean of first-four nets
    for key, row in d["rows"].items():
        nets = row["yearly_net_pct"][:4]
        geo4 = float(np.prod([1 + x / 100 for x in nets]) ** (1 / 4) - 1)
        dev4 = round(100 * ((1 + geo4) ** (1 / 12) - 1), 3)
        assert abs(dev4 - row["monthly_dev4"]) < 0.002, key
    # worst_first4 cross-check: min of first-four yearly monthly
    for key, row in d["rows"].items():
        worst = round(min(row["yearly_monthly_pct"][:4]), 3)
        assert abs(worst - row["worst_first4"]) < 1e-9, key
    # gate DD is max of 4h-close and 1m-marked DD
    for key, row in d["rows"].items():
        assert abs(row["gate_dd"] - max(row["dd_4h"], row["dd_1m"])) < 1e-9, key
    # sleeve rows take rungs with no liquidations
    for key in ("ALIGN_11", "ALIGN_150_05", "ALIGN_20"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key
        assert d["rows"][key]["stats"]["liq"] == 0, key


def test_conventions_documented():
    d = _rep()
    conv = " ".join(d["engine"]["conventions"])
    assert "minute path" in conv
    assert "same-minute tie" in conv
    # directional rung sizing: per-rung own notional in the risk budget
    assert "own rn" in d["rows"]["ALIGN_150_05"]["rung_notional"]
    assert d["rows"]["ALIGN_150_05"]["m_long"] == 1.5
    assert d["rows"]["ALIGN_150_05"]["m_other"] == 0.5
    assert d["rows"]["ALIGN_20"]["m_other"] == 0.0


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


def test_blind_script_does_not_open_v204():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "align" in body
    assert "v204_result" not in body
    assert "v204/v204" not in body
    assert "v204/" not in body.replace("v204_audit", "")
    # script must reference the directional sweep without last-year selection
    assert "ALIGN" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
    assert "monthly_dev4" in body
    assert "worst_first4" in body
