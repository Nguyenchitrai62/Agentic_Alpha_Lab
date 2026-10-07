"""Tests for oc_frontiercarry (POST-HOC carry f=0.25 on all 80 frontier rows)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_frontiercarry"
FR = ROOT / "research/tournament/oc_frontier"
C13 = ROOT / "research/tournament/oc_carryd13"
CC = ROOT / "research/tournament/oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _front():
    return json.loads((FR / "results.json").read_text())


def _cc():
    return json.loads((CC / "results.json").read_text())


def _c13mod():
    spec = importlib.util.spec_from_file_location(
        "combine_carryd13_reuse", C13 / "combine_carryd13.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_files_present_and_posthoc():
    for f in ("combine_frontiercarry.py", "results.json", "REPORT.md"):
        p = HERE / f
        assert p.exists() and p.stat().st_size > 0, f
    r = _res()
    assert r["meta"]["post_hoc"] is True and r["meta"]["reporting_only"] is True
    assert r["meta"]["carry_f"] == 0.25
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"
    assert "UNCHANGED" in r["meta"]["combination"]
    assert "33 entered / 13 skipped / 2 incomplete" in r["meta"]["carry_rule"]


def test_covers_all_80_frontier_rows_sorted():
    r, front = _res(), _front()
    assert r["checks"]["n_frontier_rows"] == 80
    assert r["checks"]["n_with_stored_runs"] == 80
    assert r["checks"]["missing_rows"] == []
    assert len(r["combos"]) == 80
    fkeys = sorted(f"{d['version']}/{d['row']}" for d in front["rows"])
    ckeys = sorted(d["key"] for d in r["combos"])
    assert ckeys == fkeys
    dds = [d["carry"]["DD_maxyearly"] for d in r["combos"]]
    assert dds == sorted(dds), "combos not sorted by carry max yearly DD"


def test_base_reproduces_frontier_exactly():
    r = _res()
    assert r["checks"]["base_R_gap_vs_official_max"] == 0.0
    assert r["checks"]["base_W_gap_vs_official_max"] == 0.0
    assert r["checks"]["base_DD_gap_vs_official_max"] == 0.0
    by = {f"{d['version']}/{d['row']}": d for d in _front()["rows"]}
    for d in r["combos"]:
        o = d["official"]
        f = by[d["key"]]
        assert o["R"] == f["R"] and o["W"] == f["W"]
        assert o["DD_maxyearly"] == f["dd_yearly"]
        exp_full = f["full_path_dd"]
        assert o["full_path_dd"] == exp_full, d["key"]
        assert d["base"]["R_5y"] == o["R"]
        assert d["base"]["W"] == o["W"]
        assert d["base"]["DD_maxyearly"] == o["DD_maxyearly"]


def test_carry_rule_reused_unchanged():
    r, cc = _res(), _cc()
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9
    M = _c13mod()
    assert M.FEE_ENTRY_PAID == 0.001 + 0.00055
    assert r["checks"]["carry_fee_entry_paid"] == M.FEE_ENTRY_PAID


def test_aggregates_and_flags_consistent():
    r = _res()
    for d in r["combos"]:
        for leg in ("base", "carry"):
            v = d[leg]
            assert len(v["years"]) == 5
            assert min(y["R"] for y in v["years"]) == v["W"]
            assert max(y["DD"] for y in v["years"]) == v["DD_maxyearly"]
            assert v["losing_years"] == sum(y["R"] < 0 for y in v["years"])
            for y in v["years"]:
                m2 = (1 + y["total_pct"] / 100) ** (1 / 12) - 1
                assert abs(m2 * 100 - y["R"]) < 1e-2
        b, c = d["base"], d["carry"]
        want_base = bool(b["R_5y"] >= 5.0 and b["DD_maxyearly"] < 20.0
                         and b["full_path_dd_chained"] < 20.0 and b["losing_years"] == 0)
        want_carry = bool(c["R_5y"] >= 5.0 and c["DD_maxyearly"] < 20.0
                          and c["full_path_dd_chained"] < 20.0 and c["losing_years"] == 0)
        want_stretch = bool(c["R_5y"] >= 5.0 and c["DD_maxyearly"] < 15.0
                            and c["full_path_dd_chained"] < 15.0 and c["losing_years"] == 0)
        assert d["base_bot_base"] == want_base, d["key"]
        assert d["carry_bot_base"] == want_carry, d["key"]
        assert d["carry_stretch"] == want_stretch, d["key"]
        assert "zero trades" in d["win_rate_note"]
    assert r["checks"]["monthly_total_residual_pp_max"] < 1e-2


def test_headline_counts_and_key_rows():
    r = _res()
    combos = r["combos"]
    assert sum(1 for d in combos if d["base_bot_base"]) == 45
    assert sum(1 for d in combos if d["carry_bot_base"]) == 47
    assert sum(1 for d in combos if d["carry_stretch"]) == 0
    by = {d["key"]: d for d in combos}
    # flips over 5.0 with the sleeve
    for k in ("v409/R2B1D13", "v420/R2B1F15K20"):
        assert by[k]["base_bot_base"] is False and by[k]["carry_bot_base"] is True, k
    assert (by["v409/R2B1D13"]["carry"]["R_5y"],
            by["v409/R2B1D13"]["carry"]["DD_maxyearly"]) == (5.091, 14.87)
    # deployed G2 (audited twin v422; v421 twin identical)
    g2 = by["v422/R2B1D17BFG2"]
    assert (g2["base"]["R_5y"], g2["carry"]["R_5y"]) == (5.41, 5.533)
    assert (g2["carry"]["DD_maxyearly"], g2["carry"]["full_path_dd_chained"]) == (16.78, 16.78)
    assert by["v421/R2B1D17BFG2"]["carry"] == g2["carry"]
    # old deploy pick
    dep = by["v411/R2B1D17BF"]
    assert (dep["base"]["R_5y"], dep["carry"]["R_5y"]) == (5.425, 5.555)
    # highest base-pass return with carry
    ok = [d for d in combos if d["carry_bot_base"]]
    top = max(ok, key=lambda d: d["carry"]["R_5y"])
    assert top["key"] == "v422/G2K20"
    assert top["carry"]["R_5y"] == 5.989
    # carry helps return everywhere and never adds yearly DD
    for d in combos:
        lift = d["carry"]["R_5y"] - d["base"]["R_5y"]
        assert 0.05 < lift < 0.30, (d["key"], lift)
        assert d["carry"]["DD_maxyearly"] <= d["base"]["DD_maxyearly"], d["key"]
        assert d["carry"]["losing_years"] == 0 and d["base"]["losing_years"] == 0


def test_hourly_mark_causal_spot_check():
    M = _c13mod()
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    d = h[h["sym"] == "BTCUSDT"].sort_values("t")
    times = d["t"].values.astype("datetime64[ns]").astype(np.int64)
    closes = d["close"].to_numpy(float)
    probe = pd.Timestamp("2024-01-15 12:00", tz="UTC").value
    full = M.last_close_before(times, closes, np.array([probe]))[0]
    trunc = d[d["t"] < pd.Timestamp("2024-01-15 12:00", tz="UTC")]
    tt = trunc["t"].values.astype("datetime64[ns]").astype(np.int64)
    part = M.last_close_before(tt, trunc["close"].to_numpy(float), np.array([probe]))[0]
    assert full == part
    assert full != closes[-1]


def test_no_1m_and_report_content():
    src = (HERE / "combine_frontiercarry.py").read_text()
    for bad in ("klines_1m", "aggflow", "_1m.parquet", "intraday_20260924", "premium_1m"):
        assert bad not in src, bad
    rep = (HERE / "REPORT.md").read_text()
    assert "POST-HOC" in rep and "REPORTING ONLY" in rep
    assert "oc_utamargin" in rep and "oc_carryfric" in rep
    assert "0.2-0.8" in rep
    assert "v422/R2B1D17BFG2" in rep and "v409/R2B1D13" in rep and "v422/G2K20" in rep
    assert "45 -> 47" in rep
