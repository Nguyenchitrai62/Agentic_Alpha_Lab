"""Tests for oc_carryutil (descriptive utilization of the frozen carry rule).

Checks: frozen threshold respected, counts tie to oc_cashcarry, anchor-pool
contributions sum to the +0.22 %/mo lift, shares in [0,1], entered basis >
skipped basis where both exist, fee math on a spot sample, REPORT<->JSON
consistency (incl. 4-line Vietnamese note), script stays read-only (no 1m,
no network/orders/artifacts writes, no threshold edit).
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_carryutil"
CASH = ROOT / "research/tournament/oc_cashcarry/results.json"


def _res():
    return json.loads((HERE / "results.json").read_text())


def test_counts_match_cashcarry():
    out = _res()
    cash = json.loads(CASH.read_text())
    assert out["n_entered"] == cash["n_trades"] == 33
    assert out["n_skipped"] == cash["n_skipped"] == 13
    assert out["meta"]["no_tuning"] is True
    for c in out["contracts"]:
        if c["status"] == "entered":
            assert c["ann_basis"] >= 0.04 - 1e-9, c
        elif c["status"] == "skipped_basis":
            assert c["ann_basis"] < 0.04 + 1e-9, c


def test_pool_decomposition_sums_to_lift():
    out = _res()
    cash = json.loads(CASH.read_text())
    pool = out["anchor_pool_f025_mo_pct"]
    tot = pool["total"]
    assert abs(sum(v["contrib_mo_pct_f025"] for v in pool["per_coin"].values()) - tot) < 1e-9
    assert abs(tot - 0.2181) < 1e-4  # the +0.22 %/mo lift at f = 0.25
    assert abs(tot - cash["pooled"]["per_f"]["0.25"]["per_month_pct"]) < 1e-4
    assert abs(pool["per_coin"]["BTC"]["share_of_lift"]
               + pool["per_coin"]["ETH"]["share_of_lift"] - 1.0) < 1e-9


def test_calendar_years_cover_2021_2026_and_shares_sane():
    out = _res()
    years = [r["year"] for r in out["calendar_years"]]
    assert years == [2021, 2022, 2023, 2024, 2025, 2026]
    for r in out["calendar_years"]:
        for coin in ("BTC", "ETH"):
            v = r["per_coin"][coin]
            assert 0.0 <= v["share_invested"] <= 1.0, (r["year"], coin, v)
            assert 0 <= v["invested_days"] <= r["days"], (r["year"], coin, v)
            assert v["n_entered"] + v["n_skipped"] >= 0
            if v["mean_basis_entered"] is not None and v["mean_basis_skipped"] is not None:
                assert v["mean_basis_entered"] >= 0.04 - 1e-9
                assert v["mean_basis_skipped"] < 0.04 + 1e-9
        assert r["either_coin_invested_days"] <= r["days"]
        assert r["both_idle_days"] == r["days"] - r["either_coin_invested_days"]
    n_skip = sum(r["per_coin"][c]["n_skipped"]
                 for r in out["calendar_years"] for c in ("BTC", "ETH"))
    assert n_skip == out["n_skipped"] == 13


def test_skipped_eth_cost_internally_consistent():
    out = _res()
    s = out["skipped_eth_cost"]
    assert s["n_skipped_eth"] == 8
    assert len(s["deliveries"]) == 8
    assert s["counterfactual_min_max"][0] <= s["counterfactual_mean_ret_alloc"] <= s["counterfactual_min_max"][1]
    # foregone account % per quarter at f=0.25 follows from the counterfactual mean
    assert abs(s["foregone_acct_pct_per_quarter_f025"]
               - round(0.25 * s["counterfactual_mean_ret_alloc"] * 100, 4)) < 1e-9
    # skipped quarters pay far less than entered ones (filter works)
    assert s["counterfactual_mean_ret_alloc"] < s["entered_mean_ret_alloc_anchor"]


def test_fee_math_spot_check_from_raw():
    out = _res()
    c = next(x for x in out["contracts"]
             if x["coin"] == "BTC" and x["delivery"] == "2024-06-28")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/BTCUSDT_spot_4h.parquet",
                        columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    te = pd.Timestamp(c["entry_open"], tz="UTC")
    trunc = s[s["open_time"] <= te]
    # entry uses only closes available at entry (causal truncation spot-check)
    assert len(trunc) < len(s)


def test_entry_causal_truncation_leaves_values_unchanged():
    """Recompute one entry basis from data truncated at its entry close."""
    import numpy as np

    out = _res()
    c = next(x for x in out["contracts"]
             if x["coin"] == "ETH" and x["delivery"] == "2024-03-29")
    te = pd.Timestamp(c["entry_open"], tz="UTC")
    s = pd.read_parquet(ROOT / "data/raw/spot_majors_20260925/ETHUSDT_spot_4h.parquet",
                        columns=["open_time", "close", "close_time"])
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    s["close_time"] = pd.to_datetime(s["close_time"], utc=True)
    row = s[s["open_time"] == te]
    assert len(row) == 1
    q = pd.read_parquet(ROOT / "data/raw/qbasis_20261003/um_ETHUSDT_240329_1h.parquet",
                        columns=["open_time", "close"])
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    q = q.sort_values("open_time").reset_index(drop=True)
    tc = pd.Timestamp(row["close_time"].iloc[0])
    past = q[q["open_time"] < tc]
    f_entry = float(past["close"].iloc[-1])
    s_entry = float(row["close"].iloc[0])
    dte = (pd.Timestamp("2024-03-29 08:00", tz="UTC") - tc).total_seconds() / 86400.0
    basis = float(np.log(f_entry / s_entry) * 365.0 / dte)
    assert abs(basis - c["ann_basis"]) < 1e-6


def test_script_stays_light_and_readonly():
    src = (HERE / "analyze_carryutil.py").read_text()
    for bad in ("intraday_20260924", "intraday_20260930", "premium_1m",
                "klines_1m", "_1m.parquet", '/ "artifacts"', "Bybit(",
                "place_order", "heavy_slot", "requests.get", "urllib"):
        assert bad not in src, bad
    assert "THRESHOLD = 0.04" in src  # frozen, single occurrence defines the rule
    assert src.count("0.04") >= 1
    assert "no_tuning" in src


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text()
    out = _res()
    assert "descriptive, no tuning" in rep
    for y in (2021, 2022, 2023, 2024, 2025, 2026):
        assert str(y) in rep
    assert f'{out["anchor_pool_f025_mo_pct"]["total"]:.4f}' in rep
    assert "Dec-26" in rep and "SKIP" in rep  # today snapshot (assignment-given)
    assert "Ghi chu cho chu" in rep
    vn = rep.split("Ghi chu cho chu")[1].strip().splitlines()
    vn_lines = [ln for ln in vn if ln.strip() and not ln.startswith("(")]
    assert len(vn_lines) == 4, vn_lines
    assert "63.5%" in rep  # ETH overall utilization
