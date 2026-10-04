"""Live liquidation recorder (backend/liquidations.py) and its causal research reader - no network."""

import asyncio
import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from backend import liquidations as L

# Real messages captured from the public streams on 2026-10-04 (Bybit v5 linear, Binance USD-M /market).
BYBIT_LIQ = ('{"topic":"allLiquidation.STRKUSDT","type":"snapshot","ts":1791091285551,'
             '"data":[{"T":1791091285156,"s":"STRKUSDT","S":"Buy","v":"2084.9","p":"0.05165"}]}')
BINANCE_LIQ = ('{"stream":"xrpusdt@forceOrder","data":{"e":"forceOrder","E":1791091175227,"o":{"s":"XRPUSDT","S":"BUY",'
               '"o":"LIMIT","f":"IOC","q":"127.2","p":"1.4984","ap":"1.4912","X":"FILLED","l":"108.1","z":"127.2",'
               '"T":1791091174219,"ps":"XRPUSDT","st":1}}}')
BINANCE_LIQ_RAW = ('{"e":"forceOrder","E":1791091027107,"o":{"s":"MANTAUSDT","S":"SELL","o":"LIMIT","f":"IOC","q":"2049.1",'
                   '"p":"0.0711500","ap":"0.0722187","X":"FILLED","l":"245.9","z":"2049.1","T":1791091026103,'
                   '"ps":"MANTAUSDT","st":1}}')
BINANCE_BOOK = ('{"e":"bookTicker","u":11730346419457,"s":"BTCUSDT","ps":"BTCUSDT","b":"84788.20","B":"5.923",'
                '"a":"84788.30","A":"2.824","T":1791091007473,"E":1791091007473,"st":1}')
BYBIT_TICK_DELTA = ('{"topic":"tickers.BTCUSDT","type":"delta","data":{"symbol":"BTCUSDT","bid1Price":"84792.60",'
                    '"bid1Size":"1.302"},"cs":820163808303,"ts":1791091006483}')
BYBIT_TICK_DELTA2 = ('{"topic":"tickers.BTCUSDT","type":"delta","data":{"symbol":"BTCUSDT","ask1Price":"84792.70",'
                     '"ask1Size":"17.487"},"cs":820163808364,"ts":1791091006584}')
BYBIT_PONG = '{"success":true,"ret_msg":"pong","conn_id":"x","req_id":"","op":"ping"}'


