"""Order-mirror bot runner: follow a merged paper trade plan on Bybit USDT perps (hedge mode).

  .venv/Scripts/python.exe -m bot.run --once                       dry run: prints what would be placed / cancelled now (no keys needed)
  .venv/Scripts/python.exe -m bot.run --mode paper --equity 2000   simulated account filled from LIVE Bybit 1m klines (prospective bot log)
  .venv/Scripts/python.exe -m bot.run --mode testnet               loop every 20 s on Bybit TESTNET (BYBIT_TESTNET_API_KEY / _SECRET in .env)
  .venv/Scripts/python.exe -m bot.run --mode live                  REAL MONEY: refused unless BOT_ALLOW_LIVE=yes-real-money is set by the owner

State (piece ledger, bot-owned orders, last execution time) in artifacts/bot/<mode>/state.json; every action is appended to
artifacts/bot/<mode>/actions.jsonl. Safety: a plan older than 2 hours blocks NEW entries (exits keep running); a dry run never sends.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

from bot import mirror
from bot.bybit_v5 import MAINNET, TESTNET, Bybit, BybitError, round_step
from bot.paper import PaperExchange

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "artifacts/research/advisor_shadow/trade_plan_v376.json"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
STALE_PLAN = pd.Timedelta(hours=4, minutes=30)  # a 4h plan is valid until the next bar plan (+ generation delay)


def parse_dip_sl_coin(items) -> dict:
    """Parse repeatable --dip-sl-coin SYMBOL=M into {SYMBOL: M} (v417 row X)."""
    out: dict = {}
    for it in items or []:
        try:
            sym, m = str(it).split("=", 1)
        except ValueError:
            sys.exit(f"bad --dip-sl-coin {it!r}: want SYMBOL=M")
        sym, m = sym.strip().upper(), m.strip()
        if sym not in SYMS:
            sys.exit(f"bad --dip-sl-coin {it!r}: symbol must be one of {','.join(SYMS)}")
        try:
            out[sym] = float(m)
        except ValueError:
            sys.exit(f"bad --dip-sl-coin {it!r}: M must be a number")
        if not out[sym] > 0:
            sys.exit(f"bad --dip-sl-coin {it!r}: M must be positive")
    return out


def env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def to_exchange(o: mirror.Order, inst: dict) -> dict | None:
    """Rounded Bybit order payload, or None when below the lot / notional minimum."""
    it = inst[o.symbol]
    qty = round_step(o.qty, it["qty_step"])
    if float(qty) < float(it["min_qty"]):
        return None
    p = dict(symbol=o.symbol, side=o.side, qty=qty, orderLinkId=o.link, positionIdx=o.position_idx)
    if o.kind == "stop":
        long_piece = o.side == "Sell"
        p.update(orderType="Market", triggerPrice=round_step(o.trigger, it["tick"], up=not long_piece), triggerDirection=2 if long_piece else 1,
                 triggerBy="LastPrice", reduceOnly=True, closeOnTrigger=True)
        return p
    up = o.side == "Sell"  # sell limits round up, buy limits round down (never a worse price than the plan)
    price = round_step(o.price, it["tick"], up=up)
    if not o.reduce_only and float(qty) * float(price) < float(it["min_notional"]):
        return None
    p.update(orderType="Limit", price=price, timeInForce="GTC")  # a crossing limit fills at once (taker, better price) instead of being lost
    if o.reduce_only:
        p["reduceOnly"] = True
    return p


class Runner:
    def __init__(self, mode: str, plan_path: Path, equity: float | None, risk_mult: float = 1.0, corr: bool = False,
                 tag: str | None = None, dip_mult: float = 1.0, bear_book: bool = False,
                 dip_cooldown_h: float = 0.0, dip_sl_coin: dict | None = None):
        self.mode, self.plan_path = mode, plan_path
        self.risk_mult, self.corr, self.tag, self.dip_mult = float(risk_mult), bool(corr), tag or None, float(dip_mult)
        self.bear_book = bool(bear_book)
        self.dip_cooldown_h = float(dip_cooldown_h or 0.0)
        self.dip_sl_coin = dict(dip_sl_coin or {})
        self._bear_at = None
        self._bear = False
        self._last_plan = None
        self.dir = ROOT / "artifacts/bot" / (mode if not self.tag else f"{mode}_{self.tag}")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_f = self.dir / "state.json"
        self.state = json.loads(self.state_f.read_text()) if self.state_f.exists() else dict(ledger={}, links={}, last_exec_ms=None)
        if mode == "dry":
            self.ex = Bybit(base=MAINNET)  # public data only
        elif mode == "paper":  # simulated account filled from live Bybit 1m klines (no keys)
            self.ex = PaperExchange(Bybit(base=MAINNET), self.dir / "exchange.json", equity or 1000.0, SYMS)
        else:
            key, sec = (env("BYBIT_TESTNET_API_KEY"), env("BYBIT_TESTNET_API_SECRET")) if mode == "testnet" else (env("BYBIT_API_KEY"), env("BYBIT_API_SECRET"))
            if not (key and sec):
                sys.exit(f"missing API keys for {mode} in .env")
            self.ex = Bybit(key, sec, base=TESTNET if mode == "testnet" else MAINNET)
            try:
                self.ex.hedge_mode()
            except BybitError as e:  # already in hedge mode (or positions open): keep going, logged
                self.log(dict(op="hedge_mode", note=str(e)))
        self.equity_arg = equity
        self.inst = self.ex.instruments(SYMS)

    def log(self, rec: dict):
        rec = dict(t=str(pd.Timestamp.now(tz="UTC")), mode=self.mode, **rec)
        with open(self.dir / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(json.dumps(rec, default=str), flush=True)

    def send(self, fn, *a, **kw):
        if self.mode == "dry":
            return None
        try:
            return fn(*a, **kw)
        except (BybitError, OSError) as e:
            self.log(dict(op="error", call=getattr(fn, "__name__", "?"), note=str(e)))
            return None

    def sync_fills(self):
        """Exchange executions of bot links -> piece ledger (testnet / live only)."""
        if self.mode == "dry":
            return
        last = self.state.get("last_exec_ms")
        start = int(last) if last is not None else int((time.time() - 3600) * 1000)
        try:
            ex = self.ex.executions(start)
        except BybitError as e:
            self.log(dict(op="error", call="executions", note=str(e)))
            return
        seen = set(self.state.setdefault("seen_exec", [])[-500:])
        for e in sorted(ex, key=lambda r: int(r["execTime"])):
            link = e.get("orderLinkId") or ""
            if e["execId"] in seen or link not in self.state["links"]:
                continue
            o = mirror.Order(**self.state["links"][link]["order"])
            mirror.apply_fill(self.state["ledger"], o, float(e["execQty"]), float(e["execPrice"]), pd.Timestamp(int(e["execTime"]), unit="ms", tz="UTC"))
            seen.add(e["execId"])
            self.log(dict(op="fill", link=link, qty=e["execQty"], price=e["execPrice"]))
            if o.kind == "stop":
                pc = self.state["ledger"].get(o.piece)
                if isinstance(pc, dict) and pc.get("kind") == "dip":
                    # native backstop stop-out (TP fills have kind tp and never trigger the cooldown)
                    try:
                        t_exit = pd.Timestamp(int(e["execTime"]), unit="ms", tz="UTC")
                    except (TypeError, ValueError):
                        t_exit = pd.Timestamp.now(tz="UTC")
                    mirror.note_dip_stop(self.state["ledger"], o.piece, t_exit)
                    if self.dip_cooldown_h > 0:
                        self.log(dict(op="dip_cool", piece=o.piece, symbol=pc.get("symbol"), t=str(t_exit)))
            self.state["last_exec_ms"] = max(int(self.state.get("last_exec_ms") or 0), int(e["execTime"]))
        self.state["seen_exec"] = list(seen)

    def have(self) -> dict:
        if self.mode == "dry":
            return {k: v["rest"] for k, v in self.state["links"].items() if v.get("rest")}
        out = {}
        for o in self.ex.open_orders():
            link = o.get("orderLinkId") or ""
            if link in self.state["links"]:
                out[link] = dict(symbol=o["symbol"], price=o.get("price"), trigger=o.get("triggerPrice"), qty=o.get("qty"))
        return out

    def last5(self) -> dict:
        out = {}
        for s in SYMS:
            k = self.ex.klines(s, "5", 2)  # newest first: [0] = bar in progress, [1] = last closed bar
            if len(k) > 1:
                out[s] = (pd.Timestamp(int(k[1][0]), unit="ms", tz="UTC") + pd.Timedelta(minutes=5), float(k[1][4]))
        return out

    def last_close_1m(self) -> dict:
        """Last CLOSED 1m close per symbol (for correlation-aware dip sizing). Paper: the simulated exchange's
        last_close; testnet / live / dry: Bybit public klines (interval 1, limit 2, take the closed bar)."""
        if self.mode == "paper":
            try:
                return {s: float(v) for s, v in self.ex.s.get("last_close", {}).items() if v is not None}
            except (AttributeError, TypeError, ValueError):
                return {}
        out: dict = {}
        for s in SYMS:
            try:
                k = self.ex.klines(s, "1", 2)  # newest first: [0] = bar in progress, [1] = last closed bar
            except Exception:
                continue
            if len(k) > 1:
                try:
                    out[s] = float(k[1][4])
                except (TypeError, ValueError, IndexError):
                    continue
        return out

    def bear_now(self, now) -> bool:
        """Bear regime from BTCUSDT 4h opens (cached 10 minutes). Off -> False without any fetch."""
        if not self.bear_book:
            return False
        now = pd.Timestamp(now)
        if self._bear_at is not None and now - self._bear_at < pd.Timedelta(minutes=10):
            return self._bear
        try:
            pub = getattr(self.ex, "pub", self.ex)
            fn = getattr(pub, "klines_4h_opens", None) or getattr(self.ex, "klines_4h_opens", None)
            opens = fn("BTCUSDT") if fn is not None else []
        except Exception:
            return self._bear if self._bear_at is not None else False
        b = bool(mirror.is_bear(opens))
        try:
            n = len(opens)
        except TypeError:
            n = 0
        if self._bear_at is None or b != self._bear:
            self.log(dict(op="bear_state", bear=b, opens=n))
        self._bear, self._bear_at = b, now
        return b

    def _protection_only(self, led) -> dict:
        """Protection orders from the ledger alone (plan file missing and no cached plan)."""
        out = {}
        for pid, pc in led.items():
            try:
                qty = float(pc.get("qty", 0.0))
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            sym = pc.get("symbol")
            if not sym or sym not in self.inst:
                continue
            side = pc.get("side", 1)
            pidx = 1 if side > 0 else 2
            if pc.get("kind") == "dip":
                if pc.get("tp"):
                    out[pid + "T"] = mirror.Order(pid + "T", sym, "Sell", qty, "tp", price=pc["tp"],
                                                 reduce_only=True, position_idx=1, piece=pid)
                if pc.get("backstop"):
                    out[pid + "S"] = mirror.Order(pid + "S", sym, "Sell", qty, "stop", trigger=pc["backstop"],
                                                 reduce_only=True, position_idx=1, piece=pid)
            elif pc.get("kind") == "book" and pc.get("sl") and pc.get("tp"):
                sell = side > 0
                out[pid + "S"] = mirror.Order(pid + "S", sym, "Sell" if sell else "Buy", qty, "stop",
                                             trigger=float(pc["sl"]), reduce_only=True, position_idx=pidx, piece=pid)
                out[pid + "T"] = mirror.Order(pid + "T", sym, "Sell" if sell else "Buy", qty, "tp",
                                             price=float(pc["tp"]), reduce_only=True, position_idx=pidx, piece=pid)
        return out

    def cycle(self):
        now = pd.Timestamp.now(tz="UTC")
        if getattr(self, "_last_plan", None) is None:
            self._last_plan = None
        plan_ok = True
        try:
            plan = json.loads(self.plan_path.read_text())
            self._last_plan = plan
        except (OSError, json.JSONDecodeError, ValueError) as e:
            self.log(dict(op="plan_error", note=f"{type(e).__name__}: {e}"))
            if isinstance(self._last_plan, dict):
                plan = self._last_plan
                plan_ok = False
            else:
                # No cached plan: keep protection from the ledger only, place nothing new.
                if self.mode == "paper":
                    try:
                        self.ex.step(now)
                    except Exception:
                        pass
                try:
                    equity = self.equity_arg if self.mode == "dry" else self.ex.equity_usdt()
                except Exception:
                    equity = self.equity_arg or 0.0
                try:
                    self.sync_fills()
                except Exception:
                    pass
                led = self.state["ledger"]
                try:
                    last5 = self.last5()
                except Exception:
                    last5 = {}
                for pid, why in mirror.exits({"phases": [], "coins": {}}, now, led, last5):
                    if why == "plan_closed_divergence":
                        continue
                    pc = led[pid]
                    if pc.get("exit_sent") and now - pd.Timestamp(pc["exit_sent"]) < pd.Timedelta(minutes=2):
                        continue
                    pc["exit_sent"] = str(now)
                    link = f"{pid}X{mirror.t36(now)}"
                    qty = round_step(pc["qty"], self.inst[pc["symbol"]]["qty_step"])
                    payload = dict(symbol=pc["symbol"], side="Sell" if pc["side"] > 0 else "Buy", orderType="Market",
                                   qty=qty, reduceOnly=True, orderLinkId=link, positionIdx=1 if pc["side"] > 0 else 2)
                    self.log(dict(op="market_exit", piece=pid, reason=why, payload=payload))
                    if self.send(self.ex.place, payload) is not None or self.mode == "dry":
                        self.state["links"][link] = dict(order=asdict(mirror.Order(link, pc["symbol"], payload["side"], float(qty), "reduce",
                                                                                  reduce_only=True, position_idx=payload["positionIdx"], piece=pid)))
                        if self.mode == "dry":
                            pc["qty"] = 0.0
                want = self._protection_only(led)
                rounded, skipped = {}, []
                for k, o in want.items():
                    p = to_exchange(o, self.inst)
                    if p is None:
                        skipped.append(k)
                    else:
                        o = replace(o, qty=float(p["qty"]), price=float(p["price"]) if "price" in p else None,
                                    trigger=float(p["triggerPrice"]) if "triggerPrice" in p else None)
                        rounded[k] = (o, p)
                try:
                    have = self.have()
                except Exception:
                    have = {}
                acts = mirror.diff({k: o for k, (o, _) in rounded.items()}, have)
                for a in acts:
                    if a["op"] == "place":
                        o = a["order"]
                        p = rounded[o.link][1]
                        self.log(dict(op="place", payload=p))
                        if self.send(self.ex.place, p) is not None or self.mode == "dry":
                            self.state["links"][o.link] = dict(order=asdict(o), rest=dict(symbol=o.symbol, price=o.price, trigger=o.trigger, qty=o.qty))
                    elif a["op"] == "cancel":
                        self.log(dict(op="cancel", link=a["link"]))
                        if self.send(self.ex.cancel, a["symbol"], a["link"]) is not None or self.mode == "dry":
                            self.state["links"].get(a["link"], {}).pop("rest", None)
                    else:
                        kw = {k2: str(v) for k2, v in a.items() if k2 in ("price", "qty")}
                        if "trigger" in a:
                            kw["triggerPrice"] = str(a["trigger"])
                        self.log(dict(op="amend", link=a["link"], **kw))
                        if self.send(self.ex.amend, a["symbol"], a["link"], **kw) is not None or self.mode == "dry":
                            rest = self.state["links"][a["link"]].setdefault("rest", {})
                            rest.update({k2: a[k2] for k2 in ("price", "trigger", "qty") if k2 in a})
                if skipped:
                    self.log(dict(op="skipped_below_minimum", links=skipped, equity=equity))
                self.state_f.write_text(json.dumps(self.state, indent=1, default=str))
                if self.mode == "paper":
                    try:
                        self.ex.save()
                    except Exception:
                        pass
                return acts
        stale = now - pd.Timestamp(plan["generated_at"]) > STALE_PLAN
        if self.mode == "paper":
            self.ex.step(now)
        equity = self.equity_arg if self.mode == "dry" else self.ex.equity_usdt()
        self.sync_fills()
        led = self.state["ledger"]
        live = mirror.plan_book_live(plan)
        for pc in led.values():
            if pc["kind"] == "book" and pc["qty"] > 0:
                if (pc["phase"], pc["symbol"]) in live:
                    pc.pop("plan_gone_since", None)
                else:
                    pc.setdefault("plan_gone_since", str(now))
        for pid, why in mirror.exits(plan, now, led, self.last5()):
            pc = led[pid]
            if pc.get("exit_sent") and now - pd.Timestamp(pc["exit_sent"]) < pd.Timedelta(minutes=2):
                continue  # a market exit is in flight; wait for its fill before sending another
            pc["exit_sent"] = str(now)
            if why == "close5_stop" and pc.get("kind") == "dip":
                # bot close-stop stop-out (time exits and TP fills never trigger the cooldown)
                mirror.note_dip_stop(led, pid, now)
                if self.dip_cooldown_h > 0:
                    self.log(dict(op="dip_cool", piece=pid, symbol=pc.get("symbol"), t=str(now)))
            link = f"{pid}X{mirror.t36(now)}"
            qty = round_step(pc["qty"], self.inst[pc["symbol"]]["qty_step"])
            payload = dict(symbol=pc["symbol"], side="Sell" if pc["side"] > 0 else "Buy", orderType="Market", qty=qty, reduceOnly=True,
                           orderLinkId=link, positionIdx=1 if pc["side"] > 0 else 2)
            self.log(dict(op="market_exit", piece=pid, reason=why, payload=payload))
            if self.send(self.ex.place, payload) is not None or self.mode == "dry":
                self.state["links"][link] = dict(order=asdict(mirror.Order(link, pc["symbol"], payload["side"], float(qty), "reduce",
                                                                          reduce_only=True, position_idx=payload["positionIdx"], piece=pid)))
                if self.mode == "dry":
                    pc["qty"] = 0.0
        bear = self.bear_now(now)
        lc = self.last_close_1m() if (self.corr or self.bear_book) else None
        want = mirror.desired(plan, now, equity, led, risk_mult=self.risk_mult, corr=self.corr,
                              last_close=lc, dip_mult=self.dip_mult,
                              bear_book=self.bear_book, bear=bear,
                              dip_cooldown_h=self.dip_cooldown_h, dip_sl_coin=self.dip_sl_coin)
        if self.bear_book:
            if bear:
                for o in want.values():
                    if o.kind == "reduce" and o.meta.get("bear_trim") and o.piece in led:
                        led[o.piece]["trimmed_bear"] = True
            else:
                for pc in led.values():
                    pc.pop("trimmed_bear", None)
        if not plan_ok:
            # Cached plan after a plan_error: keep protection, place no new entries.
            want = {k: o for k, o in want.items() if o.kind in ("tp", "stop")}
        if stale:
            want = {k: o for k, o in want.items() if o.kind in ("tp", "stop", "reduce")}
            self.log(dict(op="stale_plan", generated_at=plan["generated_at"]))
        have_before = self.have()
        rounded, skipped = {}, []
        for k, o in want.items():
            p = to_exchange(o, self.inst)
            if p is None:
                skipped.append(k)
            else:
                o = replace(o, qty=float(p["qty"]), price=float(p["price"]) if "price" in p else None,
                            trigger=float(p["triggerPrice"]) if "triggerPrice" in p else None)  # compare / amend in exchange units
                rounded[k] = (o, p)
        acts = mirror.diff({k: o for k, (o, _) in rounded.items()}, have_before,
                           amend_entry_qty=(self.corr or self.risk_mult != 1.0 or self.dip_mult != 1.0))
        failed_stop_pieces, placed_stop_links = set(), set()
        for a in acts:
            if a["op"] == "place":
                o = a["order"]
                p = rounded[o.link][1]
                self.log(dict(op="place", payload=p))
                if self.send(self.ex.place, p) is not None or self.mode == "dry":
                    self.state["links"][o.link] = dict(order=asdict(o), rest=dict(symbol=o.symbol, price=o.price, trigger=o.trigger, qty=o.qty))
                    if o.kind == "stop":
                        placed_stop_links.add(o.link)
                elif o.kind == "stop":
                    failed_stop_pieces.add(o.piece)
            elif a["op"] == "cancel":
                self.log(dict(op="cancel", link=a["link"]))
                if self.send(self.ex.cancel, a["symbol"], a["link"]) is not None or self.mode == "dry":
                    self.state["links"].get(a["link"], {}).pop("rest", None)
            else:
                kw = {k2: str(v) for k2, v in a.items() if k2 in ("price", "qty")}
                if "trigger" in a:
                    kw["triggerPrice"] = str(a["trigger"])
                self.log(dict(op="amend", link=a["link"], **kw))
                if self.send(self.ex.amend, a["symbol"], a["link"], **kw) is not None or self.mode == "dry":
                    rest = self.state["links"][a["link"]].setdefault("rest", {})
                    rest.update({k2: a[k2] for k2 in ("price", "trigger", "qty") if k2 in a})
        if skipped:
            self.log(dict(op="skipped_below_minimum", links=skipped, equity=equity))
        # Unprotected positions: an open piece whose stop is wanted but rests nowhere and
        # whose placement just failed. Retry is automatic next cycle (want still has the
        # stop); after > 2 such cycles flatten at market (reduce-only) and log op=unprotected_close.
        if self.mode != "dry":
            for pid, pc in list(led.items()):
                try:
                    qty = float(pc.get("qty", 0.0))
                except (TypeError, ValueError):
                    continue
                if qty <= 0:
                    pc.pop("unprotected_cycles", None)
                    continue
                stop_links = [k for k, o in want.items() if o.piece == pid and o.kind == "stop"]
                if not stop_links:
                    pc.pop("unprotected_cycles", None)
                    continue
                rests = any(k in have_before or k in placed_stop_links for k in stop_links)
                if rests:
                    pc.pop("unprotected_cycles", None)
                    continue
                if pid in failed_stop_pieces or any(k not in have_before for k in stop_links):
                    # No resting stop and none placed successfully this cycle.
                    # Only count cycles where a placement was actually attempted and failed;
                    # a pure have-miss without a place act means the link was skipped below
                    # minimum (already logged) and must not trigger a market close.
                    if pid not in failed_stop_pieces:
                        continue
                    n = int(pc.get("unprotected_cycles", 0) or 0) + 1
                    pc["unprotected_cycles"] = n
                    if n > 2:
                        if pc.get("exit_sent") and now - pd.Timestamp(pc["exit_sent"]) < pd.Timedelta(minutes=2):
                            continue
                        pc["exit_sent"] = str(now)
                        link = f"{pid}U{mirror.t36(now)}"
                        q = round_step(qty, self.inst[pc["symbol"]]["qty_step"])
                        payload = dict(symbol=pc["symbol"], side="Sell" if pc["side"] > 0 else "Buy",
                                       orderType="Market", qty=q, reduceOnly=True, orderLinkId=link,
                                       positionIdx=1 if pc["side"] > 0 else 2)
                        self.log(dict(op="unprotected_close", piece=pid, payload=payload, cycles=n))
                        if self.send(self.ex.place, payload) is not None:
                            self.state["links"][link] = dict(order=asdict(mirror.Order(link, pc["symbol"], payload["side"], float(q), "reduce",
                                                                                      reduce_only=True, position_idx=payload["positionIdx"], piece=pid)))
                            pc.pop("unprotected_cycles", None)
        self.state_f.write_text(json.dumps(self.state, indent=1, default=str))
        if self.mode == "paper":
            self.ex.save()
        return acts


def single_instance(lock_path: Path):
    """Hold an exclusive OS lock on lock_path for the process lifetime; exit if another runner of this mode holds it."""
    f = open(lock_path, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(f"another bot runner holds {lock_path}")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("dry", "paper", "testnet", "live"), default="dry")
    ap.add_argument("--plan", default=str(PLAN))
    ap.add_argument("--equity", type=float, default=1000.0, help="dry run / paper start: account equity in USDT")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--risk-mult", type=float, default=1.0, help="scale all book/dip sizes and the dip budget (default 1.0 = unchanged)")
    ap.add_argument("--corr-size", action="store_true", help="shrink each dip rung by 1/(1+n) flushing peers (default off = unchanged)")
    ap.add_argument("--dip-mult", type=float, default=1.0, help="scale dip rung sizes only (v406/v408 R2B1D16/D18: 1.6/1.8; default 1.0 = unchanged)")
    ap.add_argument("--bear-book", action="store_true", help="halve book LONG entry/add qty while BTC trades below its 200-day mean (default off = unchanged)")
    ap.add_argument("--dip-cooldown-h", type=float, default=0.0, help="dip stop cooldown hours per coin+phase after a dip stop-out (v417 row C; default 0 = off)")
    ap.add_argument("--dip-sl-coin", action="append", default=[], metavar="SYMBOL=M", help="per-coin dip close-stop multiple replacing 4 sigma (repeatable, e.g. XRPUSDT=5.5; default none = unchanged)")
    ap.add_argument("--tag", default=None, help="state dir artifacts/bot/<mode>[_<tag>] (default no tag = unchanged paths)")
    a = ap.parse_args()
    if a.mode == "live" and os.environ.get("BOT_ALLOW_LIVE") != "yes-real-money":
        sys.exit("live trading is locked: the account owner must set BOT_ALLOW_LIVE=yes-real-money")
    mode_dir = a.mode if not a.tag else f"{a.mode}_{a.tag}"
    (ROOT / "artifacts/bot" / mode_dir).mkdir(parents=True, exist_ok=True)
    _lock = single_instance(ROOT / "artifacts/bot" / mode_dir / "runner.lock") if not a.once else None
    r = Runner(a.mode, Path(a.plan), a.equity, risk_mult=a.risk_mult, corr=a.corr_size, tag=a.tag, dip_mult=a.dip_mult,
             bear_book=a.bear_book, dip_cooldown_h=a.dip_cooldown_h, dip_sl_coin=parse_dip_sl_coin(a.dip_sl_coin))
    while True:
        try:
            r.cycle()
        except Exception as e:  # keep the loop alive; resting exchange-native stops / take-profits protect open pieces
            r.log(dict(op="cycle_error", note=repr(e)))
        if a.once:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
