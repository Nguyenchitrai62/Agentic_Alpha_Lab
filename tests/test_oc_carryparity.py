"""Tests for oc_carryparity (frozen-rule parity audit, no network)."""

import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_carryparity"


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "oc_carryparity_mod", str(HERE / "check_parity.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_basis_math_handcheck():
    m = _load_mod()
    # ETH retry 09:14 recomputed from its S/F entries (~3.8%/yr, below gate)
    b = m.annualised_basis(2737.67, 2714.995, 79.99)
    assert abs(b - 0.03797) < 0.001, b
    assert m.decide(b) == "skip"
    assert m.decide(0.053098) == "enter"
    assert m.decide(0.04) == "enter"
    assert m.decide(0.0399) == "skip"


def test_quarterly_filter():
    m = _load_mod()
    assert m.is_quarterly_delivery(1798185600000) is True  # 2026-12-25 Fri
    assert m.is_quarterly_delivery(1774041600000) is False  # 2026-10-09 Fri weekly
    assert m.is_quarterly_delivery(1774656000000) is False  # 2026-11-27 monthly


def test_rule_identity_with_carry_paper():
    m = _load_mod()
    spec = importlib.util.spec_from_file_location(
        "carry_paper_rule", str(ROOT / "scripts" / "carry_paper.py"))
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    assert cp.RULE_PARAMS == m.RULE_PARAMS
    assert cp.rule_sha256() == m.rule_sha_of(m.RULE_PARAMS)


def test_causal_kline_mapping():
    m = _load_mod()
    bars = [(1000, 1.0), (1000 + 3600000, 2.0)]
    # bar closes at open+1h; at the exact open of the 2nd bar only the 1st is closed
    assert m.last_closed(bars, 1000 + 3600000) == (1000, 1.0)
    # one minute after the 2nd bar closes, the 2nd is the last closed
    assert m.last_closed(bars, 1000 + 2 * 3600000 + 60_000) == (1000 + 3600000, 2.0)
    assert m.last_closed(bars, 999) is None


def test_results_contract_and_known_deviation():
    out = _res()
    assert out["meta"]["delivery_ms"] == 1798185600000
    assert out["meta"]["rule_matches_carry_paper"] is True
    dec = out["decisions"]
    # live-growing: the paper/bot ledgers keep appending (144 at REPORT time
    # 2026-10-06 16:38 -> 145 at the 17:07 rerun -> more since). The count
    # only moves out; the invariants below are the real checks.
    n = len(dec)
    assert n == out["summary"]["n_decisions"] >= 144
    assert all(d["contract_ok"] for d in dec)
    assert out["summary"]["contract_ok"] == f"{n}/{n}"
    below = out["summary"]["entered_below_threshold"]
    # the known 09:14 ETH retry entered below 4%/yr must still be flagged
    assert any(b["coin"] == "ETH" and b["source"] == "bot_d17bfg2c"
               and abs(b["ledger_basis"] - 0.038) < 0.001 for b in below)
    for b in below:
        assert b["ledger_basis"] < 0.04
    # paper first decisions: BTC enter, then ETH skips (earliest 6 rows are
    # the frozen snapshot; later paper rows may follow as the loop appends).
    paper = sorted((d for d in dec if d["source"] == "paper_carry"),
                   key=lambda d: d["t"])
    assert len(paper) >= 6
    assert paper[0]["coin"] == "BTC" and paper[0]["ledger_decision"] == "enter"
    assert all(d["coin"] == "ETH" and d["ledger_decision"] == "skip"
               for d in paper[1:6])


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    out = _res()
    assert "PARITY HOLDS with one known bug" in rep
    assert "144/144" in rep
    assert "3.80%/yr" in rep or "3.8%/yr" in rep
    assert "mid-vs-last" in rep or "mid vs last" in rep.lower()
    assert "25DEC26" in (HERE / "check_parity.py").read_text()
