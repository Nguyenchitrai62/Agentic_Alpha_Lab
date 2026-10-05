"""Pure reconciliation logic: merged multi-phase trade plan + exchange state -> order actions (no I/O; tested in tests/test_bot_mirror.py).

Exchange model (Bybit USDT perps, HEDGE mode): longs on positionIdx 1, shorts on positionIdx 2, so a sub-book short and a long dip rung on
the same coin never net. Every logical position is a PIECE in a local ledger (one per sub-book book position, one per filled dip rung); its
exits are separate reduce-only orders owned by the bot:
  book piece : stop = conditional market (touch, plan SL), take-profit = limit (plan TP); both amended when the plan moves them
               (break-even / tighten); plan add / reduce / close orders become limit orders (reduce-only for reduce / close).
  dip piece  : take-profit limit, native backstop = conditional market at the plan backstop, bot stop = market close when a CLOSED 5m bar
               closes at or below the plan stop (close5), time exit = market close at the bar end (research: exit at the next 4h open).
Entries are PostOnly limits (maker only, as the research fill rule); an unfilled entry is cancelled at its expiry and never chased.
Paper and exchange can diverge (a limit the paper filled may not fill on the exchange): the bot follows the EXCHANGE for open pieces and the
PLAN for new orders; when the plan's book position is gone (paper exit) but the exchange piece is still open after GRACE minutes, the piece is
closed at market (logged as a divergence).
Dip risk budget per sub-book (engine rule): sum over open rungs and resting bids of size * (stop distance + 0.02) <= budget * sub capital;
bids are admitted shallow-first, so the resting set never lets simultaneous fills exceed the budget.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

GRACE_MIN = 3
BUDGET, GAP = 0.26, 0.02
ENTRY_DELAY_MIN = 5  # user rule: no new order fills in the first 5 minutes after the 4h close


def t36(ts) -> str:
    """Minute timestamp in base 36 (compact, stable id component)."""
    n = int(pd.Timestamp(ts).timestamp() // 60)
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
    return s or "0"


def book_pid(phase, sym, issued) -> str:
    return f"b{phase}{sym[:-4]}{t36(issued)}"


def dip_pid(phase, sym, rung, bar_start) -> str:
    return f"d{phase}{sym[:-4]}{int(round(float(rung) * 10))}{t36(bar_start)}"


@dataclass
class Order:
    link: str
    symbol: str
    side: str            # "Buy" | "Sell"
    qty: float
    kind: str            # "entry" | "add" | "reduce" | "tp" | "stop"
    price: float | None = None      # limit price
    trigger: float | None = None    # conditional (stop) trigger
    reduce_only: bool = False
    position_idx: int = 1
    piece: str = ""
    meta: dict = field(default_factory=dict)


def _ts(x):
    return pd.Timestamp(x) if x is not None else None


def _pidx(side_sign: int) -> int:
    return 1 if side_sign > 0 else 2


def desired(plan: dict, now, equity: float, ledger: dict, budget: float = BUDGET) -> dict[str, Order]:
    """The order set that should rest on the exchange now (link id -> Order). Quantities are in coins, before exchange rounding."""
    now = pd.Timestamp(now)
    out: dict[str, Order] = {}
    caps = {p["phase"]: float(p.get("capital", 0.25)) for p in plan.get("phases", [])}
    for sym, c in (plan.get("coins") or {}).items():
        for sub in c.get("subs", []):
            ph = sub["phase"]
            o = sub.get("order")
            piece = next((k for k, v in ledger.items() if v["kind"] == "book" and v["phase"] == ph and v["symbol"] == sym and v["qty"] > 0), None)
            if sub.get("state") == "pending" and o and o.get("kind") == "open":
                pid = book_pid(ph, sym, o["issued"])
                ok = _ts(o["issued"]) + pd.Timedelta(minutes=ENTRY_DELAY_MIN) <= now < _ts(o["valid_until"])
                if ok and pid not in ledger:
                    sgn = 1 if o["side"] == "BUY" else -1
                    out[pid + "E"] = Order(pid + "E", sym, "Buy" if sgn > 0 else "Sell", float(o["weight"]) * equity / float(o["price"]),
                                           "entry", price=float(o["price"]), position_idx=_pidx(sgn), piece=pid,
                                           meta=dict(sl=o.get("sl_if_filled"), tp=o.get("tp_if_filled"), phase=ph, kind="book"))
            if piece is None:
                continue
            pc = ledger[piece]
            pos = sub.get("position")
            if not pos and pc.get("sl") and pc.get("tp"):  # filled before the plan saw it: protect with the entry's attached levels
                pos = {"sl": pc["sl"], "tp": pc["tp"]}
            if pos:  # exits of the open book piece follow the plan's current SL / TP
                pc_side = "Sell" if pc["side"] > 0 else "Buy"
                out[piece + "S"] = Order(piece + "S", sym, pc_side, pc["qty"], "stop", trigger=float(pos["sl"]), reduce_only=True,
                                         position_idx=_pidx(pc["side"]), piece=piece)
                out[piece + "T"] = Order(piece + "T", sym, pc_side, pc["qty"], "tp", price=float(pos["tp"]), reduce_only=True,
                                         position_idx=_pidx(pc["side"]), piece=piece)
                if o and o.get("kind") in ("add", "reduce", "close") and now < _ts(o["valid_until"]):
                    tag = f"{piece}{o['kind'][0].upper()}{t36(o['valid_until'])}"
                    if o["kind"] == "add":
                        out[tag] = Order(tag, sym, "Buy" if pc["side"] > 0 else "Sell", float(o["amount"]) * equity / float(o["price"]), "add",
                                         price=float(o["price"]), position_idx=_pidx(pc["side"]), piece=piece)
                    else:
                        q = pc["qty"] if o["kind"] == "close" else pc["qty"] * min(1.0, float(o["amount"]))
                        out[tag] = Order(tag, sym, pc_side, q, "reduce", price=float(o["price"]), reduce_only=True,
                                         position_idx=_pidx(pc["side"]), piece=piece)
        # dip pieces already open: take-profit + native backstop (the 5m-close stop and the time exit are bot actions, see exits())
        for pid, pc in ledger.items():
            if pc["kind"] == "dip" and pc["symbol"] == sym and pc["qty"] > 0:
                out[pid + "T"] = Order(pid + "T", sym, "Sell", pc["qty"], "tp", price=pc["tp"], reduce_only=True, position_idx=1, piece=pid)
                if pc.get("backstop"):
                    out[pid + "S"] = Order(pid + "S", sym, "Sell", pc["qty"], "stop", trigger=pc["backstop"], reduce_only=True,
                                           position_idx=1, piece=pid)
    # dip bids: admitted shallow-first inside each sub-book's risk budget (open rungs count first)
    used = {ph: 0.0 for ph in caps}
    for pc in ledger.values():
        if pc["kind"] == "dip" and pc["qty"] > 0:
            used[pc["phase"]] = used.get(pc["phase"], 0.0) + pc["frac"] * (pc["dist"] + GAP)
    bids = []
    for sym, c in (plan.get("coins") or {}).items():
        for d in c.get("dips", []):
            a0, a1 = _ts(d["active_from"]), _ts(d["active_until"])
            if not (a0 <= now < a1 + pd.Timedelta(minutes=1)):  # the paper 'filled' flag is ignored: the exchange ledger is the truth
                continue
            bar = a0 - pd.Timedelta(minutes=16)
            pid = dip_pid(d["phase"], sym, d["rung"], bar)
            if pid in ledger:
                continue
            bids.append((float(d["rung"]), d["phase"], sym, pid, d, bar))
    for rung, ph, sym, pid, d, bar in sorted(bids, key=lambda b: (b[0], b[1], b[2])):
        frac, lv = float(d["size_frac"]), float(d["buy_limit"])
        dist = (lv - float(d["stop"])) / lv
        cost = frac * (dist + GAP)
        if used.get(ph, 0.0) + cost > budget * caps.get(ph, 0.25) + 1e-12:
            continue
        used[ph] = used.get(ph, 0.0) + cost
        out[pid + "E"] = Order(pid + "E", sym, "Buy", frac * equity / lv, "entry", price=lv, position_idx=1, piece=pid,
                               meta=dict(kind="dip", phase=ph, tp=float(d["tp"]), stop=float(d["stop"]), backstop=d.get("backstop"),
                                         t_exit=str(bar + pd.Timedelta(hours=4)), frac=frac, dist=dist))
    return out


def plan_book_live(plan: dict) -> set:
    """(phase, symbol) whose sub-book still holds or awaits a book position in the plan (a pending entry may already have filled on the
    exchange before the hourly plan refresh, so it is not a divergence)."""
    return {(sub["phase"], sym) for sym, c in (plan.get("coins") or {}).items() for sub in c.get("subs", [])
            if sub.get("position") or sub.get("state") == "pending"}


def exits(plan: dict, now, ledger: dict, last5: dict) -> list[tuple[str, str]]:
    """Bot market exits now: [(piece id, reason)]. last5: symbol -> (close time of the last CLOSED 5m bar, close price)."""
    now = pd.Timestamp(now)
    out = []
    book_live = plan_book_live(plan)
    for pid, pc in ledger.items():
        if pc["qty"] <= 0:
            continue
        if pc["kind"] == "dip":
            cl = last5.get(pc["symbol"])
            if pc.get("stop5") and cl is not None and pd.Timestamp(cl[0]) > pd.Timestamp(pc["opened"]) and float(cl[1]) <= pc["stop5"]:
                out.append((pid, "close5_stop"))
            elif now >= pd.Timestamp(pc["t_exit"]):
                out.append((pid, "time_exit"))
        elif pc["kind"] == "book" and (pc["phase"], pc["symbol"]) not in book_live:
            if now >= pd.Timestamp(pc.get("plan_gone_since") or now) + pd.Timedelta(minutes=GRACE_MIN):
                out.append((pid, "plan_closed_divergence"))
    return out


def diff(want: dict[str, Order], have: dict[str, dict], rel_tol: float = 1e-6) -> list[dict]:
    """Actions turning the resting set `have` (link -> {price, trigger, qty}) into `want`. Bot-owned links only."""
    acts = []
    for link, h in have.items():
        if link not in want:
            acts.append(dict(op="cancel", link=link, symbol=h["symbol"]))
    for link, o in want.items():
        h = have.get(link)
        if h is None:
            acts.append(dict(op="place", order=o))
            continue
        ch = {}
        if o.price is not None and abs(float(h.get("price") or 0) - o.price) > rel_tol * o.price:
            ch["price"] = o.price
        if o.trigger is not None and abs(float(h.get("trigger") or 0) - o.trigger) > rel_tol * o.trigger:
            ch["trigger"] = o.trigger
        if abs(float(h.get("qty") or 0) - o.qty) > max(rel_tol * o.qty, 1e-12) and o.kind in ("tp", "stop"):
            ch["qty"] = o.qty
        if ch:
            acts.append(dict(op="amend", link=link, symbol=o.symbol, **ch))
    return acts


def apply_fill(ledger: dict, order: Order, qty: float, price: float, t) -> None:
    """Book a fill of a bot order into the piece ledger (entry / add extend a piece; reduce / tp / stop shrink it)."""
    pid = order.piece
    if order.kind == "entry":
        m = order.meta
        pc = ledger.setdefault(pid, dict(symbol=order.symbol, side=1 if order.side == "Buy" else -1, qty=0.0, entry=price, kind=m["kind"],
                                         phase=m["phase"], opened=str(pd.Timestamp(t))))
        tot = pc["qty"] + qty
        pc["entry"] = (pc["entry"] * pc["qty"] + price * qty) / tot if tot > 0 else price
        pc["qty"] = tot
        if m["kind"] == "book":
            pc.update(sl=m.get("sl"), tp=m.get("tp"))
        if m["kind"] == "dip":
            pc.update(tp=m["tp"], stop5=m["stop"], backstop=m.get("backstop"), t_exit=m["t_exit"], frac=m["frac"], dist=m["dist"])
    elif order.kind == "add" and pid in ledger:
        pc = ledger[pid]
        tot = pc["qty"] + qty
        pc["entry"] = (pc["entry"] * pc["qty"] + price * qty) / tot
        pc["qty"] = tot
    elif pid in ledger:
        ledger[pid]["qty"] = max(0.0, ledger[pid]["qty"] - qty)
