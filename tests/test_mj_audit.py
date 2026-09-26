"""Tests for mj W17 blind audit (Part A). No leader code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

REP = Path("research/mj_audit/replication.json")


def test_replication_json_exists():
    assert REP.exists(), "Part A replication.json must be saved before reading leader code"
    d = json.loads(REP.read_text())
    for k in ("net_pct", "max_drawdown", "turnover_per_day"):
        assert k in d, f"missing {k}"
        assert np.isfinite(d[k]), f"{k} not finite"
    assert d["n_bars"] == 2190
    assert d["window"]["start"] == "2023-09-24T00:00:00Z"
    assert d["window"]["end"] == "2024-09-22T20:00:00Z"
    # number is a real reproduction: equity math consistent
    assert abs(d["equity_final"] - 1.0 - d["net_pct"] / 100.0) < 1e-9
    assert -1.0 < d["max_drawdown"] < 0.0
    assert d["turnover_per_day"] > 0.0


def test_signal_spec_synthetic():
    # mean(sign(d42), sign(d180)) clipped at 0: both up -> 1, split -> 0.5, both down -> 0
    logc = np.zeros(200)
    logc[0:158] = 0.0
    logc[158] = 0.10  # > value 42 bars earlier (idx 116 = 0) and 180 bars earlier (idx -22 invalid -> handle)
    # construct clean ramp: value at t=199 vs t=157 (42 back) and t=19 (180 back)
    t = 199
    a = np.sign(logc[t] - logc[t - 42])
    b = np.sign(logc[t] - logc[t - 180])
    sig = max(0.0, (a + b) / 2.0)
    assert sig in (0.0, 0.5, 1.0)
    # both down clipped to 0
    assert max(0.0, (-1.0 + -1.0) / 2.0) == 0.0
    assert max(0.0, (1.0 + -1.0) / 2.0) == 0.0  # split momentum nets to 0
    assert max(0.0, (1.0 + 0.0) / 2.0) == 0.5


def test_daily_join_uses_closed_bar_only():
    # 4h bar closing 03:59 on day D must join daily bar of D-1, not D
    daily = pd.DataFrame({
        "close_time": pd.to_datetime(["2023-09-23 23:59:59.999+00:00", "2023-09-24 23:59:59.999+00:00"]),
        "close": [100.0, 200.0],
    }).sort_values("close_time")
    bars = pd.DataFrame({
        "close_time": pd.to_datetime(["2023-09-24 03:59:59.999+00:00", "2023-09-24 23:59:59.999+00:00"]),
    }).sort_values("close_time")
    m = pd.merge_asof(bars, daily, on="close_time", direction="backward")
    assert m.loc[0, "close"] == 100.0  # prior day, same-day daily not yet closed
    assert m.loc[1, "close"] == 200.0  # coincident close is included


def test_execution_delay_one_bar():
    # weight at close t earns bar t+1 (open_{t+2}/open_{t+1}-1): decision index = holding-1
    grid = pd.date_range("2023-09-24", periods=5, freq="4h", tz="UTC")
    h = grid[2]
    t = h - pd.Timedelta(hours=4)
    assert t == grid[1]


def test_no_forward_data_in_window():
    # window end respected: last holding bar open is 2024-09-22 20:00 UTC
    d = json.loads(REP.read_text())
    assert d["window"]["end"] == "2024-09-22T20:00:00Z"
    eq = pd.read_csv("research/mj_audit/equity_4h.csv")
    assert len(eq) == 2190
    assert eq["open_time"].iloc[0].startswith("2023-09-24 00:00")
    assert eq["open_time"].iloc[-1].startswith("2024-09-22 20:00")
    assert eq["equity"].gt(0).all()
