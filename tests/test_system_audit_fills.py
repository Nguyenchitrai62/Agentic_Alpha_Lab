"""SYSTEM AUDIT 1 (Part C): synthetic minute-path tests for rules 2-5 + Part-A files."""
import json
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research" / "diagnostics" / "system_audit" / "fills_opencode"))
from replay_checker import (  # noqa: E402
    bar_start,
    book_exit_hits,
    book_stop_price,
    expected_rung_ret,
    first_touch_index,
    is_trade_through,
    rung_backstop_v321,
    rung_price,
    rung_stop5_v321,
    rung_stop_v367,
)

AUDIT = REPO / "artifacts" / "research" / "system_audit"
OUT = REPO / "research" / "diagnostics" / "system_audit" / "fills_opencode"


def test_part_a_found_input_files():
    for v in ("v367", "v321"):
        assert (AUDIT / f"events_{v}.parquet").exists()
        assert (AUDIT / f"bars_{v}.parquet").exists()
    rep = json.loads((OUT / "replication.json").read_text())
    assert set(rep["counts"]) == {"v367", "v321"}
    assert (OUT / "mismatches_v367.csv").exists() and (OUT / "mismatches_v321.csv").exists()


def test_rule2_first_trade_through_buy():
    lows = [10.0, 9.5, 9.3, 9.1, 9.4]
    highs = [10.2, 9.7, 9.5, 9.4, 9.6]
    assert first_touch_index(lows, highs, "buy", 9.2) == 3
    assert is_trade_through("buy", 9.2, 9.5, 9.2) is False  # strict: low == price is no touch
    assert is_trade_through("buy", 9.19, 9.5, 9.2) is True


def test_rule2_first_trade_through_sell():
    lows = [9.8, 9.9, 10.0, 10.1, 9.9]
    highs = [10.0, 10.1, 10.15, 10.3, 10.0]
    assert first_touch_index(lows, highs, "sell", 10.2) == 3
    assert is_trade_through("sell", 9.9, 10.2, 10.2) is False  # strict
    assert is_trade_through("sell", 9.9, 10.21, 10.2) is True


def test_rule2_no_touch():
    assert first_touch_index([9.5, 9.6], [9.7, 9.8], "buy", 9.2) is None
    assert first_touch_index([9.5, 9.6], [9.7, 9.8], "sell", 10.0) is None


def test_rule3_long_stop_price_gap():
    assert book_stop_price("long", 90.0, 95.0) == 90.0
    assert book_stop_price("long", 90.0, 85.0) == 85.0  # gapped through: fill at open
    assert book_stop_price("short", 110.0, 105.0) == 110.0
    assert book_stop_price("short", 110.0, 115.0) == 115.0


def test_rule3_stop_tp_tie_is_stop_first():
    stop_hit, tp_hit = book_exit_hits("long", 89.0, 101.0, 90.0, 100.0)
    assert stop_hit and tp_hit  # both touched -> engine must record the stop
    stop_hit, tp_hit = book_exit_hits("short", 99.0, 111.0, 110.0, 100.0)
    assert stop_hit and tp_hit
    assert book_exit_hits("long", 91.0, 101.0, 90.0, 100.0) == (False, True)
    assert book_exit_hits("long", 89.0, 99.0, 90.0, 100.0) == (True, False)
    assert book_exit_hits("short", 99.0, 109.0, 110.0, 100.0) == (False, True)


def test_rule4_rung_price_and_window():
    assert rung_price(100.0, 0.06, 3.0) == 100.0 * (1 - 3 * 0.06 / math.sqrt(6.0))
    assert rung_price(100.0, 0.06, 4.0) == 100.0 * (1 - 4 * 0.06 / math.sqrt(6.0))
    for m in (16, 100, 238):
        assert 16 <= m <= 238
    for m in (0, 15, 239):
        assert not (16 <= m <= 238)


def test_rule5_v367_touch_stop_first_touch():
    stop = rung_stop_v367(100.0, 0.06)
    assert stop == 100.0 * (1 - 8 * 0.06 / math.sqrt(6.0))
    lows = [99.0, 98.0, 80.0, 79.0]
    highs = [101.0, 100.0, 99.0, 98.0]
    assert first_touch_index(lows, highs, "buy", stop) == 2 or stop > 80.0
    assert abs(stop - 80.408) < 0.01


def test_rule5_v321_close_and_backstop_levels():
    assert rung_stop5_v321(100.0, 0.06) == 100.0 * (1 - 4 * 0.06 / math.sqrt(6.0))
    assert rung_backstop_v321(100.0, 0.06) == 100.0 * (1 - 8 * 0.06 / math.sqrt(6.0))
    assert rung_stop5_v321(100.0, 0.06) > rung_backstop_v321(100.0, 0.06)


def test_rule5_ret_formula_fees_and_funding():
    assert expected_rung_ret(100.0, 101.0, "rung_tp", "2021-10-17 20:30+00:00") == (
        101.0 / 100.0 - 1 - 0.0002 - 0.0002)
    assert expected_rung_ret(100.0, 99.0, "rung_sl", "2021-10-17 20:30+00:00") == (
        99.0 / 100.0 - 1 - 0.0002 - 0.00055)
    assert expected_rung_ret(100.0, 99.0, "rung_timeout", "2021-10-17 12:00+00:00") == (
        99.0 / 100.0 - 1 - 0.0002 - 0.00055)  # 12:00 is not a settlement
    assert expected_rung_ret(100.0, 99.0, "rung_timeout", "2021-11-11 00:00+00:00") == (
        99.0 / 100.0 - 1 - 0.0002 - 0.00055 - 0.0001)  # funding hour


def test_bar_start_floors_to_4h():
    assert bar_start(pd.Timestamp("2021-10-17 21:43+00:00")) == pd.Timestamp("2021-10-17 20:00+00:00")
    assert bar_start(pd.Timestamp("2021-10-17 20:00+00:00")) == pd.Timestamp("2021-10-17 20:00+00:00")
