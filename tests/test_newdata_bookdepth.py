"""Causality tests for the bookdepth feature module (dev-only, synthetic + real truncation)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "diagnostics" / "newdata_bookdepth"))

from features import FEATURES, attach_features  # noqa: E402

DEV_END = pd.Timestamp("2025-09-14", tz="UTC")


def _synthetic_depth() -> pd.DataFrame:
    ts = pd.date_range("2023-06-01", periods=600, freq="min", tz="UTC") + pd.Timedelta(seconds=31)
    n = len(ts)
    return pd.DataFrame({
        "minute": ts.floor("min"), "ts": ts,
        "bid_n1": 1e7 + np.arange(n) * 1e3, "ask_n1": 1e7 + np.arange(n) * 5e2,
        "bid_n2": 2e7 + np.arange(n) * 1e3, "ask_n2": 2e7 + np.arange(n) * 5e2,
        "bid_n5": 5e7, "ask_n5": 5e7,
        "total_1": 2e7 + np.arange(n) * 1.5e3,
    })


def test_strictly_before_fill_minute():
    d = _synthetic_depth()
    T = d["ts"].iloc[100]  # decision exactly at a snapshot time
    dec = pd.DataFrame({"sym": ["BTCUSDT"], "T": [T]})
    f = attach_features(dec, {"BTCUSDT": d})
    # strict <: must use snapshot 99, whose bid_n1 is known
    assert f["bd_imb_1"].iloc[0] == (d["bid_n1"].iloc[99] - d["ask_n1"].iloc[99]) / d["total_1"].iloc[99]
    assert f["bd_chg_bid_15"].iloc[0] == d["bid_n1"].iloc[99] / d["bid_n1"].iloc[85] - 1.0
    assert f["bd_chg_bid_60"].iloc[0] == d["bid_n1"].iloc[99] / d["bid_n1"].iloc[40] - 1.0


def test_truncation_equality_synthetic():
    d = _synthetic_depth()
    T = pd.date_range("2023-06-01 02:00", periods=50, freq="7min", tz="UTC")
    dec = pd.DataFrame({"sym": "BTCUSDT", "T": T})
    full = attach_features(dec, {"BTCUSDT": d})
    cut = T[30]
    trunc = d[d["ts"] < cut].reset_index(drop=True)
    part = attach_features(dec.iloc[:31], {"BTCUSDT": trunc})
    pd.testing.assert_frame_equal(full.iloc[:31], part, check_dtype=False)


def test_missing_history_is_nan():
    d = _synthetic_depth()
    dec = pd.DataFrame({"sym": ["BTCUSDT"], "T": [d["ts"].iloc[0] - pd.Timedelta(seconds=1)]})
    f = attach_features(dec, {"BTCUSDT": d})
    assert f[["bd_imb_1", "bd_chg_bid_60"]].isna().all(axis=None)


def test_truncation_equality_real():
    from features import load_depth
    depth = {s: load_depth(s) for s in ("BTCUSDT", "ETHUSDT")}
    fills = pd.read_parquet("research/diagnostics/phase_agents/fills_U.parquet")
    fills["t_fill"] = pd.to_datetime(fills["t_fill"], utc=True)
    dev = fills[(fills["t_exit"] < DEV_END) & (fills["sym"].isin(depth))
                & (fills["t_fill"] >= "2023-01-01")].head(400)
    assert (dev["t_exit"] < DEV_END).all()  # dev-only
    dec = pd.DataFrame({"sym": dev["sym"].to_numpy(), "T": dev["t_fill"].to_numpy()}, index=dev.index)
    full = attach_features(dec, depth)
    cut = dev["t_fill"].quantile(0.5)
    trunc = {s: dd[dd["ts"] < cut].reset_index(drop=True) for s, dd in depth.items()}
    early = dec[dec["T"] <= cut]
    part = attach_features(early, trunc)
    pd.testing.assert_frame_equal(full.loc[early.index], part, check_dtype=False)
    # every joined snapshot is strictly before its decision time
    for sym, grp in early.groupby("sym"):
        ts = trunc[sym]["ts"].to_numpy(dtype="datetime64[ns]")
        T = pd.to_datetime(grp["T"], utc=True).to_numpy(dtype="datetime64[ns]")
        i = np.searchsorted(ts, T, side="left") - 1
        assert (ts[np.clip(i, 0, len(ts) - 1)] < T).all()