def _load_features():
    path = Path(__file__).resolve().parents[1] / "research/diagnostics/liquidations_live/features.py"
    spec = importlib.util.spec_from_file_location("liq_live_features", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


F = _load_features()


# ---------------------------------------------------------------- parsing
def test_parse_bybit_buy_is_long_liquidated():
    rows = L.parse_bybit_liquidation(BYBIT_LIQ, 1791091285600)
    assert rows == [{"venue": "bybit", "symbol": "STRKUSDT", "side": "long", "raw_side": "Buy", "price": 0.05165,
                     "qty": 2084.9, "notional_usd": pytest.approx(0.05165 * 2084.9), "event_time": 1791091285156,
                     "recv_time": 1791091285600}]
    sell = json.loads(BYBIT_LIQ)
    sell["data"][0]["S"] = "Sell"
    assert L.parse_bybit_liquidation(sell, 1)[0]["side"] == "short"
    assert L.parse_bybit_liquidation(BYBIT_PONG, 1) == []
    assert L.parse_bybit_liquidation("not json", 1) == []


def test_parse_binance_order_side_semantics():
    (r,) = L.parse_binance_liquidation(BINANCE_LIQ, 1791091175300)
    assert (r["venue"], r["symbol"], r["side"], r["raw_side"]) == ("binance", "XRPUSDT", "short", "BUY")
    assert r["price"] == 1.4912 and r["qty"] == 127.2  # average price, cumulative filled qty (not last fill 108.1)
    assert r["event_time"] == 1791091174219 and r["recv_time"] == 1791091175300
    (r2,) = L.parse_binance_liquidation(BINANCE_LIQ_RAW, 5)  # un-wrapped (raw /ws) payload
    assert r2["side"] == "long" and r2["symbol"] == "MANTAUSDT"
    assert L.parse_binance_liquidation(BINANCE_BOOK, 1) == []


def test_parse_top_of_book():
    q = L.parse_binance_book(BINANCE_BOOK)
    assert q == {"symbol": "BTCUSDT", "bid": 84788.2, "bid_qty": 5.923, "ask": 84788.3, "ask_qty": 2.824,
                 "quote_time": 1791091007473}
    state: dict = {}
    assert L.apply_bybit_ticker(BYBIT_TICK_DELTA, state) == "BTCUSDT"
    assert L.apply_bybit_ticker(BYBIT_TICK_DELTA2, state) == "BTCUSDT"
    assert state["BTCUSDT"]["bid"] == 84792.6 and state["BTCUSDT"]["ask"] == 84792.7
    assert state["BTCUSDT"]["quote_time"] == 1791091006584
    assert L.apply_bybit_ticker(BYBIT_PONG, state) is None


# ---------------------------------------------------------------- buffering / flush / dedupe
def _collector(tmp_path, **kw):
    return L.LiquidationCollector(tmp_path / "liq", tmp_path / "book", **kw)


def test_dedupe_flush_merge_and_atomic(tmp_path):
    c = _collector(tmp_path)
    rows = L.parse_bybit_liquidation(BYBIT_LIQ, 1791091285600) + L.parse_binance_liquidation(BINANCE_LIQ, 1791091175300)
    assert c.ingest_liquidations(rows) == 2
    assert c.ingest_liquidations(rows) == 0 and c.stats["duplicates"] == 2  # reconnect replay is dropped
    assert c.flush()["liquidations"] == 2
    f = tmp_path / "liq/bybit/STRKUSDT/2026-10-04.parquet"
    assert f.exists() and (tmp_path / "liq/binance/XRPUSDT/2026-10-04.parquet").exists()
    # a second collector (after a restart) re-sends the same event plus a new one: file merges, no duplicates
    c2 = _collector(tmp_path)
    later = json.loads(BYBIT_LIQ)
    later["data"][0]["T"] += 1000
    c2.ingest_liquidations(rows[:1] + L.parse_bybit_liquidation(later, 1791091286700))
    c2.flush()
    df = pd.read_parquet(f)
    assert list(df.columns) == L.LIQ_COLUMNS and len(df) == 2 and df["event_time"].is_monotonic_increasing
    assert not list(tmp_path.rglob("*.tmp"))  # temp files never left behind


def test_failed_write_keeps_rows_buffered(tmp_path, monkeypatch):
    c = _collector(tmp_path)
    c.ingest_liquidations(L.parse_bybit_liquidation(BYBIT_LIQ, 1791091285600))

    def boom(*a, **k):
        raise PermissionError("locked")
    monkeypatch.setattr(L, "_replace_with_retry", boom)
    assert c.flush()["liquidations"] == 0 and c.status()["buffered"] == 1 and c.stats["write_failures"] == 1
    monkeypatch.undo()
    assert c.flush()["liquidations"] == 1 and c.status()["buffered"] == 0


def test_corrupt_day_file_is_kept_aside(tmp_path):
    c = _collector(tmp_path)
    f = tmp_path / "liq/bybit/STRKUSDT/2026-10-04.parquet"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"garbage")
    c.ingest_liquidations(L.parse_bybit_liquidation(BYBIT_LIQ, 1791091285600))
    c.flush()
    assert len(pd.read_parquet(f)) == 1 and len(list(f.parent.glob("*.corrupt-*"))) == 1


def test_book_sampling_and_coverage(tmp_path):
    c = _collector(tmp_path)
    q = L.parse_binance_book(BINANCE_BOOK)
    q["recv_time"] = 1791091007500
    c._quotes["binance"]["BTCUSDT"] = q
    assert c.sample_book(1791091008000) == 1
    assert c.sample_book(1791091030000) == 0  # stale quote (> 10 s) is not sampled
    c._mark_connected("bybit", True)
    c._liq_since["bybit"] -= 5000  # connected 5 s ago
    out = c.flush()
    assert out["book"] == 1 and out["coverage"] == 1
    assert (tmp_path / "book/binance/BTCUSDT/2026-10-04.parquet").exists()
    cov = F.load_coverage(tmp_path / "liq")
    assert list(cov["venue"]) == ["bybit"] and (cov["end_ms"] >= cov["start_ms"]).all()


