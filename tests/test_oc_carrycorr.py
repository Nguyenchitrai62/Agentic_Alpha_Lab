"""Tests for oc_carrycorr (frozen inputs, causality, accounting, no-1m, JSON/REPORT)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_carrycorr"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"
CUT = pd.Timestamp("2026-09-24", tz="UTC")


def _res():
    return json.loads((HERE / "results.json").read_text())


def _cc():
    return json.loads((CC / "results.json").read_text())


def _script():
    spec = importlib.util.spec_from_file_location(
        "analyze_carrycorr", HERE / "analyze_carrycorr.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_files_present():
    for f in ("analyze_carrycorr.py", "results.json", "REPORT.md"):
        assert (HERE / f).exists(), f


def test_carry_frozen_from_oc_cashcarry():
    r, cc = _res(), _cc()
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    assert cc["n_incomplete"] == 2
    assert r["meta"]["inputs"]["n_carry_trades"] == 33
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        assert abs(t["ret_alloc"] - round(gross - 0.00275, 6)) < 1e-9


def test_no_1m_and_cap():
    src = (HERE / "analyze_carrycorr.py").read_text()
    for bad in ("klines_1m", "aggflow", "_1m.parquet", "intraday_20260924",
                "premium_1m", "bybit_linear_1m"):
        assert bad not in src, bad
    r = _res()
    assert r["meta"]["data_cap"] == "2026-09-24T00:00:00Z"
    assert r["meta"]["no_1m"] is True and r["meta"]["diagnostic_only"] is True
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet",
                        columns=["t"])
    assert pd.to_datetime(h["t"], utc=True).max() < CUT


def test_fee_math_entry_vs_realized():
    M = _script()
    assert M.FEE_ENTRY_PAID == 0.001 + 0.00055
    assert M.FEE_PAIR == 2 * 0.001 + 0.00055 + 0.0002


def test_hourly_mark_causal_spot_check():
    """One mid-trade hourly mark from truncated data (strictly-before-t)."""
    M = _script()
    cc = _cc()
    t = next(x for x in cc["trades"] if x["coin"] == "BTC"
             and x["delivery"] == "2024-03-29")
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
    part = M.last_close_before(tt, trunc["close"].to_numpy(float),
                               np.array([probe]))[0]
    assert full == part
    assert full != closes[-1]
    assert pd.Timestamp(t["entry_open"], tz="UTC").value < probe


def test_daily_corr_sane():
    r = _res()
    c = r["corr_daily_overall"]
    assert c["n_days"] == 1824
    for k in ("pearson_log_vs_pnl", "spearman_log_vs_pnl",
              "pearson_simple_vs_pnl"):
        assert -1.0 <= c[k] <= 1.0, (k, c[k])
    assert abs(c["pearson_log_vs_pnl"]) < 0.5  # near-zero, not a bug hedge
    for k in ("corr_in_worst_weeks", "corr_outside_worst_weeks",
              "corr_in_dd_episodes"):
        v = r[k]
        assert -1.0 <= v["pearson"] <= 1.0 and -1.0 <= v["spearman"] <= 1.0


def test_worst_weeks_sorted_nonoverlapping():
    r = _res()
    w = r["worst_10_weeks"]
    assert len(w) == 10
    g = [x["g2_7d_logret"] for x in w]
    assert g == sorted(g) and all(v < 0 for v in g)
    ends = [pd.Timestamp(x["end"], tz="UTC") for x in w]
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            assert abs((ends[i] - ends[j]).days) >= 7
    s = r["worst_10_weeks_sums"]
    assert abs(sum(x["g2_7d_logret"] for x in w) - s["g2_7d_logret_sum"]) < 1e-9
    assert abs(sum(x["carry_7d_pnl_f025"] for x in w)
               - s["carry_7d_pnl_f025_sum"]) < 1e-9


def test_dd_episodes_and_crash_days():
    r = _res()
    eps = r["dd_episodes"]
    assert len(eps) == 3
    dds = [e["g2_dd"] for e in eps]
    assert dds == sorted(dds, reverse=True) and all(v > 0 for v in dds)
    cg = r["crash_5_worst_g2_days"]
    assert len(cg) == 5
    gl = [x["g2_logret"] for x in cg]
    assert gl == sorted(gl) and all(v < 0 for v in gl)
    for x in cg:
        assert (x["carry_sign"] == "widening_or_flat") == (x["carry_pnl_f025"] >= 0)
        assert abs(x["carry_pnl_f025"]) < 0.02  # hedge holds: bps vs G2's %
    cb = r["crash_5_worst_btc_days"]
    assert len(cb) == 5
    bl = [x["btc_logret"] for x in cb]
    assert bl == sorted(bl) and all(v < -0.05 for v in bl)


def test_basis_vs_bot_lengths():
    r = _res()
    assert r["basis_corr_inwindow25"]["n"] == 25
    assert r["basis_corr_all33"]["n"] == 25  # 8 pre-G0 excluded, labelled
    assert "excluded" in r["basis_corr_all33"]["note"]
    assert len(r["basis_vs_bot_holds"]) == 25
    sp = r["basis_split"]
    assert sp["n_high"] + sp["n_low"] == 25
    for k in ("pearson", "spearman"):
        assert -1.0 <= r["basis_corr_all33"][k] <= 1.0


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    r = _res()
    c = r["corr_daily_overall"]
    assert "0.0909" in rep  # Pearson −0.0909 (unicode minus in REPORT)
    assert "0.0782" in rep
    assert "0.0097" in rep  # worst-weeks carry sum +0.009703 (rounded in REPORT)
    assert "KẾT LUẬN" in rep and "đa dạng hóa" in rep
    assert "1824" in rep or "1,824" in rep
