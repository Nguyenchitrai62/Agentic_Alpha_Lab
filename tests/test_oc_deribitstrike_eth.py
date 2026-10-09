"""Tests for oc_deribitstrike_ETH (strike-level hourly Deribit cache).

Covers: paging de-duplication on a synthetic page boundary with equal
timestamps; instrument-name parsing; hourly aggregation on a hand case.
No network access.
"""

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CANDIDATES = [
    ROOT / "research" / "tournament" / "oc_deribitstrike_ETH" / "fetch_eth_strike.py",
]
for c in CANDIDATES:
    if c.exists():
        sys.path.insert(0, str(c.parent))
        break

from fetch_eth_strike import aggregate_hourly, dedup_pages, parse_instrument


def test_parse_instrument_basic():
    exp, strike, cp = parse_instrument("ETH-4JUN21-2500-P")
    assert strike == 2500.0 and cp == "P"
    assert (exp.year, exp.month, exp.day) == (2021, 6, 4)


def test_parse_instrument_bad():
    for bad in ["ETH-4JUN21-2500", "ETH-4JUN21-2500-X", "GARBAGE", "ETH-XX-1-P"]:
        try:
            parse_instrument(bad)
        except ValueError:
            continue
        raise AssertionError(f"should have raised for {bad!r}")


def test_paging_dedup_equal_timestamps():
    # Two pages sharing the last millisecond: the trade at the boundary must
    # survive exactly once (the +1 paging bug would drop same-ms trades).
    a = {"trade_id": "ETH-1", "timestamp": 1000}
    b = {"trade_id": "ETH-2", "timestamp": 1000}
    c = {"trade_id": "ETH-3", "timestamp": 1001}
    page1 = [a, b]  # last timestamp = 1000
    page2 = [b, c]  # inclusive paging replays the boundary trade
    merged = dedup_pages([page1, page2])
    assert sorted(t["trade_id"] for t in merged) == ["ETH-1", "ETH-2", "ETH-3"]


def _t(tid, ts_ms, name, price, index, amount, direction, iv=50.0, block=None):
    r = {
        "trade_id": tid,
        "timestamp": ts_ms,
        "instrument_name": name,
        "price": price,
        "mark_price": price,
        "iv": iv,
        "index_price": index,
        "amount": amount,
        "direction": direction,
    }
    if block is not None:
        r["block_trade_id"] = block
    return r


def test_aggregate_hourly_hand_case():
    # Hour 2021-06-04 00:00 UTC, instrument ETH-25JUN21-3000-C (DTE=21 <= 100).
    h0 = int(pd.Timestamp("2021-06-04 00:10:00", tz="UTC").timestamp() * 1000)
    h1 = int(pd.Timestamp("2021-06-04 00:20:00", tz="UTC").timestamp() * 1000)
    h2 = int(pd.Timestamp("2021-06-04 01:05:00", tz="UTC").timestamp() * 1000)
    name = "ETH-25JUN21-3000-C"
    trades = [
        _t("ETH-a", h0, name, 0.01, 2500.0, 2.0, "buy", iv=60.0),
        _t("ETH-b", h1, name, 0.02, 2600.0, 2.0, "sell", iv=80.0),
        _t("ETH-c", h2, name, 0.03, 2700.0, 1.0, "buy", iv=70.0),
        # Far expiry (>100 DTE) must be dropped.
        _t("ETH-far", h0, "ETH-31DEC30-3000-C", 0.05, 2500.0, 5.0, "buy", iv=90.0),
    ]
    out = aggregate_hourly(trades)
    assert len(out) == 2  # two (hour, instrument) groups; far-expiry dropped
    r0 = out.iloc[0]
    assert str(r0["hour"]) == "2021-06-04 00:00:00+00:00"
    assert r0["n"] == 2
    assert r0["sum_amount"] == 4.0
    # VWAP price = (0.01*2 + 0.02*2)/4 = 0.015
    assert abs(r0["vwap_price"] - 0.015) < 1e-12
    # VWAP USD = (0.01*2500*2 + 0.02*2600*2)/4 = (50+104)/4 = 38.5
    assert abs(r0["vwap_price_usd"] - 38.5) < 1e-9
    # VWAP iv = (60*2 + 80*2)/4 = 70
    assert abs(r0["vwap_iv"] - 70.0) < 1e-12
    assert r0["min_price"] == 0.01 and r0["max_price"] == 0.02
    assert r0["taker_buy_amount"] == 2.0 and r0["taker_sell_amount"] == 2.0
    assert r0["strike"] == 3000.0 and r0["cp"] == "C"
    assert abs(r0["dte_hour"] - 21.0) < 1e-9
    # VWAP index = (2500*2 + 2600*2)/4 = 2550
    assert abs(r0["vwap_index"] - 2550.0) < 1e-9


def test_aggregate_hourly_truncation_causal():
    # A trade at 00:59:59.999 belongs to the 00:00 hour, never to 01:00.
    ts = int(pd.Timestamp("2021-06-04 00:59:59.999", tz="UTC").timestamp() * 1000)
    trades = [_t("ETH-x", ts, "ETH-25JUN21-3000-P", 0.02, 2500.0, 1.0, "sell")]
    out = aggregate_hourly(trades)
    assert len(out) == 1
    assert str(out.iloc[0]["hour"]) == "2021-06-04 00:00:00+00:00"
