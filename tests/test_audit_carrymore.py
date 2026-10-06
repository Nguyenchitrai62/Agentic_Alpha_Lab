"""Blind audit test for oc_carrymore (COIN-M quarterly cash-and-carry, 5 majors).

Compares research/tournament/audit_carrymore/replication.json (built blind;
written before oc_carrymore REPORT.md/results.json were opened) against the
published oc_carrymore REPORT.md/results.json within tolerance 0.01 %/mo (R),
0.05 pp (DD), trade count exact. Plus causality spot-checks (no 1m data,
closed-bars-only entries, truncation invariance).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
AUD = ROOT / "research/tournament/audit_carrymore"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

TOL_R = 0.01 + 1e-9
TOL_DD = 0.05 + 1e-9

# REPORT.md §4 rows (POST-HOC) + inventory counts
EXP_TRADES = {"BTC": 18, "ETH": 16, "BNB": 5, "SOL": 3, "XRP": 13}
EXP_A = {"R": 5.626, "W": 2.746, "DD": 16.91, "full": 16.82, "losing": 0,
         "years": [(2.746, 10.86), (3.314, 16.91), (6.600, 15.60),
                   (10.971, 8.20), (4.702, 12.62)]}
EXP_B = {"R": 5.771, "W": 2.853, "DD": 16.91, "full": 16.82, "losing": 0,
         "years": [(2.853, 10.86), (3.327, 16.91), (6.902, 15.59),
                   (11.263, 8.46), (4.730, 12.45)]}
EXP_BASE = {"R": 5.410, "W": 2.588, "DD": 16.91, "full": 16.82}


def _rep():
    return json.loads((AUD / "replication.json").read_text())


def _check_row(got_rows, got_full, exp, tag):
    r = got_rows["0.25"]
    assert abs(r["R"] - exp["R"]) <= TOL_R, (tag, r["R"], exp["R"])
    assert abs(r["W"] - exp["W"]) <= TOL_R, (tag, r["W"], exp["W"])
    assert abs(r["DD"] - exp["DD"]) <= TOL_DD, (tag, r["DD"], exp["DD"])
    assert abs(got_full["0.25"]["full"] - exp["full"]) <= TOL_DD, (tag, got_full)
    assert r["losing"] == exp["losing"], (tag, r["losing"])
    for g, (er, ed) in zip(r["years"], exp["years"]):
        assert abs(g["R"] - er) <= TOL_R, (tag, g, er)
        assert abs(g["DD"] - ed) <= TOL_DD, (tag, g, ed)


def test_trade_counts_exact():
    rep = _rep()
    assert rep["n_entered_total"] == 55
    for coin, n in EXP_TRADES.items():
        assert rep["per_coin"][coin]["n_entered"] == n, (coin, rep["per_coin"][coin])
    res = json.loads((ROOT / "research/tournament/oc_carrymore/results.json").read_text())
    assert len(res["trades"]) == 55 and len(rep["trades"]) == 55


def test_per_trade_values_exact_vs_results():
    rep = _rep()
    res = json.loads((ROOT / "research/tournament/oc_carrymore/results.json").read_text())
    rt = {(t["coin"], t["delivery"]): t for t in rep["trades"]}
    for t in res["trades"]:
        r = rt[(t["coin"], t["delivery"])]
        for fld in ("ann_basis", "ret_alloc", "worst_mtm_alloc"):
            assert abs(r[fld] - t[fld]) < 5e-6, (t["coin"], t["delivery"], fld)
        for fld in ("F_entry", "S_entry", "S_del"):
            assert abs(r[fld] - t[fld]) / abs(t[fld]) < 1e-9, (t["coin"], t["delivery"], fld)


def test_overlay_rows_within_tolerance():
    rep = _rep()
    _check_row(rep["overlay_BTC_ETH"]["rows"], rep["overlay_BTC_ETH"]["full"], EXP_A, "BTC+ETH")
    _check_row(rep["overlay_all_majors"]["rows"], rep["overlay_all_majors"]["full"], EXP_B, "ALL")
    b = rep["overlay_BTC_ETH"]["rows"]["0.0"]
    assert abs(b["R"] - EXP_BASE["R"]) <= TOL_R
    assert abs(b["W"] - EXP_BASE["W"]) <= TOL_R
    assert abs(b["DD"] - EXP_BASE["DD"]) <= TOL_DD
    assert abs(rep["overlay_BTC_ETH"]["full"]["0.0"]["full"] - EXP_BASE["full"]) <= TOL_DD


def test_causality_fields():
    rep = _rep()
    for t in rep["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = pd.Timestamp(t["entry_close"], tz="UTC")
        assert pd.Timedelta(hours=3, minutes=59) < tc - te <= pd.Timedelta(hours=4)
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        assert tc < D, (t["coin"], t["delivery"])  # entry strictly before delivery
        assert t["DTE_days"] > 0 and t["ann_basis"] >= 0.04 - 1e-12


def test_truncation_invariance_spot_check():
    # Recompute one trade's entry prices from data truncated at entry close.
    rep = _rep()
    t = next(x for x in rep["trades"]
             if x["coin"] == "BTC" and x["delivery"] == "2024-06-28")
    tc = pd.Timestamp(t["entry_close"], tz="UTC")
    s = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                        columns=["open_time", "close_time", "close"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    s = s[s["close_time"] <= tc]  # truncate: nothing after entry close
    S_tr = float(s[s["close_time"] == tc]["close"].iloc[0])
    y, m, dd = t["delivery"].split("-")
    q = pd.read_parquet(QDIR / f"cm_BTCUSD_{y[2:]}{m}{dd}_1h.parquet",
                        columns=["open_time", "close"])
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    q = q[q["open_time"] < tc]  # strictly causal resample
    F_tr = float(q["close"].iloc[-1])
    assert abs(S_tr - t["S_entry"]) / t["S_entry"] < 1e-12
    assert abs(F_tr - t["F_entry"]) / t["F_entry"] < 1e-12


def test_no_intraday_paths_in_replication_script():
    src = (AUD / "replicate_carrymore.py").read_text()
    assert "1m" not in src.replace("0.001", "").replace("0.00055", "").replace("0.0002", "")
    assert "intraday" not in src.lower()
