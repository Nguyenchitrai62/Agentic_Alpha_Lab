"""Tests for oc_idea3_carrytier (tiered carry sizing; T1/T2 pre-reg; dev4-only selection)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_idea3_carrytier"
CC = ROOT / "research/tournament/oc_cashcarry"
CCMP = ROOT / "research/tournament/oc_carrycompound"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_prereg_first_lines():
    rep = (HERE / "REPORT.md").read_text().splitlines()
    head = "\n".join(rep[:8])
    assert "PRE-REGISTRATION" in head
    assert "T1" in head and "T2" in head
    assert "0.125" in head and "0.25" in head and "0.375" in head
    assert "2021-2024" in head


def test_baseline_repro_to_digit():
    out = _res()
    exp = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    g0 = out["baseline_repro"]["G2_f0.0"]
    assert g0["R"] == exp["R"] == 5.41 and g0["W"] == exp["W"] and g0["DD"] == exp["DD"]
    assert [yy["R"] for yy in g0["years"]] == [r for r, _ in exp["years"]]
    assert g0["full_path_dd"]["full"] == exp["full_path_dd"] == 16.82
    e25 = json.loads((CCMP / "results.json").read_text())["rows"]["G2_f0.25"]
    f25 = out["baseline_repro"]["G2_flat_f0.25"]
    assert f25["R"] == e25["R"] == 5.634 and f25["W"] == e25["W"] == 2.778
    assert f25["DD"] == e25["DD"] == 16.75
    assert f25["full_path_dd"]["full"] == 16.66


def test_dev4_selection_winner_T1():
    out = _res()
    assert out["meta"]["winner_dev_only"] == "T1"
    t1, t2 = out["dev4"]["T1"], out["dev4"]["T2"]
    assert t1["R"] == 5.941 and t1["W"] == 2.836 and t1["DD"] == 16.75
    assert t2["R"] == 5.85 and t2["W"] == 2.776 and t2["DD"] == 16.75
    for t in (t1, t2):
        assert t["losing"] == 0 and len(t["years"]) == 4
        assert t["DD"] <= 20
    # robust criterion: both eligible, both means >= 5 -> highest dev4 WORST wins
    assert t1["W"] > t2["W"]
    # 2025 scored once, winner only
    y25 = out["year2025_winner_only"]
    assert y25["winner"] == "T1" and "T2" not in y25
    assert y25["T1"]["R"] == 4.694 and y25["T1"]["DD"] == 12.66
    wf = out["winner_full"]
    assert wf["variant"] == "T1" and len(wf["years"]) == 5
    assert wf["R"] == 5.691 and wf["W"] == 2.836 and wf["DD"] == 16.75
    assert wf["losing"] == 0
    assert wf["full_path_dd"]["full"] == 16.66


def test_aggregates_consistent():
    out = _res()
    for sec in ("dev4",):
        for key in ("T1", "T2"):
            r = out[sec][key]
            assert min(y["R"] for y in r["years"]) == r["W"]
            assert max(y["DD"] for y in r["years"]) == r["DD"]
            fac = 1.0
            for y in r["years"]:
                fac *= 1 + y["R"] / 100
            assert abs(fac ** (1 / len(r["years"])) - 1 - r["R"] / 100) < 5e-5
    wf = out["winner_full"]
    fac = 1.0
    for y in wf["years"]:
        fac *= 1 + y["R"] / 100
    assert abs(fac ** (1 / 5) - 1 - wf["R"] / 100) < 5e-5
    # tiny honest lift at flat DD, far from the 8% goal
    assert round(wf["R"] - out["baseline_repro"]["G2_flat_f0.25"]["R"], 3) == 0.057
    assert wf["DD"] == out["baseline_repro"]["G2_flat_f0.25"]["DD"]


def test_tier_census_and_fee_math():
    out = _res()
    assert out["meta"]["tier_census_T1"] == {"0.125": 8, "0.25": 10, "0.375": 15}
    assert out["meta"]["tier_census_T2"] == {"0.125": 8, "0.25": 25}
    cc = json.loads((CC / "results.json").read_text())
    n125 = sum(1 for t in cc["trades"] if t["ann_basis"] < 0.06)
    n25 = sum(1 for t in cc["trades"] if 0.06 <= t["ann_basis"] <= 0.10)
    n375 = sum(1 for t in cc["trades"] if t["ann_basis"] > 0.10)
    assert (n125, n25, n375) == (8, 10, 15)
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9


def test_account_check_envelope():
    out = _res()
    ov = out["account_check"]["overlap_indexed"]
    assert ov["T2"]["max_indexed_spot_cost"] == 1.0
    assert ov["flat0.25"]["max_indexed_spot_cost"] == 1.0
    assert ov["T1"]["max_indexed_spot_cost"] == 1.5  # must borrow -> split capital only


def test_causal_marking_and_no_heavy():
    src = (HERE / "analyze_carrytier.py").read_text()
    assert 'side="left"' in src
    assert "last CLOSED hourly bar strictly" in src
    for bad in ("klines_1m", "_1m.parquet", "intraday_20260924", "aggflow",
                "simulate(", "phase_offset_full", "heavy_slot", "Pool("):
        assert bad not in src, bad
    q = pd.read_parquet(ROOT / "data/raw/qbasis_20261003/um_BTCUSDT_241227_1h.parquet",
                        columns=["open_time", "close"])
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    qn = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    H = pd.Timestamp("2024-12-27 07:00", tz="UTC").value
    idx = int(np.searchsorted(qn, H, side="left") - 1)
    assert qn[idx] < H


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    for needle in ("5.941", "5.691", "16.75", "16.66", "+0.057", "1.50",
                   "POST-HOC", "REJECT", "TU CHOI"):
        assert needle in rep, needle
