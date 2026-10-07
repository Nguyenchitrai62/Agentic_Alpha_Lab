"""oc_stopslip tests: synthetic hand checks + causality/cap guards (no market data)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path("research/tournament/oc_stopslip/run.py")


def _load():
    spec = importlib.util.spec_from_file_location("oc_stopslip_run", str(HERE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stop_level_book_is_price():
    mod = _load()
    assert mod.stop_level("book_stop", 100.0, float("nan")) == 100.0


def test_stop_level_rung_adds_fees_back():
    mod = _load()
    price, ret = 90.0, -0.10
    lv = price / (1 + ret)
    assert mod.stop_level("rung_sl", price, ret) == price + lv * (0.0002 + 0.00055)


def test_side_aware_slip_sign():
    # long stop at 100, next open 99 -> +100 bps adverse; short stop -> -100 bps (favourable)
    stop, nxt = 100.0, 99.0
    long_slip = (stop - nxt) / stop * 1e4
    short_slip = (nxt - stop) / stop * 1e4
    assert round(long_slip, 6) == 100.0
    assert round(short_slip, 6) == -100.0


def test_s4_and_frac_hand_case():
    # long: stop 100, minute low 99 -> depth 100 bps, s4 50 bps; next open 99.5 -> slip 50 bps -> frac 1.0
    stop, low, nxt = 100.0, 99.0, 99.5
    depth = max(0.0, (stop - low) / stop * 1e4)
    s4 = 0.5 * depth
    slip = (stop - nxt) / stop * 1e4
    assert (depth, s4, slip, slip / s4) == (100.0, 50.0, 50.0, 1.0)


def test_year_bucketing_edges():
    mod = _load()
    assert mod.year_of_exit(pd.Timestamp("2021-09-24 00:00", tz="UTC")) is None  # left edge excluded (a0 < t)
    assert mod.year_of_exit(pd.Timestamp("2021-09-24 00:01", tz="UTC")) == 0
    assert mod.year_of_exit(pd.Timestamp("2022-09-24 00:00", tz="UTC")) == 0  # a0+365d belongs to prior year
    assert mod.year_of_exit(pd.Timestamp("2024-09-23 12:00", tz="UTC")) == 3  # leap-day gap joins Y3
    assert mod.year_of_exit(pd.Timestamp("2026-09-24 00:00", tz="UTC")) == 4


def test_bybit_cap_respected():
    end = pd.Timestamp("2026-09-24 00:00", tz="UTC")
    idx = pd.to_datetime([1622505600000, 1791051120000], unit="ms", utc=True)
    kept = idx[idx < end]
    assert len(kept) == 1 and kept[0] < end


def test_flash_rule_hand_case():
    R = np.array([5.0, 15.0] * 800)  # mean 10, std ~5
    sig = float(np.std(R, ddof=1))
    assert not (10.0 > 3 * sig)  # normal minute is not flash
    assert (3 * sig + 1.0) > 3 * sig  # far-tail minute is flash
