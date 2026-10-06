"""Fast pytest version of the bot_carrysoak quote-fed replay (< 60 s).

Uses tests/carry_soak.py in fast mode (coarse hold period, full slice-window
resolution). Never touches bot/ code, the network, or real orders.
"""
import pytest

from tests.carry_soak import DLV_MS, FUT, run


@pytest.fixture(scope="module")
def res():
    return run(fast=True)


def test_all_scripted_faults_triggered(res):
    assert res["faults"] == ["F1", "F2", "F3", "F4", "F5", "F6"]


def test_no_invariant_violations(res):
    assert res["violations"] == []


def test_both_pairs_settled_unhedged_within_bound(res):
    assert res["stats"]["settled"] == ["BTC", "ETH"]
    assert res["stats"]["hist_coins"] == ["BTC", "ETH"]
    assert res["stats"]["open_left"] == []
    assert res["stats"]["max_unhedged"] <= 2  # bot/carry.py:49


def test_missed_bucket_still_sold_in_full(res):
    by_coin = {h["coin"]: h for h in res["history"]}
    for coin in ("BTC", "ETH"):
        h = by_coin[coin]
        assert abs(float(h["spot_slice_sold_qty"]) - float(h["spot_qty_filled"])) < 1e-9


def test_slice_events_use_real_delivery_window(res):
    from bot import carry

    assert res["stats"]["slices"] == 12  # 6 decided buckets x 2 coins
    assert carry.SLICE_WINDOW_MS == 30 * 60 * 1000  # bot/carry.py:58


def test_fut_symbols_are_quarterly_majors_only(res):
    for h in res["history"]:
        assert h["coin"] in ("BTC", "ETH")
        assert h["symbol"] == FUT[h["coin"]]
        assert h["delivery_ms"] == DLV_MS
