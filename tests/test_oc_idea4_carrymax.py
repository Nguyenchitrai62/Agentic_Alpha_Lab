"""Tests for oc_idea4_carrymax (max-basis single-coin carry)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_idea4_carrymax"
CC = ROOT / "research/tournament/oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_prereg_names_only_m1_m2():
    rep = (HERE / "REPORT.md").read_text()
    head = "\n".join(rep.splitlines()[:20])
    assert "M1 max-coin only" in head
    assert "M2 max-coin with 4.5" in head
    assert "no other variants" in head.lower()


def test_baselines_reproduced_to_digit():
    out = _res()
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json")
                     .read_text())["rows"]["R2B1D17BFG2"]
    g0 = out["baseline_G2_f0"]
    assert g0["R"] == exp["R"] and g0["W"] == exp["W"] and g0["DD"] == exp["DD"]
    assert [yy["R"] for yy in g0["years"]] == [r for r, _ in exp["years"]]
    assert [yy["DD"] for yy in g0["years"]] == [d for _, d in exp["years"]]
    assert g0["full_path_dd"]["full"] == exp["full_path_dd"]
    ref = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json")
                     .read_text())["rows"]["G2_f0.25"]
    c33 = out["baseline_FULL33_f025"]
    assert c33["R"] == ref["R"] == 5.634
    assert c33["W"] == ref["W"] == 2.778
    assert c33["DD"] == ref["DD"] == 16.75
    assert c33["full_path_dd"]["full"] == ref["full_path_dd"]["full"] == 16.66


def test_maxcoin_subsets_causal_and_sized():
    out = _res()
    cc = json.loads((CC / "results.json").read_text())
    by = {(t["coin"], t["delivery"]): t for t in cc["trades"]}
    m1 = [tuple(x) for x in out["meta"]["m1_trades"]]
    m2 = [tuple(x) for x in out["meta"]["m2_trades"]]
    assert len(m1) == 18 and len(m2) == 16 and set(m2) < set(m1)
    # per delivery: M1 holds the max entry-basis coin; all kept pass 4 %
    seen: dict[str, list] = {}
    for c, d, b in m1:
        assert by[(c, d)]["ann_basis"] == b >= 0.04 - 1e-9
        assert by[(c, d)]["ret_alloc"] > 0
        seen.setdefault(d, []).append(b)
    for d, bs in seen.items():
        both = [t["ann_basis"] for t in cc["trades"] if t["delivery"] == d]
        assert bs == [max(both)]  # the higher locked basis only
    # M2 floor: drops exactly the sub-4.5 % picks
    assert sorted(out["meta"]["m2_floor_drops"]) == sorted(
        [list(k) for k in (("BTC", "2023-12-29"), ("BTC", "2026-03-27"))])
    for c, d, b in m2:
        assert b >= 0.045 - 1e-12


def test_selection_dev_only_and_recent_once():
    out = _res()
    assert out["choice"]["winner"] == "M1"
    assert out["dev_M1_f025"]["R"] == 5.744
    assert out["dev_M2_f025"]["R"] == 5.739
    # robust criterion on dev: same DD/no-loser, M1 higher mean wins ties
    assert out["dev_M1_f025"]["DD"] <= 20 and out["dev_M1_f025"]["losing"] == 0
    assert out["dev_M2_f025"]["DD"] <= 20 and out["dev_M2_f025"]["losing"] == 0
    assert out["dev_M1_f025"]["W"] == out["dev_M2_f025"]["W"] == 2.682
    # dev rows cover exactly anchors 2021-2024; loser has no 2025 row
    assert [y["anchor"] for y in out["dev_M1_f025"]["years"]] == \
        ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
    assert [y["anchor"] for y in out["dev_M2_f025"]["years"]] == \
        ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
    assert "chosen_M2_f025" not in out
    ch = out["chosen_M1_f025"]
    assert [y["anchor"] for y in ch["years"]] == \
        ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    assert [y.get("post_hoc", False) for y in ch["years"]] == \
        [False, False, False, False, True]
    assert ch["R"] == 5.531 and ch["W"] == 2.682 and ch["DD"] == 16.75
    assert ch["full_path_dd"]["full"] == 16.66


def test_aggregates_consistent():
    out = _res()
    for key in ("baseline_G2_f0", "baseline_FULL33_f025", "chosen_M1_f025"):
        r = out[key]
        assert min(y["R"] for y in r["years"]) == r["W"]
        assert max(y["DD"] for y in r["years"]) == r["DD"]
        assert r["losing"] == sum(y["R"] < 0 for y in r["years"])
        fac = 1.0
        for y in r["years"]:
            fac *= 1 + y["R"] / 100
        assert abs(fac ** (1 / len(r["years"])) - 1 - r["R"] / 100) < 5e-5
    # max-coin earns less than both-coins on dev and 5y, same DD
    assert out["chosen_M1_f025"]["R"] < out["baseline_FULL33_f025"]["R"]
    assert out["dev_M1_f025"]["R"] < 5.870  # frozen FULL33 dev4 mean
    assert out["chosen_M1_f025"]["full_path_dd"] == \
        out["baseline_FULL33_f025"]["full_path_dd"]


def test_concurrency_bound_no_borrow():
    out = _res()
    for tag in ("M1", "M2"):
        c = out["concurrency"][tag]
        assert c["peak_concurrent_pairs"] == 2
        assert c["peak_spot_cash_x_equity_at_f025"] == 0.5
        assert c["peak_spot_cash_x_equity_at_f025"] <= 1.0


def test_no_heavy_markers():
    src = (HERE / "analyze_carrymax.py").read_text()
    assert 'side="left"' in src  # causal hourly marks
    for bad in ("klines_1m", "_1m.parquet", "intraday_20260924", "aggflow",
                "simulate(", "phase_offset_full", "heavy_slot", "Pool("):
        assert bad not in src, bad


def test_report_complete():
    rep = (HERE / "REPORT.md").read_text()
    for needle in ("reset_metric", "full-path DD", "16.66", "POST-HOC",
                    "maker 0.02", "0.055", "NO funding", "REJECT",
                    "Ket luan tieng Viet"):
        assert needle in rep, needle