def test_collector_run_with_fake_sockets(tmp_path):
    """Full asyncio path: subscribe, ping, message handling, reconnect after a drop, final flush on stop."""
    sent, conns = [], []

    class FakeWS:
        def __init__(self, url, msgs, drop):
            self.url, self.msgs, self.drop = url, list(msgs), drop

        async def send(self, m):
            sent.append((self.url, m))

        async def recv(self):
            if self.msgs:
                return self.msgs.pop(0)
            if self.drop:
                raise ConnectionError("dropped")
            await asyncio.sleep(3600)

        async def close(self):
            pass

    async def connect(url):
        n = sum(1 for u in conns if u == url)
        conns.append(url)
        if "bybit" in url:
            return FakeWS(url, [BYBIT_LIQ.replace("STRKUSDT", "BTCUSDT"), BYBIT_TICK_DELTA, BYBIT_TICK_DELTA2], drop=n == 0)
        if "forceOrder" in url:
            return FakeWS(url, [BINANCE_LIQ], drop=False)
        return FakeWS(url, [BINANCE_BOOK], drop=False)

    c = _collector(tmp_path, flush_s=3600, connect=connect)

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(c.run(stop))
        await asyncio.sleep(2.5)  # bybit drops once -> reconnects after ~1 s backoff and re-sends the same event
        stop.set()
        await asyncio.wait_for(task, 10)

    asyncio.run(go())
    assert sum("bybit" in u for u in conns) >= 2
    assert any('"op": "subscribe"' in m and "allLiquidation.BTCUSDT" in m for _, m in sent)
    assert c.stats["events"]["bybit:BTCUSDT"] == 1 and c.stats["duplicates"] >= 1
    assert c.stats["events"]["binance:XRPUSDT"] == 1
    assert len(pd.read_parquet(tmp_path / "liq/bybit/BTCUSDT/2026-10-04.parquet")) == 1  # final flush on stop
    st = c.status()
    assert st["venues"]["bybit"]["reconnects"] >= 1 and st["buffered"] == 0


# ---------------------------------------------------------------- lifecycle switch
@pytest.fixture()
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("WEB_SCHEDULER_ENABLED", "false")
    monkeypatch.delenv("WEB_LIQUIDATIONS_ENABLED", raising=False)
    for m in [m for m in sys.modules if m == "backend" or m.startswith("backend.")]:
        del sys.modules[m]
    yield importlib.import_module("backend.config")
    for m in [m for m in sys.modules if m == "backend" or m.startswith("backend.")]:
        del sys.modules[m]


def test_disabled_when_scheduler_off_and_startup_does_not_start(backend, monkeypatch):
    assert backend.SETTINGS.liquidations_enabled is False
    server = importlib.import_module("backend.server")
    liq = importlib.import_module("backend.liquidations")
    started = []
    monkeypatch.setattr(liq, "CollectorThread", lambda *a, **k: started.append(1))
    server._startup()
    assert started == [] and liq.status() == {"running": False}
    assert server._liquidations_status() == {"running": False}
    server._shutdown()  # no-op, never raises


