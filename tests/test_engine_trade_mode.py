"""Synthetic checks of engine_user's discrete trade mode (user rules 2026-09-28)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "engine_user_tm", ROOT / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)

SIG = 0.01
SD = SIG * np.sqrt(6)
LIMIT = 100 * (1 - 0.25 * SIG)  # k_off 0.25 * sigma_4h = 0.25% below the 100.0 open
TRADE = dict(theta=0.05, k_off=0.25, min_off=0.001, n_valid=2, win_start=5)


def make(nbars=1, books_vals=(1.0,), opens_bar=None, lows=None, highs=None, mopens=None):
    idx = pd.date_range("2022-01-01", periods=nbars, freq="4h", tz="UTC")
    cols = ["BTCUSDT"]
    ob = list(opens_bar or [100.0] * nbars)
    O = np.zeros((nbars, 240, 1))
    for b in range(nbars):
        O[b, :, 0] = ob[b]
    H, L, C = O.copy(), O.copy(), O.copy()
    for (b, m), v in (lows or {}).items():
        L[b, m, 0] = v
    for (b, m), v in (highs or {}).items():
        H[b, m, 0] = v
    for (b, m), v in (mopens or {}).items():
        O[b, m, 0] = v
        C[b, m, 0] = v
    o1 = np.array(ob, float).reshape(-1, 1)
    o2 = np.array(ob[1:] + [ob[-1]], float).reshape(-1, 1)
    prep = dict(idx=idx, cols=cols, O=O, H=H, L=L, C=C, sig4=np.full((nbars, 1), SIG), o1=o1, o2=o2,
                settle=np.zeros(nbars, bool))
    books = pd.DataFrame(np.array(books_vals, float).reshape(-1, 1), index=idx, columns=cols)
    opens = pd.DataFrame(o1, index=idx, columns=cols)
    return books, opens, prep


def run(books, opens, prep, trade=TRADE):
    cap, events = {}, []
    orig = eu.summarize

    def grab(idx, net, eq, eq_min, g, stats, eq_max=None):
        cap.update(net=net.copy(), stats=dict(stats))
        return {}
    eu.summarize = grab
    try:
        eu.simulate(books, opens, prep, sleeve=False, m_sl=4.0, trade=trade, win_start=trade["win_start"], events=events)
    finally:
        eu.summarize = orig
    cap["events"] = events
    return cap


def test_no_fill_in_the_first_five_minutes():
    out = run(*make(lows={(0, 3): 99.0}))
    assert out["stats"]["fills"] == 0 and out["stats"]["issued"] == 1
    out = run(*make(lows={(0, 6): 99.0}))
    fill = [e for e in out["events"] if e["kind"] == "book_fill"]
    assert len(fill) == 1 and fill[0]["price"] == pytest.approx(LIMIT) and fill[0]["t"].minute == 6


def test_resting_order_keeps_its_price_on_the_next_bar():
    # bar 0 never touches the limit; bar 1 opens higher (101) and dips to 99.7 at minute 0 -> fill at the ORIGINAL limit
    out = run(*make(nbars=2, books_vals=(1.0, 1.0), opens_bar=(100.0, 101.0), lows={(1, 0): 99.7}))
    fill = [e for e in out["events"] if e["kind"] == "book_fill"]
    assert len(fill) == 1 and fill[0]["price"] == pytest.approx(LIMIT)
    assert out["stats"]["issued"] == 1  # the order was not re-issued at bar 1


def test_break_even_stop():
    trig = LIMIT * (1 + 2 * SD) + 0.01
    out = run(*make(lows={(0, 6): 99.0, (0, 30): 99.0}, highs={(0, 20): trig}), trade=dict(TRADE, be_k=2.0))
    s = out["stats"]
    assert s["be_moves"] == 1 and s["stops"] == 1
    stop = [e for e in out["events"] if e["kind"] == "book_stop"][0]
    assert stop["price"] == pytest.approx(LIMIT * 1.001)
    q = 0.8 / LIMIT  # target weight 0.8 (W_BOOKS * s * book * g with s = g = 1)
    exp = q * (LIMIT * 1.001 - LIMIT) - q * LIMIT * eu.MAKER - q * LIMIT * 1.001 * eu.TAKER
    assert out["net"][0] == pytest.approx(exp, rel=1e-9)


def test_partial_take_profit_then_break_even():
    tp1 = LIMIT * (1 + 4 * SD)
    out = run(*make(lows={(0, 6): 99.0, (0, 60): 99.0}, highs={(0, 30): tp1 + 0.01}),
              trade=dict(TRADE, partial_k=4.0, partial_frac=0.5))
    s = out["stats"]
    assert s["partials"] == 1 and s["stops"] == 1  # the rest is stopped at break-even at minute 60
    stop = [e for e in out["events"] if e["kind"] == "book_stop"][0]
    assert stop["price"] == pytest.approx(LIMIT * 1.001)


def test_position_is_never_resized():
    out = run(*make(nbars=3, books_vals=(1.0, 0.4, 1.0), lows={(0, 6): 99.0}))
    assert out["stats"]["fills"] == 1
    assert not [e for e in out["events"] if e["kind"] == "book_fill" and e["t"] > pd.Timestamp("2022-01-01 04:10", tz="UTC")]


def test_pending_order_cancelled_on_opposite_signal():
    out = run(*make(nbars=2, books_vals=(1.0, -1.0)))
    s = out["stats"]
    assert s["cancelled"] == 1 and s["issued"] == 2  # the long order is cancelled, a short order is issued
    iss = [e for e in out["events"] if e["kind"] == "order_issue"]
    assert iss[1]["side"] == "sell" and iss[1]["price"] == pytest.approx(100 * (1 + 0.25 * SIG))


def test_opposite_signal_tightens_the_stop():
    out = run(*make(nbars=2, books_vals=(1.0, -1.0), lows={(0, 6): 99.0}), trade=dict(TRADE, tighten=1.5))
    mv = [e for e in out["events"] if e["kind"] == "sl_move"]
    assert len(mv) == 1 and mv[0]["price"] == pytest.approx(100 * (1 - 1.5 * SD))
    assert out["stats"]["fills"] == 1  # no flip: the long is kept, only its stop moves


def test_risk_sizing_loses_the_risk_budget_at_the_stop():
    trade = dict(TRADE, risk=0.01, max_w=1.0)
    stop = LIMIT * (1 - 4 * SD)
    out = run(*make(lows={(0, 6): 99.0, (0, 40): stop - 0.5}, mopens={(0, 40): stop}), trade=trade)
    w = 0.01 / (4 * SD)
    fill = [e for e in out["events"] if e["kind"] == "book_fill"][0]
    assert fill["weight"] == pytest.approx(w)
    q = w / LIMIT
    exp = q * (stop - LIMIT) - q * LIMIT * eu.MAKER - q * stop * eu.TAKER
    assert out["net"][0] == pytest.approx(exp, rel=1e-9)
    assert out["net"][0] == pytest.approx(-0.01, abs=0.0005)  # about 1% of equity lost at the stop


def test_scale_in_limit_after_minute_five_when_in_profit_and_signal_grows():
    trade = dict(TRADE, add_k=1.5, max_adds=1)
    args = dict(nbars=3, books_vals=(1.0, 1.0, 3.0), opens_bar=(100.0, 101.0, 102.0))
    out = run(*make(lows={(0, 6): 99.0, (2, 2): 101.0}, **args), trade=trade)
    assert out["stats"]["adds"] == 0  # the add order may not fill before minute 5
    out = run(*make(lows={(0, 6): 99.0, (2, 10): 101.0}, **args), trade=trade)
    add = [e for e in out["events"] if e["kind"] == "book_add"]
    assert len(add) == 1 and add[0]["price"] == pytest.approx(102.0 * (1 - 0.25 * SIG)) and add[0]["t"].minute == 10
    assert LIMIT < add[0]["avg_entry"] < add[0]["price"]


def test_scale_out_limit_when_signal_weakens():
    trade = dict(TRADE, reduce_k=0.5, reduce_frac=0.5, max_reduces=1)
    out = run(*make(nbars=2, books_vals=(1.0, 0.2), lows={(0, 6): 99.0}, highs={(1, 10): 100.5}), trade=trade)
    red = [e for e in out["events"] if e["kind"] == "book_reduce"]
    assert len(red) == 1 and red[0]["price"] == pytest.approx(100 * (1 + 0.25 * SIG))
    fill = [e for e in out["events"] if e["kind"] == "book_fill"][0]
    assert red[0]["weight"] == pytest.approx(-0.5 * fill["weight"] * red[0]["price"] / LIMIT, rel=0.02)


def test_limit_exit_when_the_signal_is_gone():
    trade = dict(TRADE, exit_on_signal_loss=True)
    out = run(*make(nbars=2, books_vals=(1.0, 0.0), lows={(0, 6): 99.0}, highs={(1, 3): 100.5, (1, 12): 100.5}), trade=trade)
    close = [e for e in out["events"] if e["kind"] == "book_close"]
    assert len(close) == 1 and close[0]["t"].minute == 12  # not before minute 5 of the deciding bar
    assert close[0]["price"] == pytest.approx(100 * (1 + 0.25 * SIG)) and out["stats"]["limit_exits"] == 1
