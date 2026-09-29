"""Tests for the whale-burst reversal event study (synthetic + causality guards)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MOD = Path("research/diagnostics/whale_burst/whale_burst_study.py")


def load():
    spec = importlib.util.spec_from_file_location("whale_burst_study", MOD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


wb = load()
CUT = pd.Timestamp("2025-09-24 00:00", tz="UTC")


def test_cutoff_constant():
    assert wb.CUTOFF == CUT


def test_enforce_cutoff_drops_locked_minutes():
    ts = pd.DatetimeIndex([
        "2025-09-23 23:58+00:00", "2025-09-23 23:59+00:00",
        "2025-09-24 00:00+00:00", "2025-09-24 00:01+00:00",
    ])
    mask = wb.enforce_cutoff(ts)
    assert mask.tolist() == [True, True, False, False]


def test_assert_cutoff_rejects_locked_data():
    ts = pd.date_range("2025-09-23 23:00", periods=200, freq="min", tz="UTC")
    with pytest.raises(AssertionError):
        wb.assert_cutoff(ts, "synthetic")
    wb.assert_cutoff(ts[:60], "synthetic-ok")  # 23:00..23:59, all < cutoff


def test_no_fill_on_touch_without_trade_through():
    assert wb.find_fill_long(100.0, np.array([101.0, 100.5, 100.0, 100.2])) is None
    assert wb.find_fill_short(100.0, np.array([99.0, 99.5, 100.0, 99.8])) is None
    assert wb.find_fill_long(100.0, np.array([101.0, 99.99])) == 1
    assert wb.find_fill_short(100.0, np.array([99.0, 100.01])) == 1


def test_stop_first_tie_long_and_short():
    px, kind, fee = wb.resolve_exit_long(98.5, 101.0,
                                         np.array([100.0]), np.array([102.0]),
                                         np.array([98.0]), 99.0)
    assert kind == "stop" and fee == wb.TAKER and px == pytest.approx(98.5)
    px, kind, fee = wb.resolve_exit_short(101.5, 99.0,
                                          np.array([100.0]), np.array([102.0]),
                                          np.array([98.0]), 101.0)
    assert kind == "stop" and fee == wb.TAKER and px == pytest.approx(101.5)


def test_stop_gap_fills_at_open():
    # long stop gapped through: open below stop -> fill at the worse open
    px, kind, _ = wb.resolve_exit_long(98.5, 110.0,
                                       np.array([97.0]), np.array([97.5]),
                                       np.array([96.0]), 99.0)
    assert kind == "stop" and px == pytest.approx(97.0)
    # short stop gapped through: open above stop -> fill at open
    px, kind, _ = wb.resolve_exit_short(101.5, 90.0,
                                        np.array([103.0]), np.array([104.0]),
                                        np.array([102.0]), 101.0)
    assert kind == "stop" and px == pytest.approx(103.0)


def test_tp_touch_fills_at_tp_maker():
    px, kind, fee = wb.resolve_exit_long(90.0, 101.0,
                                         np.array([100.0]), np.array([101.5]),
                                         np.array([99.5]), 99.0)
    assert kind == "tp" and fee == wb.MAKER and px == pytest.approx(101.0)


def test_net_bps_signs():
    assert wb.net_bps_long(100.0, 101.0, wb.MAKER) > 0
    assert wb.net_bps_long(100.0, 99.0, wb.TAKER) < 0
    assert wb.net_bps_short(100.0, 99.0, wb.MAKER) > 0
    assert wb.net_bps_short(100.0, 101.0, wb.TAKER) < 0


def test_dedup_sixty_minute_window():
    got = wb.dedup_positions(np.array([0, 30, 60, 119, 120]))
    assert got.tolist() == [0, 60, 120]
    assert wb.dedup_positions(np.array([])).size == 0


def test_year_of_bins():
    ts = pd.DatetimeIndex(["2021-09-24 00:00+00:00", "2023-01-01 00:00+00:00",
                           "2025-09-23 23:59+00:00", "2021-09-23 23:59+00:00",
                           "2025-09-24 00:00+00:00"])
    assert wb.year_of(ts).tolist() == [1, 2, 4, 0, 0]


def _grid(n=400, px=100.0):
    # Flat grid that triggers NOTHING: lows above any long limit, highs below
    # any short limit (limits sit at ~px for d=0), so tests opt into fills.
    O = np.full(n, px)
    H = np.full(n, px * 1.0005)
    L = np.full(n, px * 0.9995)
    C = np.full(n, px)
    return O, H, L, C


def _quiet_long_grid(n=400, px=100.0):
    O = np.full(n, px)
    H = np.full(n, px + 0.01)  # never touches TP (>=100.3) nor trips anything
    L = np.full(n, px + 0.05)  # strictly above the d=0 long limit: no fill
    C = np.full(n, px)
    return O, H, L, C


def _quiet_short_grid(n=400, px=100.0):
    O = np.full(n, px)
    H = np.full(n, px - 0.05)  # strictly below the d=0 short limit: no fill
    L = np.full(n, px - 0.01)
    C = np.full(n, px)
    return O, H, L, C


def test_simulate_long_fill_and_timed_exit():
    O, H, L, C = _quiet_long_grid()
    L[102] = 99.0  # trade-through below limit 100*(1-0)=100 at m+2
    E = np.array([100])
    fill, net, kind = wb.simulate(E, "long", 0.0, 0.003, 60, O, H, L, C)
    assert fill[0] == 102
    assert kind[0] == "timed"  # flat market touches nothing
    # timed exit at open[f+60] with taker fee on a flat line: small loss
    assert net[0] == pytest.approx(wb.net_bps_long(100.0, 100.0, wb.TAKER))


def test_simulate_no_fill_without_trade_through():
    O, H, L, C = _quiet_long_grid()
    L[102] = 100.0  # exact touch is not a fill
    E = np.array([100])
    fill, net, kind = wb.simulate(E, "long", 0.0, 0.003, 60, O, H, L, C)
    assert fill[0] == -1 and np.isnan(net[0])


def test_simulate_short_stop_first():
    O, H, L, C = _quiet_short_grid()
    H[105] = 101.0  # trade-through above limit 100*(1+0)
    H[110] = 103.0  # blows through stop 101.5 the same minute low dips under TP
    L[110] = 98.0
    E = np.array([100])
    fill, net, kind = wb.simulate(E, "short", 0.0, 0.01, 60, O, H, L, C)
    assert fill[0] == 105
    assert kind[0] == "stop"
    assert net[0] < 0