def test_explicit_override_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("WEB_LIQUIDATIONS_ENABLED", "true")
    cfg = importlib.reload(importlib.import_module("backend.config"))
    assert cfg.SETTINGS.liquidations_enabled is True
    monkeypatch.delenv("WEB_LIQUIDATIONS_ENABLED")
    sys.modules.pop("backend.config", None)  # later tests import a fresh config

    def broken(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(L, "LiquidationCollector", broken)
    assert L.start_background(True) is False  # start failure is swallowed (API keeps running)
    assert L.start_background(False) is False


def test_background_thread_start_stop(tmp_path, monkeypatch):
    async def never(url):
        raise ConnectionError("offline")
    monkeypatch.setattr(L, "LIQ_DIR", tmp_path / "liq")
    assert L.start_background(True, book=False, liq_root=tmp_path / "liq", book_root=tmp_path / "book", connect=never)
    try:
        assert L.status()["running"] is True
    finally:
        L.stop_background(10)
    assert L.status() == {"running": False}


# ---------------------------------------------------------------- research reader: buckets and strict as-of
def _events():
    t0 = 1791072000000  # 2026-10-04 00:00 UTC
    rows = [
        ("bybit", "BTCUSDT", "long", 1000.0, t0 + 10_000, t0 + 10_500),
        ("binance", "BTCUSDT", "long", 500.0, t0 + 20_000, t0 + 20_100),
        ("bybit", "BTCUSDT", "short", 200.0, t0 + 70_000, t0 + 70_100),
        ("bybit", "BTCUSDT", "short", 300.0, t0 + 119_000, t0 + 121_000),  # received after its minute closed
        ("bybit", "ETHUSDT", "long", 50.0, t0 + 30_000, t0 + 30_100),
    ]
    df = pd.DataFrame(rows, columns=["venue", "symbol", "side", "notional_usd", "event_time", "recv_time"])
    df["raw_side"], df["price"] = "x", 1.0
    df["qty"] = df["notional_usd"]
    return t0, df[F.EVENT_COLUMNS]


def test_minute_buckets_and_availability():
    t0, ev = _events()
    b = F.minute_buckets(ev)
    btc = b[b["symbol"] == "BTCUSDT"].set_index("minute_ms")
    assert btc.loc[t0, "long_liq_notional"] == 1500.0 and btc.loc[t0, "long_liq_count"] == 2
    assert btc.loc[t0, "available_ms"] == t0 + 60_000
    assert btc.loc[t0 + 60_000, "short_liq_notional"] == 500.0
    assert btc.loc[t0 + 60_000, "available_ms"] == t0 + 121_001  # late receipt delays availability
    assert len(F.minute_buckets(ev, by_venue=True)) == 4


def test_asof_is_strictly_causal():
    t0, ev = _events()
    b = F.minute_buckets(ev)
    f = F.asof_window(b, [t0 + 60_000, t0 + 120_000, t0 + 121_001], 60, ["BTCUSDT"]).set_index("time_ms")
    assert f.loc[t0 + 60_000, "long_liq_60m"] == 1500.0 and f.loc[t0 + 60_000, "short_liq_60m"] == 0.0
    assert f.loc[t0 + 120_000, "short_liq_60m"] == 0.0  # bucket ends at t but one event arrived later
    assert f.loc[t0 + 121_001, "short_liq_60m"] == 500.0
    # raw events: both event_time and recv_time strictly before t
    assert len(F.events_before(ev, t0 + 20_100)) == 1 and len(F.events_before(ev, t0 + 20_101)) == 2
    # the window is bounded below too
    g = F.asof_window(b, [t0 + 3 * 3_600_000], 60, ["BTCUSDT"])
    assert g["long_liq_60m"].iloc[0] == 0.0 and g["liq_imbalance_60m"].iloc[0] == 0.0


def test_features_4h_from_files(tmp_path):
    t0, ev = _events()
    c = _collector(tmp_path)
    c.ingest_liquidations(ev.to_dict("records"))
    with c._lock:
        c._cov_buf.append({"venue": "bybit", "start_ms": t0 - 4 * 3_600_000, "end_ms": t0 + 240_000})
        c._cov_buf.append({"venue": "binance", "start_ms": t0 - 600_000, "end_ms": t0 + 240_000})
    c.flush()
    f = F.features_4h([t0 + 240_000], root=tmp_path / "liq", symbols=["BTCUSDT"]).iloc[0]
    assert f["long_liq_240m"] == 1500.0 and f["short_liq_240m"] == 500.0
    # both venues connected only for the last 14 whole minutes before the close
    assert f["coverage_frac_60m"] == pytest.approx(14 / 60) and f["coverage_frac_240m"] == pytest.approx(14 / 240)
    g = F.features_4h([t0 + 240_000], root=tmp_path / "liq", symbols=["BTCUSDT"], venues=["bybit"]).iloc[0]
    assert g["coverage_frac_240m"] == 1.0 and g["long_liq_240m"] == 1000.0
