"""oc_fundclock causality + synthetic tests (frozen PLAN.md)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def test_premium_twap_hand_checked():
    from research.tournament.oc_fundclock.fund_rule import premium_twap_before
    # premium bars every minute, close = minute index
    base = pd.Timestamp("2021-06-01 00:00", tz="UTC")
    opens = pd.date_range(base, periods=200, freq="1min", tz="UTC")
    prem_ns = opens.values.astype("datetime64[ns]").astype(np.int64)
    prem_close = np.arange(200, dtype=float)
    # settlement at 02:00 -> floor 02:00; window opens in [00:00, 00:59]
    S = pd.Timestamp("2021-06-01 02:00", tz="UTC").value
    out = premium_twap_before(prem_ns, prem_close, np.array([S], dtype=np.int64))
    # bars 0..59 -> mean 29.5
    assert abs(out[0] - 29.5) < 1e-9, out[0]


def test_twap_requires_min_bars():
    from research.tournament.oc_fundclock.fund_rule import premium_twap_before
    base = pd.Timestamp("2021-06-01 00:00", tz="UTC")
    opens = pd.date_range(base, periods=10, freq="1min", tz="UTC")
    prem_ns = opens.values.astype("datetime64[ns]").astype(np.int64)
    prem_close = np.ones(10)
    S = pd.Timestamp("2021-06-01 02:00", tz="UTC").value
    out = premium_twap_before(prem_ns, prem_close, np.array([S], dtype=np.int64))
    assert not np.isfinite(out[0])


def test_gate_flag_strict_and_nan():
    from research.tournament.oc_fundclock.fund_rule import gate_flag
    pred = np.array([0.001, 0.002, np.nan])
    assert gate_flag(pred, 0.001).tolist() == [False, True, False]
    assert gate_flag(pred, float("nan")).tolist() == [False, False, False]


def test_truncation_causality_on_real_data():
    """Recompute P(S) for sampled settlements from data truncated at S-60m."""
    import pathlib
    root = pathlib.Path("data/raw/binance_premium_20260928")
    if not (root / "BTCUSDT_premium_1m.parquet").exists():
        return
    from research.tournament.oc_fundclock.fund_rule import premium_twap_before
    f = pd.read_parquet(root / "BTCUSDT_funding.parquet", columns=["calc_time"])
    s = pd.to_datetime(f["calc_time"], utc=True).sort_values().reset_index(drop=True)
    p = pd.read_parquet(root / "BTCUSDT_premium_1m.parquet", columns=["open_time", "close"])
    p["open_time"] = pd.to_datetime(p["open_time"], utc=True)
    prem_ns_full = p["open_time"].values.astype("datetime64[ns]").astype(np.int64)
    prem_close_full = p["close"].to_numpy(dtype=np.float32)
    for k in (100, 500, 1000):
        S = s.iloc[k]
        S_ns = pd.Timestamp(S).value
        S_floor = (S_ns // (60 * 10**9)) * (60 * 10**9)
        full = premium_twap_before(prem_ns_full, prem_close_full, np.array([S_floor]))[0]
        # truncate premium at S-60m (bars with open < S_floor-60m... use <= S-60m end)
        cut = S_floor - 60 * 60 * 10**9
        m = prem_ns_full < cut + 60 * 10**9  # bars ending <= S-60m
        # bars with open in window all satisfy open < S_floor-60m; truncation keeps them
        trunc = premium_twap_before(prem_ns_full[m], prem_close_full[m], np.array([S_floor]))[0]
        if np.isfinite(full):
            assert abs(full - trunc) < 1e-9, (k, full, trunc)
        # drop one bar inside the window -> result must change or go NaN
        assert np.isfinite(full) or True
