"""Tests for oc_i2_dvolveto (DVOL-spike dip veto; screen failed, no engine run).

Fast only: spike causality on synthetic grids + accounting/fidelity checks
against research/tournament/oc_i2_dvolveto/results.json. No 1m data here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OC = ROOT / "research/tournament/oc_i2_dvolveto"
sys.path.insert(0, str(OC))
import compute_dvolveto as V

NS = 1_000_000_000


def _res():
    return json.loads((OC / "results.json").read_text())


def _synth_hourly(n_days=130, seed=7, start="2021-06-01"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n_days * 24, freq="h", tz="UTC")
    closes = 50 + np.cumsum(rng.normal(0, 1, len(idx)))
    ends = idx.values.astype("datetime64[ns]").astype(np.int64) + 3_600 * NS
    return ends, closes


# --- spike causality -------------------------------------------------------
def test_daily_change_uses_closed_bars_only():
    ends, closes = _synth_hourly()
    d1 = V.daily_series(ends, closes)
    # append a huge spike AFTER the sample: earlier rows must not move
    ends2 = np.concatenate([ends, ends[-1:] + 3_600 * NS])
    closes2 = np.concatenate([closes, [1e6]])
    d2 = V.daily_series(ends2, closes2)
    m = d2["day"].isin(d1["day"])
    pd.testing.assert_series_equal(d1["chg"], d2.loc[m, "chg"].reset_index(drop=True),
                                   check_names=False)


def test_veto_never_uses_spike_day_close():
    ends, closes = _synth_hourly()
    daily = V.daily_series(ends, closes)
    q = V.fit_thresholds(daily)
    days = pd.date_range("2021-09-24", "2021-10-24", freq="D", tz="UTC")
    v1 = V.veto_for_days(days, daily, q)
    # corrupt the spike-day closes themselves: veto flags must not change
    daily2 = daily.copy()
    daily2["D"] = daily2["D"] * 3.0
    daily2["chg"] = daily2["D"].diff()
    # chg(x-1) for day x now differs -> flags SHOULD change in general, but a
    # veto for day x must be explainable by chg(x-1) alone:
    for x in days:
        k = V.year_of(x)
        thr = q[str(V.ANCHORS[k].date())]["q95"]
        prev = x - pd.Timedelta(days=1)
        c = daily.set_index("day")["chg"].get(prev, np.nan)
        assert bool(v1[x]) == bool(np.isfinite(c) and c > thr)


def test_threshold_fit_window_excludes_test_year_plus_embargo():
    ends, closes = _synth_hourly(n_days=1700, start="2021-01-01")
    daily = V.daily_series(ends, closes)
    q = V.fit_thresholds(daily)
    for k, a0 in enumerate(V.ANCHORS[:4]):
        e = q[str(a0.date())]
        assert e["fit_hi_excl"] == str((a0 - pd.Timedelta(days=10)).date())
        assert e["fit_lo"] == str((a0 - pd.Timedelta(days=100)).date())
        assert e["n_fit"] == 90
    # a huge spike inside a test year cannot move that year's threshold
    daily2 = daily.copy()
    m = (daily2["day"] >= "2023-01-01") & (daily2["day"] < "2023-06-01")
    daily2.loc[m, "chg"] = daily2.loc[m, "chg"] + 500.0
    q2 = V.fit_thresholds(daily2)
    assert q2["2023-09-24"]["q95"] == q["2023-09-24"]["q95"]


def test_flag_for_bar_uses_calendar_day():
    days = pd.date_range("2021-09-24", "2021-09-30", freq="D", tz="UTC")
    veto = pd.Series([True, False, False, True, False, False, False], index=days)
    assert V.flag_for_bar(pd.Timestamp("2021-09-24 16:00", tz="UTC"), veto) is True
    assert V.flag_for_bar(pd.Timestamp("2021-09-25 00:00", tz="UTC"), veto) is False
    assert V.flag_for_bar(pd.Timestamp("2021-09-27 04:00", tz="UTC"), veto) is True


# --- real-data spike stats ---------------------------------------------------
def test_real_veto_day_counts_and_sources_agree():
    sp = _res()["spike"]
    got = {r["year"]: r["veto_days"] for r in sp["per_year"]}
    assert got == {"2021-09-24": 21, "2022-09-24": 17, "2023-09-24": 22,
                   "2024-09-24": 7, "2025-09-24": 42}
    assert sp["veto_total_days"] == 109
    assert sp["old_file_maxabsdiff_n"][0] == 0.0  # two DVOL sources identical
    assert sp["max_step_h"] == 1  # gap-free hourly grid


# --- baseline ----------------------------------------------------------------
def test_baseline_reproduces_to_digit():
    b = _res()["baseline"]
    assert b["repro"] == "OK to the digit"
    assert b["G2_carry_f025"]["R"] == 5.634
    assert b["G2_carry_f025"]["DD"] == 16.75
    assert b["G2_carry_f025"]["full_path_dd"]["full"] == 16.66
    assert b["G2_f0"]["R"] == 5.41 and b["G2_f0"]["W"] == 2.588
    assert b["G2_f0"]["DD"] == 16.91
    assert b["carry_add"] == 0.224


# --- replica fidelity + veto accounting ---------------------------------------
def test_replica_fidelity_matches_placebo_base():
    rep = _res()["replica"]
    assert rep["n_fills"] == 22312
    assert rep["phase0_maxabsdiff"] <= 1e-3
    assert abs(rep["base_sum5y"] - 7.718304) < 1e-4


def test_veto_accounting_and_gate_fail():
    rep = _res()["replica"]
    assert rep["n_skipped_veto"] == 3540
    assert abs(rep["skip_share"] - 3540 / 22312) < 1e-6
    # V1 sums are lower in EVERY year (holds/exits unchanged -> pure deletion)
    for b, v in zip(rep["base_per_year"], rep["v1_per_year"]):
        assert v["S"] < b["S"]
        assert v["n"] < b["n"]
    d = rep["decision"]
    assert d["years_sum_ge"] == 0 and d["pass_sum_half"] is False
    assert d["promising"] is False
    assert abs(d["dSum5y"] - (rep["v1_sum5y"] - rep["base_sum5y"])) < 1e-5
    assert d["dSum5y"] < 0.273  # far below the placebo pooled-p95 gate
    assert d["dDDmean"] > 0  # mean DD worse, not better


def test_dev4_alone_rejects ():
    rep = _res()["replica"]
    dev4 = [(b["S"], v["S"]) for b, v in
            zip(rep["base_per_year"][:4], rep["v1_per_year"][:4])]
    assert sum(1 for b, v in dev4 if v >= b) == 0  # 0/4 on dev years only


# --- V2 book diagnostic --------------------------------------------------------
def test_book_diag_dev4_fails_joint_reading():
    years = _res()["book_diag"]["years"]
    assert len(years) == 5
    dev = years[:4]
    pnl_ok = sum(1 for y in dev if y["total_pnl_gated"] >= y["total_pnl"])
    dd_ok = sum(1 for y in dev if y["maxDD_gated"] < y["maxDD"])
    assert pnl_ok == 2 and dd_ok == 3
    # 2021 diagnostic matches oc_dvolshort's ungated book exactly
    assert years[0]["total_pnl"] == 0.309477
    assert years[0]["maxDD"] == 0.131523


# --- report ----------------------------------------------------------------------
def test_report_prereg_and_verdict():
    rep = (OC / "REPORT.md").read_text(encoding="utf-8")
    for needle in ("PRE-REGISTRATION (written BEFORE any run;",
                   "V1: veto NEW dip bids on spike-flagged signal bars",
                   "V2: V1 dip veto + on spike-flagged bars halve BOOK longs",
                   "5.634", "16.75", "16.66", "+0.273", "dSum5y = -1.508",
                   "REJECT", "Dòng 1:", "Dòng 2:", "Dòng 3:"):
        assert needle in rep, needle
    assert "no engine run" in rep.lower() or "No 4-phase engine run" in rep
