"""Tests for v187 blind audit (Part A). Does not open research v187 result."""
import json
from pathlib import Path

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v187_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v187.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v187 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v187_audit_replication"
    assert d["blind"] == "did_not_open_research_v187_until_this_file_saved"
    assert d["S_REF"] == 1.657
    assert abs(d["N_MAX"] - 0.05 / 0.30) < 1e-12
    assert d["margin"] == 10.0
    assert d["members_check"]["max_abs_diff_avg_vs_books"] == 0.0
    assert d["members_check"]["union_bars"] == 10950
    assert d["spec"]["symbols"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["spec"]["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert d["counts_grid"]["fills_total"] == 6972
    assert d["counts_grid"]["tp_fills"] == 4053
    assert set(d["rows"]) == {
        "conf_normal", "conf_stress",
        "flat4_normal", "flat4_stress",
        "flat2_normal", "flat2_stress",
    }


def test_agree_cap_distribution():
    d = _rep()
    assert abs(d["agree"]["live_mean"] - 0.9142) < 1e-4
    conf = d["rows"]["conf_normal"]["cap_distribution"]
    assert conf["cap2_bars"] == 714
    assert conf["cap3_bars"] == 495
    assert conf["cap4_bars"] == 9735
    assert abs(conf["mean_cap"] - 3.8243) < 1e-4
    assert d["rows"]["flat4_normal"]["cap_distribution"]["mean_cap"] == 4.0
    assert d["rows"]["flat2_normal"]["cap_distribution"]["mean_cap"] == 2.0


def test_confidence_rows():
    d = _rep()["rows"]
    assert d["conf_normal"]["monthly_pct"] == 4.331
    assert d["conf_normal"]["full_path_dd"] == 18.69
    assert d["conf_normal"]["dd_1m_mark"] == 18.96
    assert d["conf_normal"]["gate_dd"] == 18.96
    assert d["conf_normal"]["dd_1m_worst_bar"] == "2022-04-21 16:00:00+00:00"
    assert d["conf_normal"]["worst_bar"]["time"] == "2024-03-05 12:00:00+00:00"
    assert d["conf_normal"]["liquidations"] == 0
    assert d["conf_normal"]["mean_s"] == 1.724
    assert d["conf_stress"]["monthly_pct"] == 3.925
    assert d["conf_stress"]["full_path_dd"] == 18.76
    assert d["conf_stress"]["dd_1m_mark"] == 19.03
    assert d["conf_stress"]["liquidations"] == 0
    nets = {y["anchor"][:4]: y["net_pct"] for y in d["conf_normal"]["yearly"]}
    assert nets == {"2021": 33.04, "2022": 50.57, "2023": 118.32, "2024": 79.57, "2025": 62.13}


def test_flat_rows():
    d = _rep()["rows"]
    assert d["flat4_normal"]["monthly_pct"] == 4.307
    assert d["flat4_normal"]["full_path_dd"] == 18.69
    assert d["flat4_normal"]["dd_1m_mark"] == 18.96
    assert d["flat4_normal"]["liquidations"] == 0
    assert d["flat2_normal"]["monthly_pct"] == 4.293
    assert d["flat2_normal"]["full_path_dd"] == 18.75
    assert d["flat2_normal"]["dd_1m_mark"] == 19.01
    assert d["flat2_normal"]["liquidations"] == 0
    assert d["flat2_stress"]["monthly_pct"] == 3.885
    assert d["flat2_stress"]["full_path_dd"] == 18.87
    assert d["flat2_stress"]["dd_1m_mark"] == 19.13
    assert d["flat4_stress"]["monthly_pct"] == 3.907
    # flat2 with 10x matches the v183 5x base within 0.01pp (budget rarely binds)
    assert abs(d["flat2_normal"]["monthly_pct"] - 4.284) < 0.02


def test_liquidation_math_synthetic():
    # fut_eq = eq_min - prev*c*expo/1.2; mm = 0.01*prev*(|w| + c*expo/1.2 + rn*n)
    prev, eq_min, c, expo = 1.0, 0.99, 0.5, 0.8
    w_abs, rn, n = 0.6, 0.06, 2
    fut = eq_min - prev * c * expo / 1.2
    mm = 0.01 * prev * (w_abs + c * expo / 1.2 + rn * n)
    assert abs(fut - 0.6566667) < 1e-6
    assert abs(mm - 0.0105333) < 1e-6
    assert fut > mm  # no breach in this synthetic bar
    # agree/cap boundaries
    assert (2 if 0.59 < 0.6 else 3) == 2
    assert (3 if 0.6 < 0.8 else 4) == 3
    assert (4 if 0.8 >= 0.8 else 3) == 4


def test_blind_script_does_not_open_v187():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "engine_real" in body
    assert "v187_result" not in body
    assert "v187_confidence" not in body
    assert "confidence_leverage" not in body
    assert "v187/v187" not in body
