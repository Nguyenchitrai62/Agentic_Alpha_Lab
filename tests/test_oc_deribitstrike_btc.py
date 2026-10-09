"""Tests for oc_deribitstrike_BTC (strike-level Deribit fetch/aggregate)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research" / "tournament" / "oc_deribitstrike_BTC"))

import pandas as pd
from strike_lib import aggregate_hourly, dedup_pages, next_start, parse_instrument


def test_parse_instrument():
    p = parse_instrument("BTC-4JUN21-41000-C")
    assert p["strike"] == 41000.0 and p["cp"] == "C"
    assert str(p["expiry"].date()) == "2021-06-04"
    p2 = parse_instrument("BTC-27DEC24-50000-P")
    assert p2["strike"] == 50000.0 and p2["cp"] == "P"
    for bad in ["BTC-4JUN21-41000-X", "BTC-41000-C", "BTC-XX-41000-C", "BTC-4JUN21-ABC-C"]:
        try:
            parse_instrument(bad)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad}")


def test_paging_dedup_boundary_equal_timestamps():
    # Two pages sharing the last millisecond: page1 ends at ts=1000 (ids a,b),
    # page2 fetched with start=1000 repeats b then adds c. De-dup keeps a,b,c once.
    page1 = [{"trade_id": "a", "timestamp": 999}, {"trade_id": "b", "timestamp": 1000}]
    page2 = [{"trade_id": "b", "timestamp": 1000}, {"trade_id": "c", "timestamp": 1000}]
    merged = dedup_pages([page1, page2])
    assert sorted(t["trade_id"] for t in merged) == ["a", "b", "c"]
    # cursor helper: repeat of same ts with no new trades must advance by 1ms
    assert next_start(1000, 1000, 0) == 1001
    # normal case: resume at last timestamp
    assert next_start(1000, 900, 2) == 1000


def _t(tid, ts_ms, name, price, iv, index, amount, direction, block=None):
    t = {"trade_id": tid, "timestamp": ts_ms, "instrument_name": name,
         "price": price, "mark_price": price, "iv": iv, "index_price": index,
         "amount": amount, "direction": direction}
    if block is not None:
        t["block_trade_id"] = block
    return t


def test_hourly_aggregation_hand_case():
    # Hour 2021-06-01 00:00 UTC, instrument BTC-25JUN21-35000-P (expiry 2021-06-25).
    # trades: buy 2.0 @0.0100 iv 80 idx 36000; sell 1.0 @0.0200 iv 90 idx 36000 (block).
    # DTE = 24.x days -> kept (<=100).
    h = 1622505600000  # 2021-06-01 00:00:00 UTC
    trades = [
        _t("1", h + 1000, "BTC-25JUN21-35000-P", 0.01, 80.0, 36000.0, 2.0, "buy"),
        _t("2", h + 2000, "BTC-25JUN21-35000-P", 0.02, 90.0, 36000.0, 1.0, "sell", block="BLOCK-1"),
    ]
    agg = aggregate_hourly(trades)
    assert len(agg) == 1
    r = agg.iloc[0]
    assert r["n"] == 2
    assert r["sum_amount"] == 3.0
    assert abs(r["vwap_price"] - (0.01 * 2 + 0.02 * 1) / 3) < 1e-12
    assert abs(r["vwap_price_usd"] - ((0.01 * 36000) * 2 + (0.02 * 36000) * 1) / 3) < 1e-9
    assert abs(r["vwap_iv"] - (80 * 2 + 90 * 1) / 3) < 1e-9
    assert r["min_price"] == 0.01 and r["max_price"] == 0.02
    assert r["taker_buy_amount"] == 2.0 and r["taker_sell_amount"] == 1.0
    assert r["block_amount"] == 1.0
    assert str(r["hour"]) == "2021-06-01 00:00:00+00:00"


def test_dte_filter_drops_far_expiry():
    h = 1622505600000
    # expiry 2021-12-31 is ~213 days out -> dropped (max 100)
    trades = [_t("1", h + 1000, "BTC-31DEC21-50000-C", 0.05, 70.0, 36000.0, 1.0, "buy")]
    agg = aggregate_hourly(trades)
    assert len(agg) == 0
