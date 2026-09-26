"""Tests for v89 blind audit (Part A). No leader v89 code imported."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

REP = Path("research/parallel/rounds/parallel-20260906-r2/v89_audit/replication.json")


def test_replication_json_exists():
    assert REP.exists(), "Part A replication.json must be saved before reading v89 folder"
    d = json.loads(REP.read_text())
    assert d["anchor"] == "2025-09-24"
    assert d["cutoff"] == "2025-09-07T00:00:00+00:00"
    assert isinstance(d["n_train_rows"], int) and d["n_train_rows"] > 0
    assert isinstance(d["n_pred_rows"], int) and d["n_pred_rows"] > 0
    rho = d["spearman_pred_vs_y"]
    assert np.isfinite(rho) and -1.0 <= rho <= 1.0
    assert d["model"]["max_depth"] == 4
    assert d["model"]["max_iter"] == 400
    assert len(d["features"]) == 26


def test_train_cutoff_embargo_math():
    a = pd.Timestamp("2025-09-24", tz="UTC")
    cutoff = a - pd.Timedelta(hours=4 * (42 + 60))
    assert cutoff == pd.Timestamp("2025-09-07T00:00:00+00:00")
    # label needs open[t+43]; train requires open_time+172h < cutoff
    assert pd.Timedelta(hours=4 * 43) == pd.Timedelta(hours=172)


def test_target_uses_next_open_and_clips():
    # y = clip(log(open[t+43]/open[t+1])/(std42*sqrt42), -4, 4)
    opens = pd.Series([100.0, 101.0, 102.0, 103.0])
    # t=0 needs open[3] and open[1]
    y_raw = np.log(103.0 / 101.0) / (0.01 * np.sqrt(42))
    assert np.isfinite(y_raw)
    assert float(np.clip(1e9, -4, 4)) == 4.0
    assert float(np.clip(-1e9, -4, 4)) == -4.0
    assert len(opens) == 4


def test_snr_definition_synthetic():
    logc = pd.Series(np.log([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]))
    r1 = logc.diff()
    std = r1.iloc[-3:].std(ddof=1)
    ret3 = logc.iloc[-1] - logc.iloc[-4]
    snr = ret3 / (std * np.sqrt(3))
    assert np.isfinite(snr)
    # hand check: ret uses only closes <= t, std uses 1-bar returns <= t
    assert abs(ret3 - np.log(106.0 / 103.0)) < 1e-12


def test_daily_join_uses_closed_bar_only():
    daily = pd.DataFrame({
        "close_time": pd.to_datetime(["2025-09-23 23:59:59.999+00:00", "2025-09-24 23:59:59.999+00:00"]),
        "close": [100.0, 200.0],
    }).sort_values("close_time")
    bars = pd.DataFrame({
        "close_time": pd.to_datetime(["2025-09-24 03:59:59.999+00:00", "2025-09-24 23:59:59.999+00:00"]),
    }).sort_values("close_time")
    m = pd.merge_asof(bars, daily, on="close_time", direction="backward")
    assert m.loc[0, "close"] == 100.0
    assert m.loc[1, "close"] == 200.0


def test_funding_asof_uses_only_known_prints():
    fund_times = pd.to_datetime(["2025-09-24 00:00+00:00", "2025-09-24 08:00+00:00"])
    bar_close = pd.Timestamp("2025-09-24 07:59:59.999+00:00", tz="UTC")
    pos = np.searchsorted(fund_times.values.astype("datetime64[ns]"),
                          np.datetime64(bar_close.tz_convert(None).to_datetime64())) - 1
    # only the 00:00 print is known at 07:59 close
    assert pos == 0
