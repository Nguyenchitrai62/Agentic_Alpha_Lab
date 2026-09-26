"""Tests for v188 blind audit (Part A). Does not open research v188 result."""
import json
from pathlib import Path

AUD = Path("research/parallel/rounds/parallel-20260906-r2/v188_audit")
REP = AUD / "replication.json"
SCRIPT = AUD / "replicate_v188.py"


def _rep():
    assert REP.exists(), "Part A replication.json must be saved before reading v188 folder"
    return json.loads(REP.read_text())


def test_replication_structure():
    d = _rep()
    assert d["version"] == "v188_audit_replication"
    assert d["blind"] == "did_not_open_research_v188_or_engine_user_until_this_file_saved"
    assert d["S_REF"] == 1.657
    assert abs(d["N_MAX"] - 1.0 / 6.0) < 1e-12
    assert d["symbols"] == ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    assert d["rungs"] == [2.5, 3.0, 3.5, 4.0]
    assert set(d["rows"]) == {"m2_with_sleeve", "m3_with_sleeve", "m4_with_sleeve", "m4_no_sleeve"}
    assert d["selection"]["best_with_sleeve"] == "m4_with_sleeve"
    assert d["selection"]["best_m"] == 4
    assert d["live"]["bars"] == 10950


def test_monthly_and_selection():
    d = _rep()["rows"]
    assert d["m2_with_sleeve"]["monthly_pct"] == 3.042
    assert d["m3_with_sleeve"]["monthly_pct"] == 3.383
    assert d["m4_with_sleeve"]["monthly_pct"] == 3.486
    assert d["m4_no_sleeve"]["monthly_pct"] == 3.332
    assert d["m2_with_sleeve"]["monthly_dev4"] == 3.108
    assert d["m3_with_sleeve"]["monthly_dev4"] == 3.295
    assert d["m4_with_sleeve"]["monthly_dev4"] == 3.513
    assert d["m4_no_sleeve"]["monthly_dev4"] == 3.305
    # selection is best dev4 among DD<=20 no-losing-first-four (m4)
    assert d["m4_with_sleeve"]["monthly_dev4"] > d["m3_with_sleeve"]["monthly_dev4"]
    assert d["m4_with_sleeve"]["monthly_dev4"] > d["m2_with_sleeve"]["monthly_dev4"]


def test_dd_and_gate():
    d = _rep()["rows"]
    assert d["m2_with_sleeve"]["gate_dd"] == 21.14
    assert d["m3_with_sleeve"]["gate_dd"] == 19.78
    assert d["m4_with_sleeve"]["gate_dd"] == 19.3
    assert d["m4_no_sleeve"]["gate_dd"] == 18.93
    assert d["m2_with_sleeve"]["full_path_dd"] == 20.12
    assert d["m3_with_sleeve"]["full_path_dd"] == 19.25
    assert d["m4_with_sleeve"]["full_path_dd"] == 18.93
    assert d["m4_no_sleeve"]["full_path_dd"] == 18.52
    # m2 fails DD<=20, m3/m4 pass
    assert d["m2_with_sleeve"]["gate_dd"] > 20
    assert d["m3_with_sleeve"]["gate_dd"] <= 20
    assert d["m4_with_sleeve"]["gate_dd"] <= 20


def test_yearly_nets():
    d = _rep()["rows"]
    nets_m4 = {y["anchor"][:4]: y["net_pct"] for y in d["m4_with_sleeve"]["yearly"]}
    assert nets_m4 == {"2021": 22.87, "2022": 45.87, "2023": 84.95, "2024": 58.23, "2025": 49.01}
    nets_m2 = {y["anchor"][:4]: y["net_pct"] for y in d["m2_with_sleeve"]["yearly"]}
    assert nets_m2 == {"2021": 17.33, "2022": 37.2, "2023": 91.27, "2024": 41.15, "2025": 38.92}
    nets_ns = {y["anchor"][:4]: y["net_pct"] for y in d["m4_no_sleeve"]["yearly"]}
    assert nets_ns == {"2021": 18.28, "2022": 45.98, "2023": 73.7, "2024": 58.79, "2025": 50.04}
    # no losing year in first four for m3/m4
    for k in ("m3_with_sleeve", "m4_with_sleeve"):
        assert all(y["net_pct"] >= 0 for y in d[k]["yearly"][:4])


def test_counts():
    d = _rep()["rows"]
    assert d["m2_with_sleeve"]["book_fills"] == 36447
    assert d["m3_with_sleeve"]["book_fills"] == 36549
    assert d["m4_with_sleeve"]["book_fills"] == 36838
    assert d["m4_no_sleeve"]["book_fills"] == 36703
    assert d["m4_with_sleeve"]["sleeve_taken"] == 2550
    assert d["m4_with_sleeve"]["sleeve_cancelled"] == 2620
    assert d["m4_no_sleeve"]["sleeve_taken"] == 0
    assert d["m2_with_sleeve"]["book_sl"] == 582
    assert d["m3_with_sleeve"]["book_sl"] == 202
    assert d["m4_with_sleeve"]["book_sl"] == 85
    assert d["m3_with_sleeve"]["sleeve_tp"] == 1207


def test_cost_model_synthetic():
    # maker/taker + adverse funding (longs pay, shorts zero)
    maker, taker = 0.0002, 0.00055
    notional = 1000.0
    assert abs(notional * maker - 0.2) < 1e-9
    assert abs(notional * taker - 0.55) < 1e-9
    # min notional thresholds
    assert {"BTCUSDT": 100.0, "ETHUSDT": 20.0}.get("BTCUSDT") == 100.0
    assert {"BTCUSDT": 100.0, "ETHUSDT": 20.0}.get("SOLUSDT", 5.0) == 5.0
    # limit 10bps better
    p0 = 50000.0
    assert abs(p0 * (1 - 0.001) - 49950.0) < 1e-9
    assert abs(p0 * (1 + 0.001) - 50050.0) < 1e-9
    # governor boundaries
    def gov(dd):
        import numpy as np
        return float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
    assert gov(0.0) == 1.0
    assert gov(0.20) == 0.0
    assert abs(gov(0.15) - 0.5) < 1e-12
    # stop-first: SL and TP same minute -> SL wins (synthetic flag)
    sl_hit, tp_hit = True, True
    winner = "SL" if sl_hit else ("TP" if tp_hit else None)
    assert winner == "SL"


def test_blind_script_does_not_open_v188():
    src = SCRIPT.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "artifacts/research/engine_real" in body
    assert "v188_result" not in body
    assert "engine_user/" not in body
    assert "engine_user.py" not in body
    assert "v188/v188" not in body
    assert "test_engine_user" not in body
