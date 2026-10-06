"""Tests for research/tournament/oc_deliverytrack (tracking error of spot-leg sale)."""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "tournament" / "oc_deliverytrack"))

from compute_deliverytrack import ret_alloc, te_bp, window_stats

RES = ROOT / "research" / "tournament" / "oc_deliverytrack" / "results.json"


def _synth(base: float = 100.0, drift: float = 0.0) -> pd.DataFrame:
    d = pd.Timestamp("2024-12-27 08:00", tz="UTC")
    idx = pd.date_range(d - pd.Timedelta(minutes=30), d + pd.Timedelta(minutes=15), freq="min", tz="UTC")
    n = len(idx)
    close = base + drift * (pd.Series(range(n)) - 15) / 15.0
    return pd.DataFrame({
        "open_time": idx,
        "open": close - 0.01, "high": close + 0.02, "low": close - 0.02,
        "close": close, "volume": 10.0,
    }), d


def test_te_bp_hand_checked():
    assert te_bp(101.0, 100.0) == 100.0
    assert te_bp(99.5, 100.0) == -50.0


def test_ret_alloc_hand_checked():
    # S_entry=100, F_entry=102, exit=101: (1/100)+(1/102)-0.00275
    assert abs(ret_alloc(101.0, 102.0, 100.0) - (0.01 + 1 / 102 - 0.00275)) < 1e-12
    # exit == entry spot and future at same price -> -fees only
    assert abs(ret_alloc(100.0, 100.0, 100.0) + 0.00275) < 1e-12


def test_window_stats_flat_synthetic():
    df, d = _synth(100.0, 0.0)
    ws = window_stats(df, d)
    assert ws["twap"] == 100.0
    assert ws["px_open08"] == 99.99
    assert ws["px_0815"] == 99.99
    assert ws["slices6"] == 100.0
    assert ws["vwap_0800_0805"] == 100.0  # typical=(H+L+C)/3 with symmetric band
    assert te_bp(ws["slices6"], ws["twap"]) == 0.0


def test_window_stats_drift_slices_beat_single():
    df, d = _synth(100.0, drift=1.0)  # trending up into delivery
    ws = window_stats(df, d)
    # single 08:15 print is farthest from the 07:30-08:00 average on a trend
    assert abs(te_bp(ws["px_0815"], ws["twap"])) > abs(te_bp(ws["slices6"], ws["twap"]))


def test_window_stats_coverage_error():
    df, d = _synth()
    short = df.iloc[5:].reset_index(drop=True)  # pre-window incomplete
    assert "coverage_error" in window_stats(short, d)


def test_results_json_consistency():
    o = json.loads(RES.read_text(encoding="utf-8"))
    assert o["meta"]["n_trades"] == 33 and o["meta"]["n_binance_ok"] == 33
    assert len(o["deliveries"]) == 33
    for r in o["deliveries"]:
        b = r["binance"]
        for m in ("px_open08", "vwap_0800_0805", "px_0815", "slices6"):
            assert abs(b["te_bp"][m] - te_bp(b[m], b["twap"])) < 1e-9
            assert abs(b["dret_pp_vs_twap"][m] - (ret_alloc(b[m], r["F_entry"], r["S_entry"]) - b["ret_exit_twap"]) * 100) < 1e-9
    # summary worst matches per-delivery max
    worst = max(abs(r["binance"]["te_bp"]["slices6"]) for r in o["deliveries"])
    assert abs(o["summary"]["slices6"]["te_bp_worst_abs"] - worst) < 1e-9
    assert abs(o["summary"]["slices6"]["te_bp_worst_abs"] - 19.557424923171435) < 1e-6


def test_real_data_window_has_30_bars():
    df = pd.read_parquet(
        ROOT / "data" / "raw" / "btc_intraday_20260924" / "klines_1m_2024.parquet",
        columns=["open_time", "open", "high", "low", "close", "volume"],
    )
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    d = pd.Timestamp("2024-12-27 08:00", tz="UTC")
    pre = df.loc[(df["open_time"] >= d - pd.Timedelta(minutes=30)) & (df["open_time"] < d)]
    assert len(pre) == 30
