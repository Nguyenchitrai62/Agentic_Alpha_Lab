"""Live collector of forced liquidations (and sampled top-of-book) for the five majors - public websockets only.

Nothing here has a free history, so the backend records it going forward for future research (no strategy uses it yet).
No authentication, no orders: only public market-data streams.

Venues and payload semantics (checked against live messages, 2026-10-04)
-----------------------------------------------------------------------
Bybit v5 public linear  wss://stream.bybit.com/v5/public/linear, topic ``allLiquidation.{SYMBOL}``
    {"topic": "allLiquidation.BTCUSDT", "type": "snapshot", "ts": ..., "data": [{"T": ms, "s": "BTCUSDT",
     "S": "Buy"|"Sell", "v": qty, "p": price}, ...]}
    Every liquidation, batched in pushes every 500 ms. ``S`` is the POSITION side per Bybit docs: "Buy" = a long position was
    liquidated, "Sell" = a short position was liquidated. ``p`` is the bankruptcy price, ``v`` the size (base coin).
    Heartbeat: the client sends {"op": "ping"} every 20 s (the server drops idle connections).
Binance USD-M  wss://fstream.binance.com/market/stream?streams=<sym>@forceOrder/...
    {"stream": "btcusdt@forceOrder", "data": {"e": "forceOrder", "E": ms, "o": {"s", "S": "BUY"|"SELL", "o": "LIMIT",
     "f": "IOC", "q", "p", "ap", "X", "l", "z", "T": ms, ...}}}
    ``S`` is the side of the liquidation ORDER: "SELL" = a long position was liquidated, "BUY" = a short was liquidated.
    At most ONE event per symbol per second is pushed (the latest liquidation in that second; a snapshot, not every
    liquidation). ``ap`` = average fill price (``p`` = order limit price), ``z`` = filled quantity. Binance moved
    market streams to routed URLs: the legacy ``/ws`` path no longer delivers forceOrder/aggTrade (only bookTicker), so
    forceOrder uses ``/market/...`` and bookTicker uses ``/public/...``. The server pings every few minutes; the
    websockets library answers automatically; connections are recycled before Binance's 24 h limit.

Normalised liquidation columns: venue, symbol, side ("long" = liquidated long position, i.e. forced SELL;
"short" = liquidated short, forced BUY), raw_side (venue string), price, qty, notional_usd (price * qty; USDT-margined
contracts, USDT ~ USD), event_time (exchange timestamp, UTC ms), recv_time (local UTC ms). recv_time uses the local
clock: on this host it ran ~0.25 s behind Binance at the 2026-10-04 smoke (recv_time < event_time); status() reports the
median recv - event lag per venue so drift is visible.

Top-of-book (cheap): the latest best bid/ask per venue/symbol is SAMPLED once per ``book_sample_s`` (default 1 s),
from Binance ``<sym>@bookTicker`` (/public) and Bybit ``tickers.{SYMBOL}`` (bid1/ask1, 100 ms pushes).

Storage (never committed; data/raw/ is gitignored):
    data/raw/liquidations_live/{venue}/{SYMBOL}/YYYY-MM-DD.parquet   (partitioned by event_time UTC date)
    data/raw/topbook_live/{venue}/{SYMBOL}/YYYY-MM-DD.parquet        (partitioned by sample_time UTC date)
    data/raw/liquidations_live/_coverage/{venue}/YYYY-MM-DD.parquet  (connected intervals of the liquidation stream,
                                                                      so "no liquidation" differs from "no data")
Every ``flush_s`` (default 60 s) buffered rows are merged into the day file: read existing -> concat -> dedupe -> sort ->
write a temp file in the same directory -> os.replace (atomic). A crash loses at most the unflushed buffer; a failed
write keeps the rows buffered for the next flush. Dedupe key for liquidations: (venue, symbol, event_time, raw_side,
price, qty) - venues give no trade id, so two identical liquidations in the same millisecond would collapse (rare).

Standalone smoke run:  .venv/Scripts/python.exe -m backend.liquidations --minutes 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import threading
import time
from collections import OrderedDict, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

log = logging.getLogger("alphalab.liquidations")

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
VENUES: tuple[str, ...] = ("bybit", "binance")
LIQ_DIR = ROOT / "data/raw/liquidations_live"
BOOK_DIR = ROOT / "data/raw/topbook_live"

BYBIT_URL = "wss://stream.bybit.com/v5/public/linear"
BINANCE_MARKET_URL = "wss://fstream.binance.com/market/stream?streams="
BINANCE_PUBLIC_URL = "wss://fstream.binance.com/public/stream?streams="

LIQ_COLUMNS = ["venue", "symbol", "side", "raw_side", "price", "qty", "notional_usd", "event_time", "recv_time"]
LIQ_KEY = ["venue", "symbol", "event_time", "raw_side", "price", "qty"]
BOOK_COLUMNS = ["venue", "symbol", "sample_time", "quote_time", "bid", "bid_qty", "ask", "ask_qty", "recv_time"]
BOOK_KEY = ["venue", "symbol", "sample_time"]
COV_COLUMNS = ["venue", "start_ms", "end_ms"]
COV_KEY = ["venue", "start_ms"]

DAY_MS = 86_400_000
BINANCE_MAX_CONN_S = 23 * 3600 + 50 * 60  # Binance drops connections at 24 h; recycle a bit earlier


def now_ms() -> int:
    return int(time.time() * 1000)


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _loads(msg: str | bytes | dict) -> dict | None:
    if isinstance(msg, dict):
        return msg
    try:
        out = json.loads(msg)
    except (TypeError, ValueError):
        return None
    return out if isinstance(out, dict) else None


# ------------------------------------------------------------------ payload parsing (pure functions, unit tested)
def parse_bybit_liquidation(msg: str | bytes | dict, recv_time: int) -> list[dict]:
    """Bybit ``allLiquidation.{SYMBOL}`` -> normalised rows. S is the position side: Buy = long liquidated."""
    d = _loads(msg)
    if not d or not str(d.get("topic", "")).startswith("allLiquidation."):
        return []
    data = d.get("data") or []
    if isinstance(data, dict):
        data = [data]
    rows = []
    for x in data:
        raw = str(x.get("S", ""))
        side = {"Buy": "long", "Sell": "short"}.get(raw)
        price, qty = _f(x.get("p")), _f(x.get("v"))
        t = x.get("T") or d.get("ts")
        sym = str(x.get("s") or d["topic"].split(".", 1)[1]).upper()
        if side is None or not price > 0 or not qty > 0 or t is None:
            continue
        rows.append({"venue": "bybit", "symbol": sym, "side": side, "raw_side": raw, "price": price, "qty": qty,
                     "notional_usd": price * qty, "event_time": int(t), "recv_time": int(recv_time)})
    return rows


def parse_binance_liquidation(msg: str | bytes | dict, recv_time: int) -> list[dict]:
    """Binance ``<sym>@forceOrder`` (raw or combined-stream wrapper) -> rows. S is the ORDER side: SELL = long liquidated."""
    d = _loads(msg)
    if not d:
        return []
    if "data" in d and isinstance(d["data"], dict):
        d = d["data"]
    if d.get("e") != "forceOrder" or not isinstance(d.get("o"), dict):
        return []
    o = d["o"]
    raw = str(o.get("S", ""))
    side = {"SELL": "long", "BUY": "short"}.get(raw)
    ap, p = _f(o.get("ap")), _f(o.get("p"))
    price = ap if ap > 0 else p
    qty = _f(o.get("z"))
    if not qty > 0:
        qty = _f(o.get("q"))
    t = o.get("T") or d.get("E")
    if side is None or not price > 0 or not qty > 0 or t is None:
        return []
    return [{"venue": "binance", "symbol": str(o.get("s", "")).upper(), "side": side, "raw_side": raw, "price": price,
             "qty": qty, "notional_usd": price * qty, "event_time": int(t), "recv_time": int(recv_time)}]


def parse_binance_book(msg: str | bytes | dict) -> dict | None:
    """Binance ``<sym>@bookTicker`` -> quote dict (symbol, bid, bid_qty, ask, ask_qty, quote_time)."""
    d = _loads(msg)
    if not d:
        return None
    if "data" in d and isinstance(d["data"], dict):
        d = d["data"]
    if d.get("e") != "bookTicker":
        return None
    return {"symbol": str(d.get("s", "")).upper(), "bid": _f(d.get("b")), "bid_qty": _f(d.get("B")),
            "ask": _f(d.get("a")), "ask_qty": _f(d.get("A")), "quote_time": int(d.get("T") or d.get("E") or 0)}


def apply_bybit_ticker(msg: str | bytes | dict, state: dict[str, dict]) -> str | None:
    """Merge a Bybit ``tickers.{SYMBOL}`` snapshot/delta into ``state[symbol]``; returns the symbol updated (or None).

    Deltas carry only changed fields, so the latest bid1/ask1 is kept per symbol."""
    d = _loads(msg)
    if not d or not str(d.get("topic", "")).startswith("tickers."):
        return None
    x = d.get("data") or {}
    sym = str(x.get("symbol") or d["topic"].split(".", 1)[1]).upper()
    q = state.setdefault(sym, {"symbol": sym, "bid": float("nan"), "bid_qty": float("nan"), "ask": float("nan"),
                               "ask_qty": float("nan"), "quote_time": 0})
    if d.get("type") == "snapshot":
        q.update(bid=float("nan"), bid_qty=float("nan"), ask=float("nan"), ask_qty=float("nan"))
    changed = False
    for src, dst in (("bid1Price", "bid"), ("bid1Size", "bid_qty"), ("ask1Price", "ask"), ("ask1Size", "ask_qty")):
        if src in x:
            q[dst] = _f(x[src])
            changed = True
    if changed:
        q["quote_time"] = int(d.get("ts") or 0)
        return sym
    return None


# ------------------------------------------------------------------ atomic parquet day files
class ParquetSink:
    """Buffered rows -> {root}/{venue}/{SYMBOL}/YYYY-MM-DD.parquet with read-merge-write + os.replace.

    ``symbol_dir=False`` drops the symbol level (coverage files)."""

    def __init__(self, root: Path, columns: list[str], key: list[str], time_col: str, symbol_dir: bool = True):
        self.root = Path(root)
        self.columns, self.key, self.time_col, self.symbol_dir = columns, key, time_col, symbol_dir
        self.files_written: set[str] = set()

    def path_for(self, venue: str, symbol: str | None, day: str) -> Path:
        base = self.root / venue / symbol if self.symbol_dir and symbol else self.root / venue
        return base / f"{day}.parquet"

    def write(self, rows: list[dict]) -> list[dict]:
        """Merge ``rows`` into their day files. Returns the rows that could NOT be written (to be retried)."""
        if not rows:
            return []
        import pandas as pd  # local import: keeps backend import cheap

        groups: dict[Path, list[dict]] = defaultdict(list)
        for r in rows:
            groups[self.path_for(r["venue"], r.get("symbol"), _day(int(r[self.time_col])))].append(r)
        failed: list[dict] = []
        for path, part in groups.items():
            try:
                new = pd.DataFrame(part, columns=self.columns)
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    try:
                        old = pd.read_parquet(path)
                    except Exception:  # unreadable (should not happen with atomic writes): keep it aside, never delete
                        bad = path.with_suffix(f".corrupt-{now_ms()}.parquet")
                        os.replace(path, bad)
                        log.error("liquidations: unreadable %s moved to %s", path, bad.name)
                        old = None
                    if old is not None and len(old):
                        new = pd.concat([old[self.columns], new], ignore_index=True)
                new = new.drop_duplicates(subset=self.key, keep="first").sort_values(
                    [self.time_col] + [k for k in self.key if k != self.time_col], kind="mergesort").reset_index(drop=True)
                tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                new.to_parquet(tmp, index=False)
                _replace_with_retry(tmp, path)
                self.files_written.add(str(path))
            except Exception as exc:
                log.warning("liquidations: write %s failed (%r) - %d rows kept for the next flush", path, exc, len(part))
                failed.extend(part)
        return failed


def _replace_with_retry(tmp: Path, path: Path, tries: int = 5) -> None:
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: a reader may hold the target open for a moment
            if i == tries - 1:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                raise
            time.sleep(0.2 * (i + 1))


# ------------------------------------------------------------------ collector
class LiquidationCollector:
    """Asyncio collector: one Bybit connection (allLiquidation + tickers), one Binance /market connection (forceOrder)
    and one Binance /public connection (bookTicker); each reconnects with exponential backoff."""

    def __init__(self, liq_root: Path = LIQ_DIR, book_root: Path = BOOK_DIR, symbols: Iterable[str] = SYMBOLS,
                 venues: Iterable[str] = VENUES, book: bool = True, flush_s: float = 60.0, book_sample_s: float = 1.0,
                 connect: Callable | None = None):
        self.symbols = tuple(s.upper() for s in symbols)
        self.venues = tuple(venues)
        self.book, self.flush_s, self.book_sample_s = book, float(flush_s), float(book_sample_s)
        self.liq_sink = ParquetSink(Path(liq_root), LIQ_COLUMNS, LIQ_KEY, "event_time")
        self.book_sink = ParquetSink(Path(book_root), BOOK_COLUMNS, BOOK_KEY, "sample_time")
        self.cov_sink = ParquetSink(Path(liq_root) / "_coverage", COV_COLUMNS, COV_KEY, "start_ms", symbol_dir=False)
        self._connect = connect
        self._lock = threading.Lock()
        self._liq_buf: list[dict] = []
        self._book_buf: list[dict] = []
        self._cov_buf: list[dict] = []
        self._seen: OrderedDict[tuple, None] = OrderedDict()
        self._quotes: dict[str, dict[str, dict]] = {v: {} for v in VENUES}
        self._recv: dict[str, deque] = {v: deque() for v in VENUES}
        self._lag: dict[str, deque] = {v: deque(maxlen=200) for v in VENUES}  # recv_time - event_time (clock check)
        self._liq_since: dict[str, int | None] = {v: None for v in VENUES}  # liquidation stream connected since (ms)
        self.stats: dict[str, Any] = {
            "started_ms": None, "last_flush_ms": None, "flushes": 0, "write_failures": 0,
            "events": defaultdict(int), "duplicates": 0, "book_samples": defaultdict(int),
            "last_event_time": {}, "connected": {}, "reconnects": defaultdict(int), "last_error": {},
        }
        self._stop: asyncio.Event | None = None

    # ---- ingestion (called on the collector loop)
    def ingest_liquidations(self, rows: list[dict]) -> int:
        added = 0
        with self._lock:
            for r in rows:
                k = tuple(r[c] for c in LIQ_KEY)
                if k in self._seen:
                    self.stats["duplicates"] += 1
                    continue
                self._seen[k] = None
                if len(self._seen) > 100_000:
                    self._seen.popitem(last=False)
                self._liq_buf.append(r)
                v = r["venue"]
                self.stats["events"][f"{v}:{r['symbol']}"] += 1
                self._recv.setdefault(v, deque()).append(r["recv_time"])
                self._lag.setdefault(v, deque(maxlen=200)).append(r["recv_time"] - r["event_time"])
                self.stats["last_event_time"][v] = max(r["event_time"], self.stats["last_event_time"].get(v, 0))
                added += 1
        return added

    def sample_book(self, t: int | None = None) -> int:
        """Append the latest quote of every venue/symbol (if fresh, <= 10 s old on receipt) to the book buffer."""
        t = now_ms() if t is None else t
        n = 0
        with self._lock:
            for venue, qs in self._quotes.items():
                for sym, q in qs.items():
                    if sym not in self.symbols or not (q.get("bid", 0) > 0 and q.get("ask", 0) > 0):
                        continue
                    if t - q.get("recv_time", 0) > 10_000:
                        continue
                    self._book_buf.append({"venue": venue, "symbol": sym, "sample_time": t,
                                           "quote_time": int(q.get("quote_time", 0)), "bid": q["bid"],
                                           "bid_qty": q["bid_qty"], "ask": q["ask"], "ask_qty": q["ask_qty"],
                                           "recv_time": int(q["recv_time"])})
                    self.stats["book_samples"][f"{venue}:{sym}"] += 1
                    n += 1
        return n

    def _mark_connected(self, venue: str, up: bool) -> None:
        t = now_ms()
        with self._lock:
            since = self._liq_since.get(venue)
            if up and since is None:
                self._liq_since[venue] = t
            elif not up and since is not None:
                if t > since:
                    self._cov_buf.append({"venue": venue, "start_ms": since, "end_ms": t})
                self._liq_since[venue] = None
            self.stats["connected"][venue] = up

    def _cut_coverage(self, t: int) -> None:
        """Close the open coverage interval at ``t`` (and reopen it) so flushed files describe connection up to now."""
        with self._lock:
            for venue, since in self._liq_since.items():
                if since is not None and t > since:
                    self._cov_buf.append({"venue": venue, "start_ms": since, "end_ms": t})
                    self._liq_since[venue] = t

    def flush(self) -> dict:
        """Write all buffers (sync; run in a worker thread from the loop). Failed rows go back into the buffers."""
        t = now_ms()
        self._cut_coverage(t)
        with self._lock:
            liq, self._liq_buf = self._liq_buf, []
            book, self._book_buf = self._book_buf, []
            cov, self._cov_buf = self._cov_buf, []
        # a coverage interval may cross midnight: split it so each day file holds its own part
        cov_split = []
        for c in cov:
            s = c["start_ms"]
            while s < c["end_ms"]:
                e = min(c["end_ms"], (s // DAY_MS + 1) * DAY_MS)
                cov_split.append({"venue": c["venue"], "start_ms": s, "end_ms": e})
                s = e
        f_liq = self.liq_sink.write(liq)
        f_book = self.book_sink.write(book) if book else []
        f_cov = self.cov_sink.write(cov_split)
        with self._lock:
            self._liq_buf[:0] = f_liq
            self._book_buf[:0] = f_book
            self._cov_buf[:0] = f_cov
            self.stats["last_flush_ms"] = t
            self.stats["flushes"] += 1
            if f_liq or f_book or f_cov:
                self.stats["write_failures"] += 1
        return {"liquidations": len(liq) - len(f_liq), "book": len(book) - len(f_book), "coverage": len(cov_split) - len(f_cov)}

    def status(self) -> dict:
        t = now_ms()
        with self._lock:
            per_venue = {}
            for v in self.venues:
                dq = self._recv.setdefault(v, deque())
                while dq and dq[0] < t - 3_600_000:
                    dq.popleft()
                let = self.stats["last_event_time"].get(v)
                per_venue[v] = {"events_last_hour": len(dq), "connected": bool(self.stats["connected"].get(v)),
                                "last_event_utc": datetime.fromtimestamp(let / 1000, tz=timezone.utc).isoformat() if let else None,
                                "reconnects": self.stats["reconnects"].get(v, 0), "last_error": self.stats["last_error"].get(v),
                                # negative = the local clock runs behind the exchange (keep Windows time synced)
                                "median_recv_minus_event_ms": sorted(self._lag[v])[len(self._lag[v]) // 2] if self._lag.get(v) else None}
            return {"venues": per_venue, "buffered": len(self._liq_buf), "book_buffered": len(self._book_buf),
                    "flushes": self.stats["flushes"], "write_failures": self.stats["write_failures"],
                    "last_flush_utc": datetime.fromtimestamp(self.stats["last_flush_ms"] / 1000, tz=timezone.utc).isoformat()
                    if self.stats["last_flush_ms"] else None}

    # ---- network
    async def _ws_connect(self, url: str):
        if self._connect is not None:
            return await self._connect(url)
        from websockets.asyncio.client import connect
        return await connect(url, ping_interval=20, ping_timeout=20, close_timeout=2, open_timeout=15,
                             max_size=2 ** 20, user_agent_header=None)

    async def _run_conn(self, name: str, url: str, on_message: Callable[[str, int], None], subscribe: dict | None = None,
                        app_ping: dict | None = None, stale_s: float | None = None, max_conn_s: float | None = None,
                        liq_venue: str | None = None) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            ws = None
            opened = time.monotonic()
            try:
                ws = await self._ws_connect(url)
                if subscribe:
                    await ws.send(json.dumps(subscribe))
                log.info("liquidations: %s connected", name)
                if liq_venue:
                    self._mark_connected(liq_venue, True)
                last_rx = last_ping = time.monotonic()
                while not self._stop.is_set():
                    mono = time.monotonic()
                    if app_ping and mono - last_ping >= 20:
                        await ws.send(json.dumps(app_ping))
                        last_ping = mono
                    if stale_s and mono - last_rx > stale_s:
                        raise TimeoutError(f"no message for {stale_s:.0f} s")
                    if max_conn_s and mono - opened > max_conn_s:
                        log.info("liquidations: %s recycling connection (age limit)", name)
                        break
                    if mono - opened > 60:
                        backoff = 1.0  # stable connection: reset the backoff
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue
                    last_rx = time.monotonic()
                    try:
                        on_message(msg, now_ms())
                    except Exception:
                        log.exception("liquidations: %s message handler error", name)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.stats["last_error"][name.split("-")[0]] = f"{type(exc).__name__}: {exc}"[:200]
                log.warning("liquidations: %s disconnected (%r); reconnect in %.0f s", name, exc, backoff)
            finally:
                if liq_venue:
                    self._mark_connected(liq_venue, False)
                if ws is not None:
                    try:
                        await asyncio.wait_for(ws.close(), timeout=2)
                    except Exception:
                        pass
            if self._stop.is_set():
                break
            self.stats["reconnects"][name.split("-")[0]] += 1
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff * (0.8 + 0.4 * random.random()))
            except asyncio.TimeoutError:
                pass
            backoff = min(60.0, backoff * 2)

    def _on_bybit(self, msg: str, recv: int) -> None:
        d = _loads(msg)
        if not d:
            return
        topic = str(d.get("topic", ""))
        if topic.startswith("allLiquidation."):
            self.ingest_liquidations(parse_bybit_liquidation(d, recv))
        elif topic.startswith("tickers."):
            with self._lock:
                sym = apply_bybit_ticker(d, self._quotes["bybit"])
                if sym:
                    self._quotes["bybit"][sym]["recv_time"] = recv
        elif d.get("op") == "subscribe" and d.get("success") is False:
            log.error("liquidations: bybit subscribe rejected: %s", d.get("ret_msg"))
            self.stats["last_error"]["bybit"] = f"subscribe: {d.get('ret_msg')}"[:200]

    def _on_binance_liq(self, msg: str, recv: int) -> None:
        self.ingest_liquidations(parse_binance_liquidation(msg, recv))

    def _on_binance_book(self, msg: str, recv: int) -> None:
        q = parse_binance_book(msg)
        if q:
            q["recv_time"] = recv
            with self._lock:
                self._quotes["binance"][q["symbol"]] = q

    async def _flusher(self) -> None:
        next_sample = time.monotonic()
        next_flush = time.monotonic() + self.flush_s
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(0.05, min(next_sample, next_flush) - time.monotonic()))
            except asyncio.TimeoutError:
                pass
            mono = time.monotonic()
            if self.book and mono >= next_sample:
                self.sample_book()
                next_sample += self.book_sample_s
                if next_sample < mono:
                    next_sample = mono + self.book_sample_s
            if mono >= next_flush:
                next_flush = mono + self.flush_s
                try:
                    await asyncio.to_thread(self.flush)
                except Exception:
                    log.exception("liquidations: flush error")

    async def run(self, stop: asyncio.Event | None = None) -> None:
        self._stop = stop or asyncio.Event()
        self.stats["started_ms"] = now_ms()
        tasks = [asyncio.create_task(self._flusher(), name="liq-flusher")]
        if "bybit" in self.venues:
            topics = [f"allLiquidation.{s}" for s in self.symbols] + ([f"tickers.{s}" for s in self.symbols] if self.book else [])
            tasks.append(asyncio.create_task(self._run_conn(
                "bybit", BYBIT_URL, self._on_bybit, subscribe={"op": "subscribe", "args": topics},
                app_ping={"op": "ping"}, stale_s=90, liq_venue="bybit")))
        if "binance" in self.venues:
            streams = "/".join(f"{s.lower()}@forceOrder" for s in self.symbols)
            tasks.append(asyncio.create_task(self._run_conn(
                "binance-liq", BINANCE_MARKET_URL + streams, self._on_binance_liq, max_conn_s=BINANCE_MAX_CONN_S,
                liq_venue="binance")))
            if self.book:
                streams = "/".join(f"{s.lower()}@bookTicker" for s in self.symbols)
                tasks.append(asyncio.create_task(self._run_conn(
                    "binance-book", BINANCE_PUBLIC_URL + streams, self._on_binance_book, stale_s=60,
                    max_conn_s=BINANCE_MAX_CONN_S)))
        try:
            await self._stop.wait()
        finally:
            self._stop.set()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for v in self.venues:
                self._mark_connected(v, False)
            await asyncio.to_thread(self.flush)  # final flush: nothing buffered is lost on a clean stop


# ------------------------------------------------------------------ background thread for the FastAPI app
class CollectorThread:
    """Runs a collector on its own event loop in a daemon thread (the API loop and parquet writes never block it)."""

    def __init__(self, collector: LiquidationCollector):
        self.collector = collector
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> "CollectorThread":
        self._thread = threading.Thread(target=self._main, name="liquidation-collector", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return self

    def _main(self) -> None:
        try:
            asyncio.run(self._amain())
        except Exception:
            log.exception("liquidations: collector thread crashed (API unaffected)")

    async def _amain(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._ready.set()
        await self.collector.run(self._stop)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def stop(self, timeout: float = 20.0) -> None:
        if self._loop is not None and self._stop is not None and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._stop.set)
            except RuntimeError:
                pass
        if self._thread is not None:
            self._thread.join(timeout)


_runner: CollectorThread | None = None


def start_background(enabled: bool, book: bool = True, **kw) -> bool:
    """Start the collector once (no-op when disabled or already running). Never raises."""
    global _runner
    if not enabled:
        log.info("liquidations: collector OFF")
        return False
    try:
        if _runner is not None and _runner.alive:
            return True
        _runner = CollectorThread(LiquidationCollector(book=book, **kw)).start()
        log.info("liquidations: collector ON (%s; top-of-book %s) -> %s", ", ".join(VENUES), "ON" if book else "OFF", LIQ_DIR)
        return True
    except Exception:
        log.exception("liquidations: collector failed to start (API unaffected)")
        return False


def stop_background(timeout: float = 20.0) -> None:
    global _runner
    r, _runner = _runner, None
    if r is None:
        return
    try:
        r.stop(timeout)
        log.info("liquidations: collector stopped")
    except Exception:
        log.exception("liquidations: collector stop error")


def status() -> dict:
    r = _runner
    if r is None:
        return {"running": False}
    try:
        return {"running": r.alive, **r.collector.status()}
    except Exception as exc:
        return {"running": r.alive, "error": repr(exc)[:200]}


# ------------------------------------------------------------------ CLI smoke run
def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect public liquidation (+ top-of-book) streams for the majors.")
    ap.add_argument("--minutes", type=float, default=3.0, help="run time (0 = until Ctrl+C)")
    ap.add_argument("--flush-s", type=float, default=60.0)
    ap.add_argument("--no-book", action="store_true", help="liquidations only")
    ap.add_argument("--liq-root", type=Path, default=LIQ_DIR)
    ap.add_argument("--book-root", type=Path, default=BOOK_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-5s %(message)s")
    col = LiquidationCollector(args.liq_root, args.book_root, book=not args.no_book, flush_s=args.flush_s)

    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(col.run(stop))
        try:
            if args.minutes > 0:
                await asyncio.sleep(args.minutes * 60)
            else:
                await asyncio.Event().wait()
        finally:
            stop.set()
            await task

    try:
        asyncio.run(go())
    except KeyboardInterrupt:
        pass
    print(json.dumps({"events": dict(sorted(col.stats["events"].items())), "duplicates": col.stats["duplicates"],
                      "status": col.status(),
                      "book_samples": dict(sorted(col.stats["book_samples"].items())),
                      "reconnects": dict(col.stats["reconnects"]), "last_error": col.stats["last_error"],
                      "files_written": sorted(col.liq_sink.files_written | col.book_sink.files_written | col.cov_sink.files_written)},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
