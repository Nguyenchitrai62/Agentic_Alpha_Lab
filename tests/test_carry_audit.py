"""Tests for the blind cash-carry audit (OPENCODE_CARRY_AUDIT).

Covers PART A replication integrity (window, causality, fees, formulas) and
PART B comparison artefacts + overlay/margin code-shape checks. No git writes.
"""
import json
import math
import os

import pandas as pd

REP = "research/tournament/carry_audit/replication.json"
CMP = "research/tournament/carry_audit/COMPARISON.md"
CHK = "research/tournament/carry_audit/checks.json"
CC = "research/tournament/oc_cashcarry/results.json"


def _load_rep():
    assert os.path.exists(REP), "replication.json must be saved FIRST (blind)"
    with open(REP) as fh:
        return json.load(fh)


def test_replication_exists_and_window():
    d = _load_rep()
    assert d["window_start"].startswith("2021-09-24")
    assert d["window_end"].startswith("2026-09-24")
    assert d["n_trades"] == len(d["trades"]) >= 20
    lo = pd.Timestamp("2021-09-24", tz="UTC")
    hi = pd.Timestamp("2026-09-24", tz="UTC")
    for t in d["trades"]:
        h = pd.Timestamp(t["entry_time"])
        assert lo <= h < hi, t
        assert t["basis_ann"] >= 0.04 - 1e-12, t
        assert t["coin"] in ("BTC", "ETH")


def test_entry_causality_strict():
    d = _load_rep()
    for t in d["trades"]:
        h = pd.Timestamp(t["entry_time"])
        assert pd.Timestamp(t["F_entry_bar"]) < h, t
        assert pd.Timestamp(t["S_entry_bar"]) < h, t


def test_fees_and_formulas():
    d = _load_rep()
    for t in d["trades"]:
        assert abs(t["fees"] - 0.00275) < 1e-12
        r = (t["S_exit"] / t["S_entry"] - 1) + \
            ((t["F_entry"] - t["F_settle"]) / t["F_entry"]) - 0.00275
        assert abs(r - t["return"]) < 1e-9, t
        b = math.log(t["F_entry"] / t["S_entry"]) * 365.0 / t["days_to_delivery"]
        assert abs(b - t["basis_ann"]) < 1e-9, t


def test_per_year_sums_add_up():
    d = _load_rep()
    tot = sum(v["sum_return"] for v in d["per_anchor_year"].values())
    assert abs(tot - d["total_return_sum"]) < 1e-9
    assert sum(v["n_trades"] for v in d["per_anchor_year"].values()) == d["n_trades"]


def test_hand_checked_synthetic_basis():
    # ln(110/100)*365/365 = ln(1.1)
    assert abs(math.log(110.0 / 100.0) * 365.0 / 365.0 - math.log(1.1)) < 1e-12
    # fee drag identity
    assert abs((0.001 + 0.001 + 0.00055 + 0.0002) - 0.00275) < 1e-12


def test_comparison_artefacts_and_verdict():
    assert os.path.exists(CMP) and os.path.exists(CHK)
    with open(CHK) as fh:
        c = json.load(fh)
    assert c["verdict"] in ("carry: PASS", "carry: FAIL")
    with open(CMP) as fh:
        text = fh.read()
    assert c["verdict"] in text
    # comparison ran against real oc_cashcarry results
    assert os.path.exists(CC)
    cc = json.load(open(CC))
    assert cc["pooled"]["n_trades"] == 25


def test_overlay_and_margin_code_shape():
    # overlay arithmetic present verbatim (not reimplemented here)
    src = open("research/tournament/oc_carryd13/combine_carryd13.py").read()
    assert "es_c = es + c" in src and "f * (raw[seg] - raw_at_anchor[y])" in src.replace(
        "cy = f * (raw[seg] - raw_at_anchor[y])", "f * (raw[seg] - raw_at_anchor[y])")
    fric = open("research/tournament/oc_carryfric/combine_carryfric.py").read()
    assert "es_c = es + c" in fric
    uta = open("research/tournament/oc_utamargin/analyze_utamargin.py").read()
    assert "(Gall * Eq_mix + short_not) / LEV" in uta
    assert "HAIRCUT * spot_val" in uta
    assert "im_over_bal > BLOCK_FRAC" in uta or "blocked = im_over_bal > BLOCK_FRAC" in uta
