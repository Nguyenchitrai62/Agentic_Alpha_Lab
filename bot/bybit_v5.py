"""Minimal Bybit V5 REST client (USDT linear perpetuals): public market data + signed account / order calls.

Testnet by default. Signing (V5, HMAC-SHA256): sign(timestamp + api_key + recv_window + payload), payload = the query string for GET and the
JSON body for POST. Keys are read from the environment / .env by the caller and never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from contextlib import contextmanager
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from urllib.parse import urlencode

import requests

TESTNET = "https://api-testnet.bybit.com"
MAINNET = "https://api.bybit.com"
RECV_WINDOW = "10000"

# Shared on-disk public-kline cache: N runners on one machine share one fetch per
# symbol per TTL (bot_opsfix). Single values (1m close, 4h opens) and the 1m
# bar map for paper fills live in artifacts/bot/_kline_cache/<SYMBOL>.json as
# {field: {"t": fetch_epoch_s, "v": value}}. All helpers are exception-safe
# (miss on any error) and accept cache_dir/now for tests.
KLINE_CACHE_TTL = 20.0
KLINE_CACHE_MAX_BARS = 1500


def kline_cache_dir(cache_dir=None) -> Path:
    if cache_dir is not None:
        return Path(cache_dir)
    return Path(__file__).resolve().parents[1] / "artifacts" / "bot" / "_kline_cache"


def kline_cache_path(symbol: str, cache_dir=None) -> Path:
    safe = "".join(c for c in str(symbol).upper() if c.isalnum() or c in ("-", "_")) or "UNKNOWN"
    return kline_cache_dir(cache_dir) / f"{safe}.json"


@contextmanager
def _kline_locked(lock_path: Path):
    """Exclusive OS lock on a sidecar file (shared across runners); never raises."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            try:
                import msvcrt
                f.seek(0)
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    pass  # contention: proceed; atomic rename still protects readers
            except ImportError:
                pass
        else:
            try:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass
        yield
    finally:
        try:
            if os.name == "nt":
                try:
                    import msvcrt
                    f.seek(0)
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                except ImportError:
                    pass
            else:
                try:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass
        finally:
            try:
                f.close()
            except OSError:
                pass


def _cache_now(now=None) -> float:
    return float(now) if now is not None else time.time()


