"""Tests for oc_carrymargin (deployment safety check, no engine reruns).

Verifies results.json schema + arithmetic consistency, hand-checked IM math,
the causal mark convention on a synthetic series, and that the worker script
touches neither artifacts/bot state nor the network.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "research" / "tournament" / "oc_carrymargin"
RES = json.loads((D / "results.json").read_text(encoding="utf-8"))
CUT = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def test_files_exist():
    assert (D / "compute_carrymargin.py").exists()
    assert (D / "REPORT.md").exists()
    assert (D / "results.json").exists()
    assert (D / "tmp").is_dir()


def test_meta_definitions():
    m = RES["meta"]
    assert m["f"] == 0.25
    assert m["leverage_perp"] == 5
    assert m["leverage_carry_base"] == 10
    assert m["haircut_base"] == 0.05
    assert m["haircut_stress"] == 0.10
    assert m["no_engine_reruns"] is True
    assert m["no_network"] is True
    assert m["v421_v422_equity_identical_to_barsum"] == {"v421": True, "v422": True}
    assert m["post_hoc_changes"] == "none"
    assert RES["meta"]["grid"][2] == 43824
    assert pd.Timestamp(RES["meta"]["grid"][0], tz="UTC") >= pd.Timestamp(
        "2021-09-24", tz="UTC")
    assert pd.Timestamp(RES["meta"]["grid"][1], tz="UTC") < CUT


def _check_row(key):
    r = RES[key]
    assert r["n"] == 43824
    assert 0 <= r["mean"] <= r["p99"] <= r["max"] < 1.0
    assert r["n_above_95"] <= r["n_above_80"]
    assert r["share_above_80_pct"] == round(100.0 * r["n_above_80"] / r["n"], 3)
    assert r["share_above_95_pct"] == round(100.0 * r["n_above_95"] / r["n"], 3)


def test_rows_consistent():
    for k in ("G2_alone_f0", "G2_carry_f0.25_usage_eq",
              "G2_carry_f0.25_bal_base5", "G2_carry_f0.25_bal_stress10",
              "G2_carry_f0.25_bal_cons5x_carry"):
        _check_row(k)


def test_no_blocked_hours():
    for k in ("G2_alone_f0", "G2_carry_f0.25_usage_eq",
              "G2_carry_f0.25_bal_base5", "G2_carry_f0.25_bal_stress10",
              "G2_carry_f0.25_bal_cons5x_carry"):
        assert RES[k]["n_above_80"] == 0, k
        assert RES[k]["n_above_95"] == 0, k


def test_ordering_base_stress_conservative():
    b = RES["G2_carry_f0.25_bal_base5"]
    s = RES["G2_carry_f0.25_bal_stress10"]
    c = RES["G2_carry_f0.25_bal_cons5x_carry"]
    e = RES["G2_carry_f0.25_usage_eq"]
    f0 = RES["G2_alone_f0"]
    assert e["max"] >= f0["max"]  # carry adds IM
    assert b["max"] >= e["max"]  # balance <= equity while spot held
    assert s["max"] >= b["max"]  # bigger haircut -> smaller balance
    assert c["max"] >= b["max"]  # carry/5x more IM than carry/10x


def test_conservative_reproduces_utamargin():
    # Independent rebuild on the shared convention must match oc_utamargin
    # f=0.25 (max IM/bal 0.7751, worst hour 2025-09-25 18:00) to the digit.
    c = RES["G2_carry_f0.25_bal_cons5x_carry"]
    assert c["max"] == 0.7751
    w0 = RES["worst5_hours_by_bal_base"][0]
    assert w0["hour"] == "2025-09-25 18:00:00+00:00"
    assert w0["G2_gross_frac"] == 2.8492


def test_worst5_sorted_inside_grid():
    w = RES["worst5_hours_by_bal_base"]
    assert len(w) == 5
    vals = [x["usage_bal_base"] for x in w]
    assert vals == sorted(vals, reverse=True)
    for x in w:
        t = pd.Timestamp(x["hour"], tz="UTC")
        assert pd.Timestamp("2021-09-24", tz="UTC") <= t < CUT
        assert x["usage_bal_stress"] >= x["usage_bal_base"] >= x["usage_eq"]
    assert w[0]["usage_bal_base"] == RES["G2_carry_f0.25_bal_base5"]["max"]


def test_spot_cash_no_borrow():
    sc = RES["spot_cash"]
    assert sc["max_spot_cost_over_Eq"] == 0.9582
    assert sc["n_hours_spot_cost_above_Eq"] == 0
    assert sc["min_cash_headroom_frac"] == round(
        1.0 - sc["max_spot_cost_over_Eq"], 4)


def test_recon_small():
    for s, r in RES["meta"]["recon_vs_barsum_gross_book"].items():
        assert r["median_abs_diff"] < 0.01, s


def test_im_math_hand_checked():
    # Synthetic: G=2.0 Eq_mix=1.0, short=0.5, spot=0.4, carry MtM=0.
    G, Eq, short, spot = 2.0, 1.0, 0.5, 0.4
    im = G * Eq / 5 + short / 10
    assert im == 0.45
    usage_eq = im / Eq
    assert usage_eq == 0.45
    bal = Eq - 0.05 * spot
    assert bal == 0.98
    assert round(im / bal, 4) == 0.4592
    bal_s = Eq - 0.10 * spot
    assert round(im / bal_s, 4) == 0.4688
    # threshold flags
    assert not (im / bal > 0.95) and not (im / bal > 0.80)
    assert (0.96 > 0.95) is True  # sanity on the comparison direction


def test_causal_mark_convention_synthetic():
    # Marks at H must use the last bar STRICTLY before H (never the bar at H).
    bt = np.array([0, 1, 2, 3]) * 3_600_000_000_000
    cl = np.array([10.0, 11.0, 12.0, 13.0])
    H = np.array([1, 2, 3]) * 3_600_000_000_000
    q = H - 3_600_000_000_000
    i = np.searchsorted(bt, q, side="right") - 1
    got = cl[np.maximum(i, 0)]
    assert list(got) == [10.0, 11.0, 12.0]  # bar at H excluded
    # same-timestamp bar must NOT leak into its own hour
    assert got[0] != 11.0


def test_script_touches_no_bot_state_no_network():
    txt = (D / "compute_carrymargin.py").read_text(encoding="utf-8")
    assert "artifacts/bot" not in txt
    assert "urlopen" not in txt and "urllib" not in txt
    assert "BYBIT" not in txt and ".env" not in txt


def test_report_has_verdict_and_worst_hour():
    rep = (D / "REPORT.md").read_text(encoding="utf-8")
    assert "2025-09-25 18:00" in rep
    assert "f=0.25" in rep
    assert "Verdict" in rep
