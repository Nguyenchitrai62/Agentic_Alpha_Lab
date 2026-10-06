"""Tests for oc_paperparity (paper == research order-by-order).

- Pure unit tests of the replay fill rules (trade-through, placement-minute
  exclusion, stop-first, outage exclusion, cancel-bounded windows).
- One integration check on research/diagnostics/oc_paperparity/results.json
  (verdict PARITY, 0 real_bug, fills/P&L sane). Regenerating results needs
  network (public Bybit klines); the test only reads the committed file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MOD = Path("research/diagnostics/oc_paperparity/check_parity.py")
RES = Path("research/diagnostics/oc_paperparity/results.json")


def _load_mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location("oc_paperparity_mod", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_replay_rules_pure():
    m = _load_mod()
    bars = [{"t": 1000, "o": 10.0, "h": 10.1, "l": 9.9, "c": 10.0},
            {"t": 2000, "o": 10.0, "h": 10.0, "l": 9.5, "c": 9.6},
            {"t": 3000, "o": 9.6, "h": 9.7, "l": 9.55, "c": 9.6}]
    # strict trade-through: low < price; placement minute (t=1000) never fills
    assert m.expected_limit_buy_fill(9.9, 1000, bars) == 2000
    assert m.expected_limit_buy_fill(9.9, 2000, bars) == 3000  # 9.55 < 9.9
    assert m.expected_limit_buy_fill(9.5, 2000, bars) is None  # low == price is not a trade-through
    assert m.expected_limit_buy_fill(9.0, 0, bars) is None  # above-market buy fills at once; deep bid never touched
    # stop triggers on low <= trigger
    assert m.expected_stop_trigger(9.5, 1000, bars) == 2000
    assert m.expected_stop_trigger(9.5, 2000, bars) is None
    # TP sell fills on high > price
    assert m.expected_tp_sell_fill(9.65, 1000, bars) == 2000  # first bar with high > price
    assert m.expected_tp_sell_fill(99.0, 0, bars) is None


def test_outage_windows_listed():
    m = _load_mod()
    assert len(m.OUTAGES) == 2
    assert m._ms("2026-10-06T10:32:00+00:00") <= m._ms("2026-10-06T11:00:00+00:00") < m._ms("2026-10-06T14:16:00+00:00")
    assert m.in_outage(m._ms("2026-10-06T11:00:00+00:00")) is not None
    assert m.in_outage(m._ms("2026-10-06T12:00:00+00:00")) is not None  # inside both
    assert m.in_outage(m._ms("2026-10-06T09:00:00+00:00")) is None
    assert m.in_outage(m._ms("2026-10-06T15:00:00+00:00")) is None


def test_reconstruct_replaced_link_episodes():
    m = _load_mod()
    acts = [
        {"op": "place", "t": "2026-10-05 20:05:00+00:00",
         "payload": {"symbol": "ETHUSDT", "side": "Buy", "qty": "0.02",
                     "orderLinkId": "b0E", "orderType": "Limit", "price": "2700.0",
                     "timeInForce": "GTC"}},
        {"op": "cancel", "t": "2026-10-06 00:00:06+00:00", "link": "b0E"},
        {"op": "place", "t": "2026-10-06 00:05:38+00:00",
         "payload": {"symbol": "ETHUSDT", "side": "Buy", "qty": "0.02",
                     "orderLinkId": "b0E", "orderType": "Limit", "price": "2700.0",
                     "timeInForce": "GTC"}},
        {"op": "fill", "t": "2026-10-06 02:36:19+00:00", "link": "b0E",
         "qty": "0.02", "price": "2700.0"},
    ]
    orders = m.reconstruct_orders(acts)
    assert len(orders) == 2  # two episodes, not one overwritten
    eps = sorted(orders.values(), key=lambda o: o["placed_t"])
    assert eps[0]["fill_t"] is None and eps[0]["cancel_t"] is not None
    assert eps[1]["fill_t"] is not None and eps[1]["cancel_t"] is None


def test_results_parity():
    r = json.loads(RES.read_text(encoding="utf-8"))
    assert r["verdict"] == "PARITY"
    assert r["mismatches"] == []
    assert len(r["outages_excluded"]) == 2
    assert r["book_entries"], "expected the 4 paper fills to be compared"
    assert sum(1 for b in r["book_entries"] if b["status"] == "match") == 4
    assert any(b["status"] == "both_unfilled" for b in r["book_entries"])
    assert all(b["paper_bar"] == b["expected_bar"] for b in r["book_entries"]
               if b["status"] == "match")
    assert r["dips"]["filled"] == 0 and r["dips"]["resting_now_mismatch"] == 0
    assert abs(r["pnl"]["fees_diff"]) <= r["tolerances"]["pnl_usdt"]
    assert abs(r["pnl"]["funding_diff"]) <= r["tolerances"]["pnl_usdt"]
    assert r["pnl"]["fills"] == 4
