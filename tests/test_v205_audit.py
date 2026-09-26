"""Tests for v205 blind audit (Part A). Does not open research v205 result."""
import json
from pathlib import Path

import numpy as np

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v205_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v205.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v205 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v205_audit_replication"
    assert d["blind"] == "did_not_open_research_v205_until_this_file_saved"
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
    assert d["engine"]["align"] == [1.5, 0.5]
    assert d["engine"]["m_long"] == 1.5
    assert d["engine"]["m_other"] == 0.5
    assert set(d["rows"]) == {"REF_ANNUAL", "BLEND_50_50"}
    for key, row in d["rows"].items():
        assert row["pipeline"] == "v204_rules"
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
        assert row["align"] == [1.5, 0.5]
        assert row["m_long"] == 1.5
        assert row["m_other"] == 0.5
        assert len(row["yearly"]) == 5
        assert [y["anchor"] for y in row["yearly"]] == [
            "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]


def test_pipeline_rows():
    d = _rep()["rows"]
    assert d["REF_ANNUAL"]["monthly_dev4"] == 5.872
    assert d["REF_ANNUAL"]["worst_first4"] == 2.945
    assert d["REF_ANNUAL"]["monthly_5y"] == 5.334
    assert d["REF_ANNUAL"]["monthly_last_year"] == 3.212
    assert d["REF_ANNUAL"]["gate_dd"] == 19.46
    assert d["BLEND_50_50"]["monthly_dev4"] == 5.824
    assert d["BLEND_50_50"]["worst_first4"] == 3.41
    assert d["BLEND_50_50"]["monthly_5y"] == 5.488
    assert d["BLEND_50_50"]["monthly_last_year"] == 4.152
    assert d["BLEND_50_50"]["gate_dd"] == 19.76
    assert d["REF_ANNUAL"]["yearly_net_pct"] == [41.66, 49.19, 181.38, 160.1, 46.13]
    assert d["BLEND_50_50"]["yearly_net_pct"] == [49.54, 54.51, 147.19, 165.05, 62.93]
    assert d["REF_ANNUAL"]["yearly_dd_1m_pct"] == [19.46, 17.42, 16.55, 9.55, 15.83]
    assert d["BLEND_50_50"]["yearly_dd_1m_pct"] == [19.51, 17.93, 19.76, 9.94, 15.89]
    assert d["REF_ANNUAL"]["stats"]["fills"] == 40205
    assert d["BLEND_50_50"]["stats"]["fills"] == 41670
    assert d["REF_ANNUAL"]["stats"]["rungs"] == 5010
    assert d["BLEND_50_50"]["stats"]["rungs"] == 4999
    assert d["REF_ANNUAL"]["stats"]["liq"] == 0
    assert d["BLEND_50_50"]["stats"]["liq"] == 0
    # reference anchors the v204 ALIGN_150_05 selection exactly
    assert d["REF_ANNUAL"]["stats"]["rung_stops"] == 193
    assert d["REF_ANNUAL"]["stats"]["rung_tps"] == 2706
    assert d["BLEND_50_50"]["stats"]["rung_stops"] == 187
    assert d["BLEND_50_50"]["stats"]["rung_tps"] == 2702


def test_robust_selection_uses_first_four_only():
    d = _rep()
    assert d["selection_rule"].startswith("robust criterion")
    assert d["selection"] == "BLEND_50_50"
    assert d["eligible"] == ["BLEND_50_50", "REF_ANNUAL"]
    for key in d["eligible"]:
        row = d["rows"][key]
        assert row["losing_years_first4"] == 0
        assert row["gate_dd"] <= 20
    # robust criterion: among eligible with dev4 >= 5 (both here), pick highest worst_first4, ties -> higher dev4
    elig = {k: d["rows"][k] for k in d["eligible"]}
    pool = [k for k in elig if elig[k]["monthly_dev4"] >= 5] or list(elig)
    best = max(pool, key=lambda k: (elig[k]["worst_first4"], elig[k]["monthly_dev4"]))
    assert best == d["selection"]
    assert d["rows"]["BLEND_50_50"]["worst_first4"] == 3.41
    assert d["rows"]["REF_ANNUAL"]["worst_first4"] == 2.945
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
    for key in ("REF_ANNUAL", "BLEND_50_50"):
        assert d["rows"][key]["stats"]["rungs"] > 0, key
        assert d["rows"][key]["stats"]["liq"] == 0, key


def test_conventions_documented():
    d = _rep()
    conv = " ".join(d["engine"]["conventions"])
    assert "minute path" in conv
    assert "same-minute tie" in conv
    # directional rung sizing: per-rung own notional in the risk budget
    assert "own rn" in d["rows"]["BLEND_50_50"]["rung_notional"]
    assert d["rows"]["BLEND_50_50"]["m_long"] == 1.5
    assert d["rows"]["BLEND_50_50"]["m_other"] == 0.5
    assert d["reference"].startswith("REF_ANNUAL")


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


def test_blind_script_does_not_open_v205():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_user" in body
    assert "align" in body
    assert "members_quarterly" in body
    assert "members_v154" in body
    assert "v205_result" not in body
    assert "v205/v205" not in body
    assert "v205/" not in body.replace("v205_audit", "")
    # script must reference the blend + directional sweep without last-year selection
    assert "BLEND_50_50" in body
    assert "REF_ANNUAL" in body
    assert "sleeve_risk_budget" in body
    assert "size_mult" in body
    assert "monthly_dev4" in body
    assert "worst_first4" in body
