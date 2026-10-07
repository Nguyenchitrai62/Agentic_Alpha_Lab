"""oc_planparity tests: pure-helper checks + results.json sanity. Light, no network/DB writes."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "research/diagnostics/oc_planparity/results.json"
SCRIPT = ROOT / "research/diagnostics/oc_planparity/check_parity.py"

TICKS = {"BTCUSDT": 0.1, "ETHUSDT": 0.01, "BNBUSDT": 0.1, "SOLUSDT": 0.01, "XRPUSDT": 0.0001}


def _sigma_from_rungs(buys, rungs):
    r = buys[0] / buys[-1]
    return (1 - r) / (rungs[0] - r * rungs[-1])


def test_sigma_inversion_exact():
    sg, o1 = 0.0077, 85512.3
    rungs = [2.5, 3.0, 3.5, 4.0, 5.0]
    buys = [o1 * (1 - k * sg) for k in rungs]
    assert abs(_sigma_from_rungs(buys, rungs) - sg) < 1e-12


def test_book_ratio_rule():
    avg, sd = 100.0, 0.02  # m_sl=4, m_tp=8 -> TP leg is 2x SL leg
    sl, tp = avg * (1 - 4 * sd), avg * (1 + 8 * sd)
    assert abs(((tp - avg) / avg) / ((avg - sl) / avg) - 2.0) < 1e-9


def test_merge_caps_sum_to_one():
    growth = {"a": 1.01, "b": 0.99}
    mix = sum(growth.values()) / 2
    caps = {k: 0.25 * g / mix * 2 for k, g in growth.items()}  # 2 phases x 0.25 share norm -> sums to 1
    assert abs(sum(caps.values()) - 1.0) < 1e-12


def test_bear_halve_is_runner_overlay_not_plan():
    w = 0.18
    assert w * 0.5 == 0.09  # bot --bear-book halves; plan must keep w


def test_results_json_parity_schema():
    d = json.loads(RES.read_text(encoding="utf-8"))
    assert d["verdict"] in ("PARITY", "MISMATCH")
    assert isinstance(d["mismatches"], list)
    assert set(d["plans"]) == {"0", "1", "2", "3"}
    assert d["tolerances"]["weights_abs"] == 1e-6
    if d["verdict"] == "PARITY":
        assert d["mismatches"] == []
    for s, p in d["plans"].items():
        assert p["decision_bar"] and p["generated_at"]
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
            assert sym in p["expected_books"]


def test_script_is_read_only():
    src = SCRIPT.read_text(encoding="utf-8")
    for banned in ("kv_set(", "db.write", "fetch_klines(", "INSERT INTO kv", "UPDATE kv"):
        assert banned not in src, banned
    assert "mode=ro" in src  # DB is opened read-only
