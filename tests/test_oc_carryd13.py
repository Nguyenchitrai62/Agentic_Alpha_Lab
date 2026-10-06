"""Tests for oc_carryd13 (frozen rule reuse, causality, accounting, no-1m, JSON/REPORT)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_carryd13"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _cc():
    return json.loads((CC / "results.json").read_text())


def _script():
    spec = importlib.util.spec_from_file_location(
        "combine_carryd13", HERE / "combine_carryd13.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_only_d13bf_qualifies():
    r = _res()
    assert r["meta"]["qualifying_max_yearly_DD_lt_15"] == ["v424/R2B1D13BF"]
    sc = r["meta"]["rows_scanned"]
    assert sc["v424/R2B1D13BF"]["DD"] == 14.98
    assert sc["v424/R2B1D14BFX5"]["DD"] == 15.34
    assert sc["v425/D13BFG2"]["DD"] == 15.07  # nearest miss, correctly excluded
    assert len(r["combos"]) == 2  # 1 row x f in {0.25, 0.5}
    assert sorted(c["f"] for c in r["combos"]) == [0.25, 0.5]


def test_carry_rule_reused_unchanged():
    r, cc = _res(), _cc()
    assert "33 entered / 13 skipped / 2 incomplete" in r["meta"]["carry_rule"]
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9


def test_base_reproduces_official():
    r = _res()
    assert r["checks"]["base_R_gap_vs_official"] == 0.0
    assert r["checks"]["base_W_gap_vs_official"] == 0.0
    assert r["checks"]["base_DD_gap_vs_official"] == 0.0
    off = r["base_official_v424"]
    assert (off["R"], off["W"], off["DD"]) == (4.971, 2.485, 14.98)


def test_hourly_mark_causal_spot_check():
    """Recompute one mid-trade hourly mark from truncated data (bars strictly before t)."""
    M = _script()
    cc = _cc()
    t = next(x for x in cc["trades"] if x["coin"] == "BTC" and x["delivery"] == "2024-03-29")
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
    assert full == part  # later bars cannot move an earlier mark
    assert full != closes[-1]  # full-history last close does not leak in
    # probe is inside the holding window: entry 2023-12-22, delivery 2024-03-29
    assert pd.Timestamp(t["entry_open"], tz="UTC").value < probe


def test_fee_math_entry_vs_realized():
    M = _script()
    assert M.FEE_ENTRY_PAID == 0.001 + 0.00055
    cc = _cc()
    t = cc["trades"][0]
    # realized ret_alloc carries the FULL 0.00275 drag, MtM only entry fees
    import pytest as _pt
    assert 0.00275 - M.FEE_ENTRY_PAID == _pt.approx(0.0002 + 0.001)


def test_recompute_aggregates_and_stretch_flag():
    r = _res()
    for c in r["combos"]:
        tots = np.array([y["total_pct"] / 100 for y in c["years"]])
        R5 = float(np.prod(1 + tots) ** (1 / 60) - 1) * 100  # cross-check path
        assert abs(R5 - c["R_5y"]) < 0.05  # (1/60 on totals vs geo of monthlies)
        assert min(y["R"] for y in c["years"]) == c["W"]
        assert max(y["DD"] for y in c["years"]) == c["DD_maxyearly"]
        assert c["losing_years"] == sum(y["R"] < 0 for y in c["years"])
        for y in c["years"]:
            m2 = (1 + y["total_pct"] / 100) ** (1 / 12) - 1
            assert abs(m2 * 100 - y["R"]) < 1e-2
        want = bool(c["R_5y"] >= 5.0 and c["DD_maxyearly"] < 15.0
                    and c["full_path_dd_chained"] < 15.0 and c["losing_years"] == 0)
        assert c["stretch_all"] == want
        assert "unchanged" in c["win_rate_note"].lower() and "zero trades" in c["win_rate_note"]
    by_f = {c["f"]: c for c in r["combos"]}
    assert by_f[0.25]["stretch_all"] is True and by_f[0.5]["stretch_all"] is True
    assert by_f[0.5]["R_5y"] > by_f[0.25]["R_5y"] > 4.971  # carry adds return
    assert r["checks"]["monthly_total_residual_pp"] < 1e-2


def test_no_1m_and_posthoc_label():
    src = (HERE / "combine_carryd13.py").read_text()
    for bad in ("klines_1m", "aggflow", "_1m.parquet", "intraday_20260924", "premium_1m"):
        assert bad not in src, bad
    r = _res()
    assert r["meta"]["post_hoc"] is True and r["meta"]["reporting_only"] is True
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    r = _res()
    assert "v424/R2B1D13BF" in rep and "D13BFG2" in rep and "15.07" in rep
    for c in r["combos"]:
        assert str(c["R_5y"]) in rep and str(c["full_path_dd_chained"]) in rep
    assert "YES" in rep
