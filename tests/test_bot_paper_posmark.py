"""Regression (2026-10-07, ops_carrygap): a symbol with an OPEN position but no resting order must still be marked.

The dated carry short (IOC entry filled at placement) left no resting order, so PaperExchange.step() never fetched its klines,
last_close stayed empty and equity_usdt() valued the short at 0 while the spot leg was marked -> paper equity understated.
"""
import tempfile
from pathlib import Path

import pandas as pd

from bot.paper import PaperExchange


class Pub:
    def __init__(self, rows_by_sym):
        self.rows_by_sym = rows_by_sym
        self.calls = []

    def instruments(self, syms):
        return {s: dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1") for s in syms}

    def public(self, path, **k):
        sym = k.get("symbol")
        self.calls.append(sym)
        return {"list": self.rows_by_sym.get(sym, [])}


def _ex(pub):
    d = Path(tempfile.mkdtemp())
    ex = PaperExchange(pub, d / "ex.json", 10000.0, ["BTCUSDT"])
    ex.cache_dir = d / "cache"
    return ex


def test_open_position_symbol_is_polled_and_marked():
    now = pd.Timestamp.now(tz="UTC").floor("min")
    t0 = int((now - pd.Timedelta(minutes=3)).timestamp() * 1000)
    # bars t0 .. now (4 minutes); the first step starts a newly polled symbol at the main symbols' cursor,
    # so the dated symbol is marked from the next closed minute on (one-minute delay, as in the live runner)
    rows = {s: [[str(t0 + i * 60_000), "100", "101", "99", str(98 + i), "1", "1"] for i in range(4)]
            for s in ("BTCUSDT", "BTCQ")}
    pub = Pub(rows)
    ex = _ex(pub)
    ex.s["last_ms"] = {"BTCUSDT": t0}
    ex.s["pos"]["BTCQ|2"] = dict(qty=0.01, avg=110.0)  # open dated short, no resting order
    ex.step(now=now)  # registers the cursor for BTCQ (nothing new to fetch yet)
    ex.step(now=now + pd.Timedelta(minutes=1))
    assert "BTCQ" in pub.calls
    assert ex.s["last_close"].get("BTCQ") == 101.0
    # the short (sold 110, now 101) adds +0.09 to equity instead of being ignored
    assert abs(ex.equity_usdt() - (ex.s["cash"] + (101.0 - 110.0) * 0.01 * -1)) < 1e-9


def test_flat_position_symbol_not_polled():
    now = pd.Timestamp.now(tz="UTC").floor("min")
    t0 = int((now - pd.Timedelta(minutes=3)).timestamp() * 1000)
    pub = Pub({"BTCUSDT": []})
    ex = _ex(pub)
    ex.s["last_ms"] = {"BTCUSDT": t0}
    ex.s["pos"]["ETHQ|2"] = dict(qty=0.0, avg=0.0)
    ex.step(now=now)
    assert "ETHQ" not in pub.calls
