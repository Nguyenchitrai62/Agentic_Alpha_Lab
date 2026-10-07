"""Regression (2026-10-07): a confirmed market exit must not be cancelled by the resting-order diff.

Paper fills a market order at the next 1m bar, so in the cycle that sends it the exit is still listed by have();
mirror.diff cancelled it because it is not a wanted resting order -> time exits / close5 stops never executed.
"""
from bot import mirror
from bot.run import _acts_without_exit_cancel


def _led():
    return {
        "d0BTC25x": dict(symbol="BTCUSDT", side=1, qty=0.003, kind="dip", exit_link="d0BTC25xXabc"),
        "d0ETH25x": dict(symbol="ETHUSDT", side=1, qty=0.0, kind="dip", exit_link="d0ETH25xXabc"),  # closed piece
        "d0SOL25x": dict(symbol="SOLUSDT", side=1, qty=2.0, kind="dip"),  # no exit in flight
    }


def test_diff_would_cancel_inflight_exit_but_filter_keeps_it():
    have = {"d0BTC25xXabc": dict(symbol="BTCUSDT", price=None, trigger=None, qty="0.003"),
            "d0SOL25xS": dict(symbol="SOLUSDT", price=None, trigger=110.0, qty="2.0")}
    acts = mirror.diff({}, have)
    assert {a["link"] for a in acts if a["op"] == "cancel"} == {"d0BTC25xXabc", "d0SOL25xS"}
    kept = _acts_without_exit_cancel(acts, _led())
    assert {a["link"] for a in kept if a["op"] == "cancel"} == {"d0SOL25xS"}


def test_closed_piece_exit_link_may_be_cancelled():
    acts = [dict(op="cancel", link="d0ETH25xXabc", symbol="ETHUSDT")]
    assert _acts_without_exit_cancel(acts, _led()) == acts


def test_non_cancel_acts_and_empty_ledger_untouched():
    acts = [dict(op="amend", link="d0BTC25xXabc", symbol="BTCUSDT", qty=0.003), dict(op="cancel", link="zzz", symbol="XRPUSDT")]
    assert _acts_without_exit_cancel(acts, _led()) == acts
    assert _acts_without_exit_cancel(acts, {}) == acts
    assert _acts_without_exit_cancel(acts, None) == acts
