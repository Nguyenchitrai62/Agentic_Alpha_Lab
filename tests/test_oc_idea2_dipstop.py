"""Tests for oc_idea2_dipstop (fast: artifact consistency + selection math + synthetic)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_idea2_dipstop"
sys.path.insert(0, str(HERE))
from run_dipstop import RUNS, rank_key

REF = "R2B1D17BFG2"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_only_preregistered_variants():
    assert set(RUNS) == {"G2_P1", "G2_P2"}
    assert RUNS["G2_P1"] == dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, xrp=5.5, rest=4.0)
    assert RUNS["G2_P2"] == dict(rule="inv", k=1.0, kd=1.7, bear=True, G=2.0, xrp=5.5, rest=4.5)
    res = _res()
    assert res["meta"]["prereg"] == ["G2_P1: XRP5.5/rest4.0", "G2_P2: XRP5.5/rest4.5"]
    assert set(res["dev4"]) == {REF, "G2_P1", "G2_P2"}


def test_baseline_reproduced_to_digit():
    res = _res()
    assert res["baseline"]["G2"] == {"R": 5.41, "W": 2.588, "DD": 16.91, "full_path_dd": 16.82}
    assert res["baseline"]["G2_carry_f025"] == {"R": 5.634, "W": 2.778, "DD": 16.75, "full_path_dd": 16.66}
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"][REF]
    assert (exp["R"], exp["W"], exp["DD"], exp["full_path_dd"]) == (5.41, 2.588, 16.91, 16.82)
    cc = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())["rows"]["G2_f0.25"]
    assert (cc["R"], cc["W"], cc["DD"], cc["full_path_dd"]["full"]) == (5.634, 2.778, 16.75, 16.66)


def test_dev4_aggregates_consistent():
    res = _res()
    for row, m in res["dev4"].items():
        assert len(m["years"]) == 4
        assert m["W"] == min(r for r, _ in m["years"])
        assert m["DD"] == max(d for _, d in m["years"])
        assert m["losing"] == sum(r < 0 for r, _ in m["years"])
        fac = 1.0
        for r, _ in m["years"]:
            fac *= 1 + r / 100
        assert abs(fac ** (1 / 4) - 1 - m["R"] / 100) < 5e-5


def test_winner_is_robust_criterion_argmax():
    res = _res()
    assert res["winner"] == max(RUNS, key=lambda r: rank_key(res["dev4"][r]))
    assert res["winner"] == "G2_P2"
    # robust criterion: eligible (DD<=20, no losing), R>=5 both, highest WORST wins
    p1, p2 = res["dev4"]["G2_P1"], res["dev4"]["G2_P2"]
    for m in (p1, p2):
        assert m["DD"] <= 20 and m["losing"] == 0 and m["R"] >= 5
    assert p2["W"] > p1["W"]


def test_most_recent_year_only_for_winner():
    res = _res()
    assert set(res["y2025_posthoc"]) == {REF, res["winner"]}
    assert set(res["full_path_dd"]) == {REF, res["winner"]}
    assert res["slip_S4_dev4"] is not None and res["slip_S4_dev4"]["losing"] == 0


def test_folds_no_transfer():
    res = _res()
    assert set(res["folds"]) == {"2", "3", "4"}
    assert all(f["good"] is False for f in res["folds"].values())


def test_rank_key_orders_robust_criterion():
    a = {"R": 5.6, "W": 2.6, "DD": 16.9, "losing": 0}   # eligible, R>=5
    b = {"R": 5.7, "W": 2.5, "DD": 16.9, "losing": 0}   # higher mean, lower worst
    c = {"R": 4.9, "W": 3.0, "DD": 16.9, "losing": 0}   # below 5 floor
    d = {"R": 9.0, "W": 9.0, "DD": 21.0, "losing": 0}   # DD breach
    assert max(("a", "b"), key=lambda k: rank_key({"a": a, "b": b}[k])) == "a"
    assert rank_key(a) > rank_key(c) > rank_key(d)


def test_per_coin_stop_mapping():
    src = (HERE / "run_dipstop.py").read_text()
    assert "sleeve_sl_coin" in src and "sleeve_gross_cap" in src
    assert 'pipe_setup("v321"' in src and "win_start=5" in src
    assert "stop_slip" in src and "event_study" not in src  # engine-judged, never a vectorised screen
    # synthetic hook: XRP gets xrp, every other coin the rest distance
    xa, x, b = 4, 5.5, 4.0
    f = lambda i, a, xa=xa, x=x, b=b: x if a == xa else b  # noqa: E731 - mirrors the script
    assert f(0, xa) == 5.5 and all(f(0, a) == 4.0 for a in range(5) if a != xa)


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    for needle in ("G2_P1", "G2_P2", "5.601", "5.618", "5.606", "16.82", "16.80",
                   "POST-HOC", "REJECT", "Tu choi"):
        assert needle in rep, needle
