"""Minimal Bybit V5 REST client (USDT linear perpetuals): public market data + signed account / order calls.

Testnet by default. Signing (V5, HMAC-SHA256): sign(timestamp + api_key + recv_window + payload), payload = the query string for GET and the
JSON body for POST. Keys are read from the environment / .env by the caller and never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from urllib.parse import urlencode

import requests

TESTNET = "https://api-testnet.bybit.com"
MAINNET = "https://api.bybit.com"
RECV_WINDOW = "10000"


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
