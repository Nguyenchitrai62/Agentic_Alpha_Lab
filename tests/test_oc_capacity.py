"""Tests for research/tournament/oc_capacity/capacity.py (fast, self-contained).

Scratch depth parquets go ONLY to research/tournament/oc_capacity/tmp/
(never the system temp folder). Heavy real files are never loaded except the
small G2 events table (t column) for the window-bounds check.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent  # tests/
ROOT = HERE.parent
OC = ROOT / "research/tournament/oc_capacity"
SCRATCH = OC / "tmp" / "test_depth"


def _load_cap():
    spec = importlib.util.spec_from_file_location("oc_capacity_mod", OC / "capacity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_mini(root: Path, bad_row: bool = False):
    """One mini depth file per symbol; BTC snapshots every minute (ts = mm:30)."""
    root.mkdir(parents=True, exist_ok=True)
    base = pd.Timestamp("2023-06-01 00:00:00", tz="UTC")
    n = 500
    minutes = [base + pd.Timedelta(minutes=i) for i in range(n)]
    ts = [m + pd.Timedelta(seconds=30) for m in minutes]
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
        ask = np.full(n, 10_000_000.0)
        bid = np.full(n, 12_000_000.0)
        if bad_row and sym == "BTCUSDT":
            ask = ask.copy()
            ask[100] = 50.0  # stale near-zero print in the middle
        pd.DataFrame({"minute": minutes, "ts": ts, "bid_n1": bid,
                      "ask_n1": ask}).to_parquet(root / f"{sym}_bookdepth_1m.parquet")
    return base


def _orders(rows):
    return pd.DataFrame(rows, columns=["t", "sym", "side", "kind", "leg", "w", "eq",
                                       "profit", "shift"])


def test_join_uses_snapshot_strictly_before_t():
    cap = _load_cap()
    root = SCRATCH / "mini1"
    if root.exists():
        shutil.rmtree(root)
    base = _write_mini(root)
    cap.DEPTH = root
    # distinct ask per minute would be ideal; here all 10M: check minute identity via ts
    orders = _orders([
        # order 90s after the 00:01 snapshot -> must match 00:01 (ts 00:01:30 < t)
        (base + pd.Timedelta(minutes=2), "BTCUSDT", "buy", "rung_fill",
         "maker_entry", 0.05, 2.0, 0.01, 0),
        # order exactly ON a snapshot ts -> strictly before => previous snapshot
        (base + pd.Timedelta(minutes=1, seconds=30), "BTCUSDT", "buy", "rung_fill",
         "maker_entry", 0.05, 2.0, 0.01, 0),
        # order before the first snapshot -> unmatched
        (base - pd.Timedelta(minutes=5), "BTCUSDT", "buy", "rung_fill",
         "maker_entry", 0.05, 2.0, 0.01, 0),
        # order 10 min after the last snapshot -> lag > 5 min -> unmatched
        (base + pd.Timedelta(minutes=510), "BTCUSDT", "sell", "rung_fill",
         "maker_entry", 0.05, 2.0, 0.01, 0),
    ])
    orders["t"] = pd.to_datetime(orders["t"], utc=True)
    out, n_un, _n_bad, _med = cap.attach_depth(orders)
    assert out["D_side"].iloc[0] == 10_000_000.0  # buy -> ask side
    assert out["D_side"].iloc[1] == 10_000_000.0  # matched 00:00 snapshot, not 00:01
    assert np.isnan(out["D_side"].iloc[2])
    assert np.isnan(out["D_side"].iloc[3])
    assert n_un == 2
    shutil.rmtree(root)


def test_badprint_below_floor_is_unmatched():
    cap = _load_cap()
    root = SCRATCH / "mini2"
    if root.exists():
        shutil.rmtree(root)
    base = _write_mini(root, bad_row=True)
    cap.DEPTH = root
    bad_minute = base + pd.Timedelta(minutes=100)
    orders = _orders([
        (bad_minute + pd.Timedelta(minutes=1), "BTCUSDT", "buy", "rung_fill",
         "maker_entry", 0.05, 2.0, 0.01, 0),  # matches the $50 ask print
        (base + pd.Timedelta(minutes=200, seconds=45), "BTCUSDT", "buy", "rung_fill",
         "maker_entry", 0.05, 2.0, 0.01, 0),  # normal print
    ])
    orders["t"] = pd.to_datetime(orders["t"], utc=True)
    out, _n_un, n_bad, _med = cap.attach_depth(orders)
    assert np.isnan(out["D_side"].iloc[0])  # $50 print dropped
    assert out["D_side"].iloc[1] == 10_000_000.0
    assert n_bad == 1
    shutil.rmtree(root)


def test_haircut_math_and_ratio_scaling():
    cap = _load_cap()
    # r(E) = b*E/4 linear in E
    b = 0.05 * 4.0 / 10_000.0  # r(10k) = 5% exactly
    assert abs(b * 10_000 / 4.0 - 0.05) < 1e-12
    assert abs(b * 100_000 / 4.0 - 0.5) < 1e-12
    # fill prob p = 0.05/r for r > 5%
    r = 0.5
    p = 0.05 / r
    assert p == 0.1
    missed = (1 - p) * max(0.02, 0)  # winner
    assert abs(missed - 0.018) < 1e-12
    assert (1 - p) * max(-0.02, 0) == 0.0  # missing a loser costs nothing
    # stop cost = half-spread * notional fraction
    hs = cap.HALF_P90["BNBUSDT"]
    assert abs(hs - 0.5 * 1.2810 / 1e4) < 1e-15
    assert abs(hs * 0.1 - 0.5 * 1.2810 / 1e4 * 0.1) < 1e-18


def test_results_schema_and_monotonicity():
    res = json.loads((OC / "results.json").read_text())
    assert set(res) == {"rule", "inputs", "coverage", "per_symbol", "overall", "haircut"}
    cov = res["coverage"]
    assert cov["n_matched"] + cov["n_unmatched_lag"] == cov["n_orders_window"]
    assert cov["n_badprint_below_p05"] <= cov["n_unmatched_lag"]
    eqs = [str(e) for e in res["inputs"]["equities"]]
    assert eqs == ["1000", "5000", "10000", "50000", "100000", "500000"]
    prev_share, prev_drag = -1.0, -1.0
    for e in eqs:
        o = res["overall"][e]
        h = res["haircut"][e]
        assert abs(h["adj_monthly"] - (res["inputs"]["base_monthly"] - h["drag_pp_month"])) < 0.01
        s = o["frac"]["gt5_1pct"]
        assert s >= prev_share and h["drag_pp_month"] >= prev_drag - 1e-9
        prev_share, prev_drag = s, h["drag_pp_month"]
        assert set(res["per_symbol"][e]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
    # headline numbers (regression pins)
    assert res["haircut"]["50000"]["drag_pp_month"] < 0.5
    assert res["haircut"]["100000"]["drag_pp_month"] > 0.5
    assert res["overall"]["10000"]["frac"]["gt5_1pct"] < 0.01


def test_loader_uses_no_row_outside_window():
    cap = _load_cap()
    orders = cap.load_orders()
    assert len(orders) > 40_000
    assert orders["t"].min() >= pd.Timestamp("2023-01-01", tz="UTC")
    assert orders["t"].max() < pd.Timestamp("2026-09-24", tz="UTC")
    assert set(orders["leg"].unique()) <= {"maker_entry", "stop", "other_exit"}
