"""Order-mirror bot runner: follow a merged paper trade plan on Bybit USDT perps (hedge mode).

  .venv/Scripts/python.exe -m bot.run --once                       dry run: prints what would be placed / cancelled now (no keys needed)
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
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from bot import mirror
from bot.bybit_v5 import MAINNET, TESTNET, Bybit, BybitError, round_step

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "artifacts/research/advisor_shadow/trade_plan_v376.json"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
STALE_PLAN = pd.Timedelta(hours=2)


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
    p.update(orderType="Limit", price=price, timeInForce="PostOnly" if o.kind in ("entry", "add") else "GTC")
    if o.reduce_only:
        p["reduceOnly"] = True
    return p


class Runner:
    def __init__(self, mode: str, plan_path: Path, equity: float | None):
        self.mode, self.plan_path = mode, plan_path
        self.dir = ROOT / "artifacts/bot" / mode
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_f = self.dir / "state.json"
        self.state = json.loads(self.state_f.read_text()) if self.state_f.exists() else dict(ledger={}, links={}, last_exec_ms=None)
        if mode == "dry":
            self.ex = Bybit(base=MAINNET)  # public data only
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
        start = self.state.get("last_exec_ms") or int((time.time() - 3600) * 1000)
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

    def cycle(self):
        now = pd.Timestamp.now(tz="UTC")
        plan = json.loads(self.plan_path.read_text())
        stale = now - pd.Timestamp(plan["generated_at"]) > STALE_PLAN
        equity = self.equity_arg if self.mode == "dry" else self.ex.equity_usdt()
        self.sync_fills()
        led = self.state["ledger"]
        live = {(sub["phase"], sym) for sym, c in plan["coins"].items() for sub in c.get("subs", []) if sub.get("position")}
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
        want = mirror.desired(plan, now, equity, led)
        if stale:
            want = {k: o for k, o in want.items() if o.kind in ("tp", "stop", "reduce")}
            self.log(dict(op="stale_plan", generated_at=plan["generated_at"]))
        rounded, skipped = {}, []
        for k, o in want.items():
            p = to_exchange(o, self.inst)
            if p is None:
                skipped.append(k)
            else:
                rounded[k] = (o, p)
        acts = mirror.diff({k: o for k, (o, _) in rounded.items()}, self.have())
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
        return acts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("dry", "testnet", "live"), default="dry")
    ap.add_argument("--plan", default=str(PLAN))
    ap.add_argument("--equity", type=float, default=1000.0, help="dry run only: account equity in USDT")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=20.0)
    a = ap.parse_args()
    if a.mode == "live" and os.environ.get("BOT_ALLOW_LIVE") != "yes-real-money":
        sys.exit("live trading is locked: the account owner must set BOT_ALLOW_LIVE=yes-real-money")
    r = Runner(a.mode, Path(a.plan), a.equity)
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
