"""Paper exchange with the Bybit client's interface, filled from LIVE Bybit 1m klines (prospective bot evidence without API keys).

Fill rules (as the research engine, stated conservatively):
- an order can fill only in minutes that START after it was placed (the placement minute never fills);
- limit buy fills when the minute's low < price, limit sell when the high > price (strict trade-through), at the limit price, maker 0.0002;
- PostOnly: rejected at placement if it would cross the last 1m close (buy price >= close, sell price <= close);
- conditional market stop: long (triggerDirection 2) when low <= trigger at min(trigger, minute open); short (1) when high >= trigger at
  max(trigger, minute open); taker 0.00055; a stop and a take-profit of the same position in the same minute -> the stop first;
- market orders fill at the open of the first minute after placement, taker 0.00055;
- IOC limits (bot_carry entry legs, categories spot / dated-future): fill
  immediately at the limit price (maker 0.0002) when the limit crosses the
  current price - Buy px >= ask, Sell px <= bid - where ask/bid is the paper
  ticker when the public client has one, else the last closed 1m close +- one
  tick (dated futures use their own symbol's close); a non-crossing IOC is
  cancelled by the exchange at placement (no resting order, no fill);
- reduce-only orders are capped at the position size (cancelled when the position is flat);
- funding (gate rule, adverse): longs pay 0.0001 x notional at 00 / 08 / 16 UTC, shorts receive nothing.
Hedge mode: positions keyed (symbol, positionIdx), idx 1 = long, idx 2 = short.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pandas as pd

from bot.bybit_v5 import cached_1m_rows

MAKER, TAKER, FUNDING = 0.0002, 0.00055, 0.0001


class PaperExchange:
    def __init__(self, public, path: Path, equity0: float, symbols):
        self.pub, self.path, self.symbols = public, path, list(symbols)
        if path.exists():
            self.s = json.loads(path.read_text())
        else:
            now_min = int(pd.Timestamp.now(tz="UTC").floor("min").timestamp() * 1000)
            self.s = dict(cash=equity0, equity0=equity0, orders={}, pos={}, execs=[], last_ms={s: now_min for s in self.symbols},
                          last_close={}, funding_paid=0.0, fees=0.0)

    # ---- persistence ---------------------------------------------------------------------------------------------------------
    def save(self):
        self.s["execs"] = self.s["execs"][-2000:]
        self.path.write_text(json.dumps(self.s, indent=1))

    # ---- Bybit-like interface ------------------------------------------------------------------------------------------------
    def instruments(self, symbols):
        return self.pub.instruments(symbols)

    def klines(self, symbol, interval="5", limit=3):
        return self.pub.klines(symbol, interval, limit)

    def hedge_mode(self):
        return {}

    def _pos(self, sym, idx):
        return self.s["pos"].setdefault(f"{sym}|{idx}", dict(qty=0.0, avg=0.0))

    def _spot(self, sym):
        return self.s.setdefault("spot", {}).setdefault(sym, dict(qty=0.0, avg=0.0))

    def equity_usdt(self) -> float:
        eq = self.s["cash"]
        for k, p in self.s["pos"].items():
            sym, idx = k.split("|")
            px = self.s["last_close"].get(sym)
            if px and p["qty"]:
                eq += (px - p["avg"]) * p["qty"] * (1 if idx == "1" else -1)
        for sym, sp in (self.s.get("spot") or {}).items():
            try:
                q = float(sp.get("qty", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if q:
                px = self.s["last_close"].get(sym)
                if px:
                    eq += q * float(px)
        return eq

    def open_orders(self):
        return [dict(orderLinkId=k, symbol=o["symbol"], price=o.get("price"), triggerPrice=o.get("triggerPrice"), qty=o["qty"])
                for k, o in self.s["orders"].items()]

    def executions(self, start_ms):
        return [e for e in self.s["execs"] if int(e["execTime"]) >= int(start_ms)]

    def _tick_size(self, sym):
        """Tick size for the IOC ask/bid proxy (cached; None when unknown)."""
        try:
            cache = self.__dict__.setdefault("_tick_cache", {})
        except Exception:
            cache = {}
        try:
            if sym in cache:
                return cache[sym]
        except TypeError:
            pass
        tick = None
        try:
            inst = self.pub.instruments([sym])
            tick = float((inst.get(sym) or {}).get("tick") or 0) or None
        except Exception:
            tick = None
        try:
            cache[sym] = tick
        except Exception:
            pass
        return tick

    def _ioc_book(self, sym, category):
        """Current (ask, bid): paper ticker when available, else last 1m close +- tick."""
        try:
            res = self.pub.public("/v5/market/tickers",
                                  category="spot" if category == "spot" else "linear",
                                  symbol=sym)
            row = (res.get("list") or [{}])[0]
            ask = float(row.get("ask1Price") or 0) or None
            bid = float(row.get("bid1Price") or 0) or None
            if ask and bid:
                return ask, bid
        except Exception:
            pass
        try:
            ref = self.s.get("last_close", {}).get(sym)
            ref = float(ref) if ref is not None else None
        except (TypeError, ValueError):
            ref = None
        if ref is None or not ref > 0:
            return None, None
        try:
            tick = float(self._tick_size(sym) or 0.0)
        except (TypeError, ValueError):
            tick = 0.0
        return ref + tick, ref - tick

    def _ioc_try_fill(self, o) -> bool | None:
        """Immediate IOC outcome: True = filled now, False = cancelled (never rests).

        Applies to spot and dated-future IOC limits only. A Buy crosses when
        px >= ask, a Sell when px <= bid; fills book at the limit price (maker).
        F5: an IOC whose ref price is unknown (no ticker, no last_close) is
        cancelled like a non-crossing IOC — a real exchange cancels it, it
        never rests for a later trade-through.
        """
        try:
            px = float(o.get("price"))
            qty = float(o.get("qty"))
        except (TypeError, ValueError):
            return False
        if not (px > 0 and qty > 0):
            return False
        try:
            link = o.get("orderLinkId")
            t_ms = int(o.get("t_ms") or 0)
        except (TypeError, ValueError):
            return False
        ask, bid = self._ioc_book(o.get("symbol"), o.get("category", "linear"))
        if ask is None or bid is None:
            return False
        side = o.get("side")
        if (side == "Buy" and px >= ask) or (side == "Sell" and px <= bid):
            self._fill(link, o, qty, px, MAKER, t_ms)
            return True
        return False

    def place(self, p: dict):
        o = dict(p, t_ms=int(pd.Timestamp.now(tz="UTC").timestamp() * 1000))
        last = self.s["last_close"].get(p["symbol"])
        if p.get("timeInForce") == "PostOnly" and last is not None:
            px = float(p["price"])
            if (p["side"] == "Buy" and px >= last) or (p["side"] == "Sell" and px <= last):
                return None  # rejected (PostOnly would cross)
        if o.get("timeInForce") == "IOC" and o.get("orderType") == "Limit":
            cat = o.get("category", "linear")
            sym = o.get("symbol")
            try:
                in_syms = sym in (self.symbols or [])
            except TypeError:
                in_syms = False
            if cat == "spot" or not in_syms or cat not in ("linear", "inverse"):
                hit = self._ioc_try_fill(o)
                if hit is True:
                    return dict(orderLinkId=o["orderLinkId"])  # filled at placement, nothing rests
                if hit is False:
                    return None  # cancelled by the exchange (IOC, no cross)
        self.s["orders"][p["orderLinkId"]] = o
        return dict(orderLinkId=p["orderLinkId"])

    def amend(self, symbol, link, **kw):
        o = self.s["orders"].get(link)
        if o is None:
            return None
        for k, v in kw.items():
            o[k] = v
        return dict(orderLinkId=link)

    def cancel(self, symbol, link):
        return self.s["orders"].pop(link, None) and dict(orderLinkId=link)

    # ---- matching ------------------------------------------------------------------------------------------------------------
    def _fill(self, link, o, qty, px, fee_rate, t_ms):
        # Spot legs (bot_carry): physical coin against USDT cash.
        if o.get("category") == "spot":
            sym = o["symbol"]
            sp = self._spot(sym)
            if o["side"] == "Buy":
                tot = sp["qty"] + qty
                sp["avg"] = (sp["avg"] * sp["qty"] + px * qty) / tot if tot > 0 else px
                sp["qty"] = tot
                self.s["cash"] -= qty * px
            else:
                qty = min(qty, sp["qty"])
                if qty <= 0:
                    return
                sp["qty"] -= qty
                self.s["cash"] += qty * px
            fee = fee_rate * qty * px
            self.s["cash"] -= fee
            self.s["fees"] += fee
            self.s["execs"].append(dict(execId=uuid.uuid4().hex, orderLinkId=link, execQty=str(qty), execPrice=str(px), execTime=str(t_ms)))
            return
        sym, idx = o["symbol"], int(o.get("positionIdx", 1))
        p = self._pos(sym, idx)
        sgn = 1 if idx == 1 else -1
        opening = (o["side"] == "Buy") == (idx == 1)
        if opening:
            tot = p["qty"] + qty
            p["avg"] = (p["avg"] * p["qty"] + px * qty) / tot
            p["qty"] = tot
        else:
            qty = min(qty, p["qty"])
            if qty <= 0:
                return
            self.s["cash"] += (px - p["avg"]) * qty * sgn
            p["qty"] -= qty
        fee = fee_rate * qty * px
        self.s["cash"] -= fee
        self.s["fees"] += fee
        self.s["execs"].append(dict(execId=uuid.uuid4().hex, orderLinkId=link, execQty=str(qty), execPrice=str(px), execTime=str(t_ms)))

    def _minute(self, sym, t_ms, o_, h, l, c):
        mine = [(k, o) for k, o in self.s["orders"].items() if o["symbol"] == sym and o["t_ms"] < t_ms]
        # stops first (stop-first tie rule), then market orders, then limits
        order = sorted(mine, key=lambda ko: 0 if ko[1].get("triggerPrice") else (1 if ko[1]["orderType"] == "Market" else 2))
        for k, o in order:
            if k not in self.s["orders"]:
                continue
            idx = int(o.get("positionIdx", 1))
            qty = float(o["qty"])
            if o.get("reduceOnly"):
                if o.get("category") == "spot":
                    continue  # spot sale at delivery is not reduce-only-gated; capped in _fill
                have = self._pos(sym, idx)["qty"]
                if have <= 0:
                    self.s["orders"].pop(k)
                    continue
                qty = min(qty, have)
            if o.get("category") == "spot" and o["side"] == "Sell" and o["orderType"] == "Market":
                qty = min(qty, self._spot(sym)["qty"]) if self._spot(sym)["qty"] > 0 else qty
            if o.get("triggerPrice"):
                tr = float(o["triggerPrice"])
                if int(o.get("triggerDirection", 2)) == 2 and l <= tr:
                    self._fill(k, o, qty, min(tr, o_), TAKER, t_ms)
                elif int(o.get("triggerDirection", 2)) == 1 and h >= tr:
                    self._fill(k, o, qty, max(tr, o_), TAKER, t_ms)
                else:
                    continue
            elif o["orderType"] == "Market":
                self._fill(k, o, qty, o_, TAKER, t_ms)
            else:
                px = float(o["price"])
                if (o["side"] == "Buy" and l < px) or (o["side"] == "Sell" and h > px):
                    self._fill(k, o, qty, px, MAKER, t_ms)
                else:
                    continue
            self.s["orders"].pop(k, None)
        self.s["last_close"][sym] = c
        ts = pd.Timestamp(t_ms, unit="ms", tz="UTC")
        if ts.minute == 0 and ts.hour % 8 == 0:  # funding settlement (gate rule: longs pay, shorts receive nothing)
            p = self._pos(sym, 1)
            if p["qty"] > 0:
                f = FUNDING * p["qty"] * o_
                self.s["cash"] -= f
                self.s["funding_paid"] += f

    def step(self, now=None):
        """Process every CLOSED 1m bar since the last call (live Bybit klines,
        shared across runners via the on-disk kline cache, TTL 20 s)."""
        now_ms = int(pd.Timestamp(now or pd.Timestamp.now(tz="UTC")).floor("min").timestamp() * 1000)
        # bot_carry: dated quarterly symbols ride along (same 1m trade-through
        # fills as every other paper order).
        extra = {o["symbol"] for o in self.s["orders"].values()
                 if o.get("symbol") not in self.symbols}
        # ops_carrygap 2026-10-07: also poll symbols with an OPEN position (e.g. the dated carry short after its IOC entry filled):
        # without a resting order they never got a kline, last_close stayed empty and equity_usdt() valued the short at 0.
        for _k, _p in (self.s.get("pos") or {}).items():
            try:
                _sym = _k.split("|")[0]
                if float(_p.get("qty") or 0) and _sym not in self.symbols:
                    extra.add(_sym)
            except (AttributeError, TypeError, ValueError):
                continue
        extra = sorted(extra)
        for sym in list(self.symbols) + extra:
            start = int(self.s.setdefault("last_ms", {}).setdefault(
                sym, min(int(self.s["last_ms"].get(s, now_ms)) for s in self.symbols) if self.s.get("last_ms") else now_ms))
            if start >= now_ms:
                continue
            cache_dir = getattr(self, "cache_dir", None)

            def _fetch(s=start, e=now_ms - 1, _sym=sym):
                return self.pub.public("/v5/market/kline", category="linear", symbol=_sym,
                                       interval="1", start=s, end=e, limit=1000)["list"]

            try:
                rows, _hit = cached_1m_rows(sym, start, now_ms, _fetch, cache_dir=cache_dir)
            except Exception:
                rows = self.pub.public("/v5/market/kline", category="linear", symbol=sym, interval="1",
                                       start=start, end=now_ms - 1, limit=1000)["list"]
            for r in sorted(rows, key=lambda r: int(r[0])):
                t = int(r[0])
                if t < start or t >= now_ms:
                    continue  # bar in progress / already processed
                self._minute(sym, t, *(float(x) for x in r[1:5]))
                self.s["last_ms"][sym] = t + 60_000
        hour = str(pd.Timestamp(now_ms, unit="ms", tz="UTC").floor("h"))
        curve = self.s.setdefault("equity_curve", [])
        if not curve or curve[-1][0] != hour:  # one mark-to-market point per hour (first cycle of the hour)
            curve.append([hour, round(self.equity_usdt(), 4)])
        self.save()