def kline_cache_get(symbol: str, field: str, cache_dir=None, ttl: float = KLINE_CACHE_TTL, now=None):
    """Cached field value, or None on miss/expiry/corruption. Never raises."""
    try:
        t = _cache_now(now)
        path = kline_cache_path(symbol, cache_dir)
        if not path.exists():
            return None
        with _kline_locked(path.with_suffix(".lock")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        try:
            ent = doc.get(field)
            if not isinstance(ent, dict) or ent.get("v") is None:
                return None
            if t - float(ent.get("t", 0.0)) >= float(ttl):
                return None
            return ent["v"]
        except (TypeError, ValueError, AttributeError):
            return None
    except Exception:
        return None


def kline_cache_put(symbol: str, field: str, value, cache_dir=None, now=None) -> None:
    """Store a field value (atomic rename). Never raises; ignores None values."""
    if value is None:
        return
    try:
        t = _cache_now(now)
        path = kline_cache_path(symbol, cache_dir)
        with _kline_locked(path.with_suffix(".lock")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except (OSError, ValueError):
                doc = {}
            if not isinstance(doc, dict):
                doc = {}
            doc[field] = {"t": t, "v": value}
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, path)
    except Exception:
        pass


def cached_call(symbol: str, field: str, fetch, cache_dir=None, ttl: float = KLINE_CACHE_TTL, now=None):
    """Shared-cache wrapper for one fetch: (value, from_cache). Miss -> fetch(),
    store, return. fetch() exceptions propagate (nothing cached)."""
    t = _cache_now(now)
    hit = kline_cache_get(symbol, field, cache_dir, ttl, now=t)
    if hit is not None:
        return hit, True
    val = fetch()
    if val is not None:
        kline_cache_put(symbol, field, val, cache_dir, now=t)
    return val, False


def cached_1m_rows(symbol: str, start_ms: int, end_ms: int, fetch_rows, cache_dir=None,
                   ttl: float = KLINE_CACHE_TTL, now=None):
    """1m bars for [start_ms, end_ms) shared across runners.

    fetch_rows(start_ms, end_ms) must return Bybit kline rows (newest-first or
    oldest-first list of [start_ms, open, high, low, close, ...]). Returns
    (rows_newest_first, from_cache). Closed-bar OHLC never changes, so cached
    bars for old minutes are reused even past the TTL; the TTL only gates how
    long a fully-covered range is served without any network. Miss path fetches
    the full range (bit-for-bit with the old behaviour) and merges it into the
    cache. Never raises on cache errors (falls back to fetch).
    """
    t = _cache_now(now)
    start_ms, end_ms = int(start_ms), int(end_ms)
    want = set(range(start_ms, end_ms, 60_000)) if end_ms > start_ms else set()
    cached = kline_cache_get(symbol, "bars_1m", cache_dir, ttl, now=t)
    have: dict = {}
    if isinstance(cached, dict):
        for k, v in cached.items():
            try:
                m = int(k)
            except (TypeError, ValueError):
                continue
            if m in want and isinstance(v, (list, tuple)) and len(v) >= 4:
                try:
                    have[m] = [float(v[0]), float(v[1]), float(v[2]), float(v[3])]
                except (TypeError, ValueError):
                    continue
    if want and set(have) >= want:
        rows = [[str(m), str(have[m][0]), str(have[m][1]), str(have[m][2]), str(have[m][3]), "0", "0"]
                for m in sorted(have, reverse=True) if m in want]
        return rows, True
    rows = fetch_rows(start_ms, end_ms)
    try:
        path = kline_cache_path(symbol, cache_dir)
        with _kline_locked(path.with_suffix(".lock")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except (OSError, ValueError):
                doc = {}
            if not isinstance(doc, dict):
                doc = {}
            ent = doc.get("bars_1m")
            bars = dict(ent["v"]) if isinstance(ent, dict) and isinstance(ent.get("v"), dict) else {}
            for r in rows or []:
                try:
                    m = int(r[0])
                    bars[str(m)] = [float(r[1]), float(r[2]), float(r[3]), float(r[4])]
                except (TypeError, ValueError, IndexError):
                    continue
            while len(bars) > int(KLINE_CACHE_MAX_BARS):
                try:
                    bars.pop(min(bars, key=int))
                except (TypeError, ValueError):
                    break
            doc["bars_1m"] = {"t": t, "v": bars}
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, path)
    except Exception:
        pass
    return rows, False


def sign(secret: str, timestamp: str, api_key: str, recv_window: str, payload: str) -> str:
    return hmac.new(secret.encode(), (timestamp + api_key + recv_window + payload).encode(), hashlib.sha256).hexdigest()


class BybitError(RuntimeError):
    pass


class Bybit:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None, base: str = TESTNET, timeout: float = 10.0):
        self.key, self.secret, self.base, self.timeout = api_key, api_secret, base, timeout
        self.s = requests.Session()

    # ---- transport -------------------------------------------------------------------------------------------------------------
    def _check(self, r):
        r.raise_for_status()
        d = r.json()
        if d.get("retCode") != 0:
            raise BybitError(f"{d.get('retCode')}: {d.get('retMsg')}")
        return d.get("result", {})

    def public(self, path: str, **params):
        for attempt in range(4):  # 10006 = IP rate limit: back off and retry (public market data only)
            try:
                return self._check(self.s.get(self.base + path, params=params, timeout=self.timeout))
            except BybitError as e:
                if "10006" not in str(e) or attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))

    def _headers(self, payload: str):
        if not (self.key and self.secret):
            raise BybitError("signed call without API keys")
        ts = str(int(time.time() * 1000))
        return {"X-BAPI-API-KEY": self.key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": RECV_WINDOW, "X-BAPI-SIGN-TYPE": "2",
                "X-BAPI-SIGN": sign(self.secret, ts, self.key, RECV_WINDOW, payload), "Content-Type": "application/json"}

    def get(self, path: str, **params):
        q = urlencode(sorted((k, v) for k, v in params.items() if v is not None))
        return self._check(self.s.get(f"{self.base}{path}?{q}", headers=self._headers(q), timeout=self.timeout))

    def post(self, path: str, body: dict):
        payload = json.dumps(body, separators=(",", ":"))
        return self._check(self.s.post(self.base + path, data=payload, headers=self._headers(payload), timeout=self.timeout))

    # ---- market data -----------------------------------------------------------------------------------------------------------
    def instruments(self, symbols):
        out = {}
        for s in symbols:
            it = self.public("/v5/market/instruments-info", category="linear", symbol=s)["list"][0]
            lot, pf = it["lotSizeFilter"], it["priceFilter"]
            out[s] = dict(qty_step=lot["qtyStep"], min_qty=lot["minOrderQty"], min_notional=lot.get("minNotionalValue", "5"),
                          tick=pf["tickSize"])
        return out

    def klines(self, symbol: str, interval: str = "5", limit: int = 3):
        """Newest first: [start_ms, open, high, low, close, volume, turnover]."""
        return self.public("/v5/market/kline", category="linear", symbol=symbol, interval=interval, limit=limit)["list"]

    def klines_4h_opens(self, symbol: str, n: int = 1200) -> list:
        """Last n 4h opens oldest-first (closed and current bars; the current bar's open is known)."""
        rows: list = []
        end = None
        while len(rows) < int(n):
            batch_limit = min(1000, int(n) - len(rows))
            kw: dict = dict(category="linear", symbol=symbol, interval="240", limit=batch_limit)
            if end is not None:
                kw["end"] = end
            batch = self.public("/v5/market/kline", **kw)["list"]
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < batch_limit:
                break
            oldest = min(int(r[0]) for r in batch)
            nxt = oldest - 1
            if end is not None and nxt >= int(end):
                break
            end = nxt
        rows = sorted(rows, key=lambda r: int(r[0]))[-int(n):]
        return [float(r[1]) for r in rows]

    # ---- account / orders ------------------------------------------------------------------------------------------------------
    def equity_usdt(self) -> float:
        acc = self.get("/v5/account/wallet-balance", accountType="UNIFIED")["list"][0]
        return float(acc["totalEquity"])

    def open_orders(self):
        return self.get("/v5/order/realtime", category="linear", settleCoin="USDT", limit=50)["list"]

    def executions(self, start_ms: int):
        return self.get("/v5/execution/list", category="linear", startTime=start_ms, limit=100)["list"]

    def hedge_mode(self):
        return self.post("/v5/position/switch-mode", {"category": "linear", "coin": "USDT", "mode": 3})

    def place(self, o: dict):
        return self.post("/v5/order/create", dict(category="linear", **o))

    def amend(self, symbol: str, link: str, **kw):
        return self.post("/v5/order/amend", dict(category="linear", symbol=symbol, orderLinkId=link, **kw))

    def cancel(self, symbol: str, link: str):
        return self.post("/v5/order/cancel", {"category": "linear", "symbol": symbol, "orderLinkId": link})


def round_step(x: float, step: str, up: bool = False) -> str:
    """Round x to a multiple of step (string, exact decimal); down unless up."""
    d, st = Decimal(str(x)), Decimal(step)
    q = (d / st).to_integral_value(rounding=ROUND_UP if up else ROUND_DOWN) * st
    return format(q.normalize() if q != 0 else Decimal(0), "f")
