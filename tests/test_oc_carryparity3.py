"""Tests for oc_carryparity3 (full carry parity audit, no network)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "diagnostics" / "oc_carryparity3"
SCRATCH = ROOT / "research" / "tournament" / "oc_carryparity3" / "tmp"


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "oc_carryparity3_mod", str(HERE / "check_parity.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _res():
    return json.loads((HERE / "results.json").read_text(encoding="utf-8"))


def _tmp_jsonl(name):
    return [json.loads(l) for l in (SCRATCH / name).read_text(
        encoding="utf-8").splitlines() if l.strip()]


def test_basis_math_handcheck():
    m = _load_mod()
    # ETH retry 09:14 recomputed from its own S/F entries (~3.80%/yr, below gate)
    b = m.annualised_basis(2737.67, 2714.995, 79.96)
    assert abs(b - 0.0380) < 0.001, b
    assert m.decide(b) == "skip"
    # BTC retry same stamp is well above the gate
    assert m.decide(m.annualised_basis(86946.1, 85934.15, 79.96)) == "enter"
    assert m.decide(0.053098) == "enter"
    assert m.decide(0.04) == "enter"
    assert m.decide(0.0399) == "skip"


def test_quarterly_filter():
    m = _load_mod()
    assert m.is_quarterly_delivery(1798185600000) is True  # 2026-12-25 Fri
    assert m.is_quarterly_delivery(1774041600000) is False  # weekly
    assert m.is_quarterly_delivery(1774656000000) is False  # monthly


def test_rule_identity_with_frozen_rule():
    m = _load_mod()
    spec = importlib.util.spec_from_file_location(
        "carry_paper_rule", str(ROOT / "scripts" / "carry_paper.py"))
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    out = _res()
    assert out["meta"]["rule_sha256"] == cp.rule_sha256()
    assert out["meta"]["rule_matches_carry_paper"] is True
    # bot/carry.py must import the frozen rule, never re-define it
    src = (ROOT / "bot" / "carry.py").read_text(encoding="utf-8")
    assert "from scripts.carry_paper import" in src
    assert "\nRULE_PARAMS = " not in src and "\nRULE_PARAMS=" not in src
    assert cp.RULE_PARAMS["basis_threshold"] == 0.04
    assert out["meta"]["bot_carry_imports_frozen_rule"] is True


def test_causal_kline_mapping():
    m = _load_mod()
    bars = [(1000, 0, 0, 0, 1.0), (1000 + 3600000, 0, 0, 0, 2.0)]
    assert m.last_closed(bars, 1000 + 3600000) == bars[0]
    assert m.last_closed(bars, 1000 + 2 * 3600000 + 60_000) == bars[1]
    assert m.last_closed(bars, 999) is None


def test_floor_to_step():
    m = _load_mod()
    assert m.floor_to_step(0.01464332949482856, "0.001") == 0.014
    assert m.floor_to_step(0.46086347380452014, "0.01") == 0.46
    assert m.floor_to_step(0.01447856882242904, "0.001") == 0.014
    assert m.floor_to_step(0.0, "0.001") == 0.0


def test_results_cover_every_logged_decision():
    out = _res()
    dec = out["decisions"]
    assert len(dec) == out["summary"]["n_decisions"]
    # every entry/skip in the three scratch copies is covered exactly once
    n_expected, fills_expected = 0, 0
    for name in ("paper_carry_actions.jsonl", "d17bfg2c_actions.jsonl",
                 "g2k20c_actions.jsonl"):
        for r in _tmp_jsonl(name):
            if r.get("op") in ("entry", "skip", "carry_entry", "carry_skip"):
                n_expected += 1
            if r.get("op") == "carry_fill":
                fills_expected += 1
    assert len(dec) == n_expected == 150
    assert out["summary"]["by_source"] == {"paper_carry": 9, "bot_d17bfg2c": 138,
                                          "bot_g2k20c": 3}
    assert len(out["fills"]) == fills_expected == 8
    assert out["summary"]["contract_ok"] == "150/150"
    assert all(d["contract_ok"] for d in dec)


def test_known_retry_deviation_is_the_only_real_bug():
    out = _res()
    real = [m for m in out["mismatches"] if m["class"] == "real_bug"]
    assert len(real) == 1
    assert out["summary"]["n_real_bug"] == 1
    assert real[0]["coin"] == "ETH" and real[0]["source"] == "bot_d17bfg2c"
    assert "gate" in real[0]["cause"]
    assert out["verdict"].startswith("PARITY HOLDS with one known bug")
    assert out["summary"]["carry_abandon"] == 0
    assert out["summary"]["settles"] == 0


def test_fills_and_fees_agree():
    out = _res()
    assert out["summary"]["fills_price_ok"] == "8/8"
    assert out["summary"]["fills_exec_ok"] == "8/8"
    for key in ("bot_d17bfg2c", "bot_g2k20c", "paper_carry"):
        assert out["fees"][key]["fees_ok"] is True, key
    assert abs(out["fees"]["bot_d17bfg2c"]["carry_fee_expected"]
               - 0.98524364) < 1e-8
    assert abs(out["fees"]["bot_g2k20c"]["carry_fee_expected"]
               - 0.98779324) < 1e-8
    assert out["fees"]["paper_carry"]["entry_fees_expected"] == 3.875


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    out = _res()
    assert "PARITY HOLDS with one known bug" in rep
    assert "150/150" in rep
    assert "25DEC26" in rep
    assert "3.80%/yr" in rep
    assert "mid-vs-last" in rep
    vi = out["verdict_vi"]
    assert len([l for l in vi.strip().splitlines() if l.strip()]) == 3
    for line in vi.strip().splitlines():
        assert line.strip() in rep
