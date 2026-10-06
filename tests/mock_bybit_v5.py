"""Fake in-process Bybit V5 layer for bot tests (no network, no keys).

The real ``bot.bybit_v5.Bybit`` client talks to this fake through its own HTTP
calls: :meth:`MockBybitV5.install_session` monkeypatches ``requests`` at the
``Session.get`` / ``Session.post`` level, so the client's real signing, V5
field names, ``retCode`` handling (``_check``) and the ``10006`` backoff in
``Bybit.public`` all run unmodified. The fake answers with V5 envelopes
(``{"retCode":..,"retMsg":..,"result":..}``); any non-Bybit URL raises, so the
tests are offline by construction.

Matching follows ``bot/paper.py`` conservatively: limits fill only on a strict
1m trade-through in a minute that starts after placement, stops are
conditional-market with the stop-first rule, PostOnly crossing limits are
rejected with 110079, qty/notional violations raise 110094/170136-style
errors, and a 10006 burst can be injected on demand (``fail_public`` /
``fail_signed`` counters).
"""
from __future__ import annotations

import json
import time
import uuid
from urllib.parse import parse_qsl, urlparse

import requests

from bot.bybit_v5 import MAINNET, TESTNET, BybitError

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

DEFAULT_INST = {
    "BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1"),
    "ETHUSDT": dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01"),
    "SOLUSDT": dict(qty_step="0.1", min_qty="0.1", min_notional="5", tick="0.01"),
    "BNBUSDT": dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01"),
    "XRPUSDT": dict(qty_step="1", min_qty="1", min_notional="5", tick="0.0001"),
}

_DEFAULT_PX = {"BTCUSDT": 80000.0, "ETHUSDT": 3000.0, "SOLUSDT": 150.0,
               "BNBUSDT": 600.0, "XRPUSDT": 2.0}


class FakeResponse:
    """Minimal ``requests`` response: HTTP 200 carrying a V5 envelope."""

    def __init__(self, envelope):
        self._env = envelope

    def raise_for_status(self):
        return None

    def json(self):
        return self._env


