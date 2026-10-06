"""Tests for oc_idea6_d13carry (baselines, max-coin causality, dev selection, no-1m)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_idea6_d13carry"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _cc():
    return json.loads((CC / "results.json").read_text())


def _script_src():
    return (HERE / "analyze_d13carry.py").read_text()


def test_baseline_gate_reproduced():
    r = _res()["baseline_checks"]
    assert (r["G2_official"]["R"], r["G2_official"]["W"],
            r["G2_official"]["DD"]) == (5.41, 2.588, 16.91)
    assert r["G2_official"]["full_path_dd"] == 16.82
    assert (r["D13BF_official"]["R"], r["D13BF_official"]["W"],
            r["D13BF_official"]["DD"]) == (4.971, 2.485, 14.98)
    c = r["G2_carrycompound_f0.25"]
    assert (c["R"], c["W"], c["DD"]) == (5.634, 2.778, 16.75)
    assert c["full"] == 16.66 and c["add_pp"] == 0.224
    assert r["bothcoin_d13_f0.25"] == {"R": 5.104, "DD": 14.85}
    assert r["bothcoin_d13_f0.50"] == {"R": 5.234, "DD": 14.71}


def test_maxcoin_frozen_and_causal():
    r, cc = _res(), _cc()
    assert r["maxcoin"]["n_kept"] == 18 and r["maxcoin"]["n_excluded"] == 15
    assert len(cc["trades"]) == 33
    by_del: dict[str, list[dict]] = {}
    for t in cc["trades"]:
        by_del.setdefault(t["delivery"], []).append(t)
    kept = {(t["coin"], t["delivery"]) for t in r["maxcoin"]["kept"]}
    for dl, ts in by_del.items():
        if len(ts) == 2:
            best = max(ts, key=lambda t: (t["ann_basis"], t["ret_alloc"]))
            assert (best["coin"], best["delivery"]) in kept
            for t in ts:
                assert t["ann_basis"] >= 0.04 - 1e-9  # entry-known filter only
    for t in r["maxcoin"]["kept"]:
        assert t["ret_alloc"] > 0


def test_dev_selection_only_and_winner():
    r = _res()
    assert r["winner"] == "S1"
    assert [y["anchor"] for y in r["S1_dev_years"]] == [
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
    dev = r["S1_dev4"]
    Rs = [y["R"] for y in r["S1_dev_years"]]
    assert min(Rs) == dev["W"] and max(
        y["DD"] for y in r["S1_dev_years"]) == dev["DD"]
    fac = float(np.prod([1 + x / 100 for x in Rs]))
    assert abs(fac ** (1 / 4) - 1 - dev["R"] / 100) < 5e-5
    assert dev["DD"] <= 20 and dev["losing"] == 0 and dev["R"] >= 5
    # S2 pre-registered but NOT scored (no numbers invented)
    assert "ENGINE-REQUIRED" in r["S2_status"]
    assert "S2_dev" not in r and "S2_recent" not in r
    # recent scored once, winner only
    assert r["S1_recent_once"]["anchor"] == "2025-09-24"
    five = r["S1_five_posthoc"]
    allR = Rs + [r["S1_recent_once"]["R"]]
    assert five["W"] == min(allR)
    assert abs(float(np.prod([1 + x / 100 for x in allR])) ** (1 / 5)
               - 1 - five["R"] / 100) < 5e-5
    assert r["S1_full_chained_posthoc"] == 14.71
    assert r["S1_chained_full_dev"] == 14.71


def test_base_dev_matches_official():
    v424 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2"
                       "/v424/v424_result.json").read_text())
    off = v424["rows"]["R2B1D13BF"]["years"]
    for i, y in enumerate(_res()["S1_dev_years"]):
        assert y["base_R"] == off[i][0] and y["base_DD"] == off[i][1]


def test_hourly_mark_causal_spot_check():
    spec = importlib.util.spec_from_file_location(
        "d13carry_mod", HERE / "analyze_d13carry.py")
    assert spec is not None
    d13 = importlib.util.spec_from_file_location(
        "reuse_mod", ROOT / "research/tournament/oc_carryd13"
        / "combine_carryd13.py")
    mod = importlib.util.module_from_spec(d13)
    d13.loader.exec_module(mod)
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    d = h[h["sym"] == "BTCUSDT"].sort_values("t")
    times = d["t"].values.astype("datetime64[ns]").astype(np.int64)
    closes = d["close"].to_numpy(float)
    probe = pd.Timestamp("2024-01-15 12:00", tz="UTC").value
    full = mod.last_close_before(times, closes, np.array([probe]))[0]
    trunc = d[d["t"] < pd.Timestamp("2024-01-15 12:00", tz="UTC")]
    tt = trunc["t"].values.astype("datetime64[ns]").astype(np.int64)
    part = mod.last_close_before(tt, trunc["close"].to_numpy(float),
                                 np.array([probe]))[0]
    assert full == part
    assert full != closes[-1]


def test_no_1m_no_engine_and_posthoc():
    src = _script_src()
    for bad in ("klines_1m", "_1m.parquet", "intraday_20260924", "aggflow",
                "simulate(", "Pool(", "heavy_slot", "phase_offset_full"):
        assert bad not in src, bad
    assert 'side="left"' in src or "side='left'" in src or \
        "combine_carryd13" in src
    r = _res()
    assert r["meta"]["post_hoc"] is True
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"
    assert "zero trades" in r["win_rate_note"]


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    assert "S1" in rep and "S2" in rep  # pre-reg lines intact
    for needle in ("5.203", "2.632", "14.71", "5.115", "4.764",
                   "5.634", "16.66", "ENGINE-REQUIRED"):
        assert needle in rep, needle