class MockBybitV5:
    """In-memory V5 exchange answering at the HTTP layer."""

    def __init__(self, prices=None, equity=10000.0, inst=None):
        self.prices = {s: _DEFAULT_PX[s] for s in SYMS}
        for s, v in (prices or {}).items():
            self.prices[s] = float(v)
        self.inst_map = dict(inst or DEFAULT_INST)
        self.cash = float(equity)
        self.orders: dict = {}  # link -> stored payload + t_ms
        self.pos: dict = {}  # (sym, idx) -> {qty, avg}
        self.execs: list = []
        self.fail_public = 0  # next N public HTTP calls answer 10006
        self.fail_signed = 0  # next N signed HTTP calls answer 10006
        self.calls: list = []

    # ---- prices -----------------------------------------------------------------
    def set_price(self, sym, px):
        self.prices[sym] = float(px)

    def _kline_rows(self, symbol, limit):
        now_ms = int(time.time() * 1000)
        closed_ms = now_ms - (now_ms % 60_000) - 60_000
        px = float(self.prices.get(symbol, 0.0))
        return [[str(closed_ms - i * 60_000), str(px), str(px), str(px), str(px), "1", "1"]
                for i in range(int(limit))]

    # ---- HTTP entry point ---------------------------------------------------------
    def install_session(self, monkeypatch):
        """Route the real client's HTTP calls to this fake (offline by construction)."""
        mock = self

        def fake_get(session_self, url, params=None, **kw):
            return FakeResponse(mock._http("GET", url, params=params, data=None))

        def fake_post(session_self, url, data=None, **kw):
            return FakeResponse(mock._http("POST", url, params=None, data=data))

        monkeypatch.setattr(requests.Session, "get", fake_get)
        monkeypatch.setattr(requests.Session, "post", fake_post)
        return self

    def _http(self, method, url, params=None, data=None):
        if not url.startswith((TESTNET, MAINNET)):
            raise AssertionError(f"network disabled in mockex tests: {url}")
        path = urlparse(url).path
        query = dict(parse_qsl(urlparse(url).query))
        if isinstance(params, dict):
            query.update({k: v for k, v in params.items() if v is not None})
        try:
            body = json.loads(data) if data else {}
        except (TypeError, ValueError):
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            result = self._route(method, path, query, body)
        except BybitError as e:
            msg = str(e)
            code, _, text = msg.partition(":")
            try:
                code = int(code.strip())
            except (TypeError, ValueError):
                code, text = 10001, msg
            return {"retCode": code, "retMsg": (text.strip() or msg)[:256], "result": {}}
        return {"retCode": 0, "retMsg": "OK", "result": result}

    def _is_public(self, path):
        return path in ("/v5/market/instruments-info", "/v5/market/kline")

    def _route(self, method, path, query, body):
        self.calls.append((method, path, dict(query), dict(body)))
        if self._is_public(path):
            if self.fail_public > 0:
                self.fail_public -= 1
                raise BybitError("10006: Too many visits (mock public rate limit)")
            if path == "/v5/market/instruments-info":
                return self._instruments(query.get("symbol"))
            return self._kline(query)
        if self.fail_signed > 0:
            self.fail_signed -= 1
            raise BybitError("10006: Too many visits (mock signed rate limit)")
        if method == "GET" and path == "/v5/account/wallet-balance":
            return {"list": [{"totalEquity": str(self.equity_usdt())}]}
        if method == "GET" and path == "/v5/order/realtime":
            return {"list": [dict(orderLinkId=k, symbol=o["symbol"], side=o.get("side"),
                                  orderType=o.get("orderType"), price=o.get("price"),
                                  triggerPrice=o.get("triggerPrice"), qty=o.get("qty"),
                                  positionIdx=o.get("positionIdx"),
                                  reduceOnly=o.get("reduceOnly", False))
                            for k, o in self.orders.items()]}
        if method == "GET" and path == "/v5/execution/list":
            start = int(query.get("startTime", 0) or 0)
            return {"list": [e for e in self.execs if int(e["execTime"]) >= start]}
        if method == "GET" and path == "/v5/position/list":
            return {"list": [dict(symbol=sym, positionIdx=idx, size=str(p["qty"]),
                                  avgPrice=str(p["avg"]), side="Buy" if idx == 1 else "Sell")
                             for (sym, idx), p in self.pos.items() if p["qty"] > 0]}
        if method == "POST" and path == "/v5/position/switch-mode":
            return {}
        if method == "POST" and path == "/v5/order/create":
            return self._create(body)
        if method == "POST" and path == "/v5/order/amend":
            o = self.orders.get(body.get("orderLinkId"))
            if o is None:
                raise BybitError("110001: Order does not exist")
            for k in ("price", "qty", "triggerPrice"):
                if k in body and body[k] is not None:
                    o[k] = body[k]
            return dict(orderLinkId=body.get("orderLinkId"))
        if method == "POST" and path == "/v5/order/cancel":
            o = self.orders.pop(body.get("orderLinkId"), None)
            if o is None:
                raise BybitError("110001: Order does not exist")
            return dict(orderLinkId=body.get("orderLinkId"))
        raise BybitError(f"10001: mock has no route for {method} {path}")

    # ---- V5 data --------------------------------------------------------------------
    def _instruments(self, symbol):
        it = self.inst_map[symbol]
        return {"list": [{"symbol": symbol,
                           "lotSizeFilter": {"qtyStep": it["qty_step"], "minOrderQty": it["min_qty"],
                                             "minNotionalValue": it["min_notional"]},
                           "priceFilter": {"tickSize": it["tick"]}}]}

    def _kline(self, query):
        sym = query.get("symbol")
        limit = int(query.get("limit", 2) or 2)
        if query.get("interval") == "240":  # 4h opens: flat series at the last price
            px = float(self.prices.get(sym, 0.0))
            n = min(limit, 1200)
            now_ms = int(time.time() * 1000)
            rows = [[str(now_ms - (n - 1 - i) * 14_400_000), str(px), str(px),
                     str(px), str(px), "1", "1"] for i in range(n)]
            return {"list": list(reversed(rows))}
        return {"list": self._kline_rows(sym, limit)}

    def _create(self, p):
        sym, side = p.get("symbol"), p.get("side")
        link = p.get("orderLinkId")
        if sym not in self.inst_map:
            raise BybitError("110014: Symbol not allowed")
        try:
            qty = float(p.get("qty", 0))
        except (TypeError, ValueError):
            raise BybitError("110094: Abnormal order quantity")
        it = self.inst_map[sym]
        if not qty > 0 or qty < float(it["min_qty"]) - 1e-12:
            raise BybitError(f"110094: Order quantity below minimum {it['min_qty']}")
        otype = p.get("orderType")
        ro = bool(p.get("reduceOnly"))
        if otype == "Market" and not ro:
            raise BybitError("110094: Market order must be reduce-only in hedge mock")
        px_raw = p.get("price")
        px = float(px_raw) if px_raw is not None else None
        if otype == "Limit":
            if px is None or not px > 0:
                raise BybitError("170136: Abnormal order price")
            if not ro and qty * px < float(it["min_notional"]) - 1e-9:
                raise BybitError(f"170136: Order notional below minimum {it['min_notional']}")
            if p.get("timeInForce") == "PostOnly":
                last = self.prices.get(sym)
                if last is not None:
                    if (side == "Buy" and px >= float(last)) or (side == "Sell" and px <= float(last)):
                        raise BybitError("110079: Post-only order would cross the book")
        self.orders[link] = dict(p, t_ms=int(time.time() * 1000))
        return dict(orderId=uuid.uuid4().hex, orderLinkId=link)

    # ---- matching (paper.py rules) ----------------------------------------------------
    def equity_usdt(self):
        eq = self.cash
        for (sym, idx), p in self.pos.items():
            last = self.prices.get(sym)
            if last and p["qty"]:
                eq += (float(last) - p["avg"]) * p["qty"] * (1 if idx == 1 else -1)
        return eq

    def _execute(self, link, o, qty, px, t_ms):
        sym, idx = o["symbol"], int(o.get("positionIdx", 1))
        p = self.pos.setdefault((sym, idx), dict(qty=0.0, avg=0.0))
        sgn = 1 if idx == 1 else -1
        opening = (o["side"] == "Buy") == (idx == 1)
        if opening:
            tot = p["qty"] + qty
            p["avg"] = (p["avg"] * p["qty"] + px * qty) / tot if tot > 0 else px
            p["qty"] = tot
        else:
            qty = min(qty, p["qty"])
            if qty <= 0:
                self.orders.pop(link, None)
                return
            self.cash += (px - p["avg"]) * qty * sgn
            p["qty"] -= qty
        self.execs.append(dict(execId=uuid.uuid4().hex, orderLinkId=link, symbol=sym,
                               execQty=str(qty), execPrice=str(px), execTime=str(t_ms)))

    def process_bar(self, sym, o, h, l, c, t_ms):
        """Fill resting orders of sym against one CLOSED 1m bar (stop-first)."""
        self.prices[sym] = float(c)
        mine = [(k, x) for k, x in self.orders.items()
                if x["symbol"] == sym and int(x.get("t_ms", 0)) < int(t_ms)]
        mine.sort(key=lambda kv: 0 if kv[1].get("triggerPrice") else (1 if kv[1].get("orderType") == "Market" else 2))
        filled = []
        for k, x in mine:
            if k not in self.orders:
                continue
            qty = float(x["qty"])
            if x.get("reduceOnly"):
                have = self.pos.get((sym, int(x.get("positionIdx", 1))), {}).get("qty", 0.0)
                if have <= 0:
                    self.orders.pop(k, None)
                    continue
                qty = min(qty, have)
            if x.get("triggerPrice"):
                tr = float(x["triggerPrice"])
                td = int(x.get("triggerDirection", 2))
                if td == 2 and l <= tr:
                    self._execute(k, x, qty, min(tr, o), t_ms)
                elif td == 1 and h >= tr:
                    self._execute(k, x, qty, max(tr, o), t_ms)
                else:
                    continue
            elif x.get("orderType") == "Market":
                self._execute(k, x, qty, o, t_ms)
            else:
                px = float(x["price"])
                if (x["side"] == "Buy" and l < px) or (x["side"] == "Sell" and h > px):
                    self._execute(k, x, qty, px, t_ms)
                else:
                    continue
            self.orders.pop(k, None)
            filled.append(k)
        return filled

    def manual_fill(self, link, qty, price, t_ms):
        """Partial (or full) fill of one resting order, keeping the remainder."""
        o = self.orders.get(link)
        if o is None:
            raise BybitError("110001: Order does not exist")
        qty = min(float(qty), float(o["qty"]))
        self._execute(link, o, qty, float(price), t_ms)
        rest = float(o["qty"]) - qty
        if rest <= 1e-12:
            self.orders.pop(link, None)
        else:
            o["qty"] = str(rest)
        return rest
