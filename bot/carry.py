"""Cash-and-carry sleeve for the BOT (bot_carry assignment).

Uses the SAME frozen rule as scripts/carry_paper.py: imports RULE_PARAMS and
is_quarterly_delivery (never re-defined) plus the frozen helpers
annualised_basis / pick_candidate / realised_pnl_pair / MS_DAY.

Rule per coin (BTC, ETH): flat + roll due (no open pair and front quarterly
has <= 7 d left, or first availability) + annualised basis ln(F/S)*365/DTE >=
4 %/yr -> spot BUY + quarterly SELL, each leg notional = f x equity, equal
coin quantity. Hold to delivery; after delivery sell the spot leg at market
(plus a safety futures buy-back for sim accounts where dated shorts do not
auto-settle) and log realised P&L. Single-fill opens are retried at market
next cycle (op=carry_unhedged); never left unhedged > 2 cycles, otherwise the
filled leg is closed.

All carry orders use bot-owned link ids with prefix ``c`` and pass through
risk_guard (plus a carry cap: short notional <= 0.30 x equity per coin). They
are never counted in the dip gross cap (added after mirror.desired).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.carry_paper import (  # noqa: E402  (frozen rule: import, do not re-define)
    MS_DAY,
    RULE_PARAMS,
    annualised_basis,
    is_quarterly_delivery,
    pick_candidate,
    realised_pnl_pair,
)

from bot import mirror  # noqa: E402
from bot import risk_guard  # noqa: E402

LINK_PREFIX = "c"
MAX_UNHEDGED_CYCLES = 2
CARRY_SHORT_CAP = 0.30  # carry short notional <= 0.30 x equity per coin


def spot_symbol(coin: str) -> str:
    return f"{str(coin).upper()}USDT"


def _now_ms(now) -> int:
    import pandas as pd

    return int(pd.Timestamp(now).timestamp() * 1000)


def carry_state(state: dict) -> dict:
    """Return (creating) the carry sub-state inside Runner.state."""
    try:
        c = state.get("carry")
    except AttributeError:
        return {"positions": {}, "entered": [], "history": []}
    if not isinstance(c, dict):
        c = {"positions": {}, "entered": [], "history": []}
        try:
            state["carry"] = c
        except (TypeError, AttributeError):
            return c
    c.setdefault("positions", {})
    c.setdefault("entered", [])
    c.setdefault("history", [])
    return c


def has_history(cstate: dict, coin: str) -> bool:
    try:
        if coin in (cstate.get("positions") or {}):
            return True
        for h in cstate.get("history") or []:
            if isinstance(h, dict) and h.get("coin") == coin:
                return True
        for s in cstate.get("entered") or []:
            if str(s).startswith(str(coin) + ":") or str(s) == str(coin):
                return True
    except (AttributeError, TypeError):
        pass
    return False


def roll_candidate(expiries: list, now_ms: int, hist: bool):
    """Frozen roll rule: front <= 7 d -> NEXT quarterly, else front only at first availability."""
    try:
        return pick_candidate(list(expiries or []), int(now_ms), bool(hist))
    except (TypeError, ValueError):
        return None


def qty_for(f: float, equity: float, ref_px: float) -> float:
    eq = float(equity)
    px = float(ref_px)
    if not (eq > 0 and px > 0 and f > 0):
        return 0.0
    return float(f) * eq / px


def _links(coin: str, now) -> tuple[str, str]:
    base = f"{LINK_PREFIX}{str(coin).upper()}{mirror.t36(now)}"
    return base + "S", base + "F"


def entry_payloads(coin, cand, spot_ask, fut_bid, qty, now) -> tuple[dict, dict]:
    """Spot BUY limit at the ask (IOC, category spot) + quarterly SELL limit at
    the bid (IOC, category as listed). Equal coin quantity, each leg ~f x equity."""
    s_link, f_link = _links(coin, now)
    spot = dict(symbol=spot_symbol(coin), side="Buy", qty=str(qty),
                orderType="Limit", price=str(spot_ask), timeInForce="IOC",
                orderLinkId=s_link, category="spot")
    fut = dict(symbol=cand["symbol"], side="Sell", qty=str(qty),
               orderType="Limit", price=str(fut_bid), timeInForce="IOC",
               orderLinkId=f_link, category=cand.get("category", "linear"),
               positionIdx=2)
    return spot, fut


def market_payload(symbol, side, qty, link, category, reduce_only=False, position_idx=None) -> dict:
    p = dict(symbol=symbol, side=side, qty=str(qty), orderType="Market",
             orderLinkId=link, category=category)
    if reduce_only:
        p["reduceOnly"] = True
    if position_idx is not None:
        p["positionIdx"] = int(position_idx)
    return p


def carry_cap_ok(qty: float, fut_px: float, equity: float) -> bool:
    try:
        return float(qty) * float(fut_px) <= float(CARRY_SHORT_CAP) * float(equity) + 1e-9
    except (TypeError, ValueError):
        return False


def guard_carry(orders: list, ledger, equity: float, prices: dict):
    """Pass carry orders through risk_guard.check with an extended allowlist
    (dated futures symbols are not in the default majors list), then enforce
    the carry cap: futures short notional <= 0.30 x equity per coin.

    Returns (allowed, rejected). Rejected entries: {link, symbol, reason}.
    """
    try:
        eq = float(equity)
    except (TypeError, ValueError):
        eq = 0.0
    syms = set()
    conv = []
    for o in orders or []:
        try:
            sym = o.get("symbol") if isinstance(o, dict) else getattr(o, "symbol", None)
        except Exception:
            sym = None
        if sym:
            syms.add(sym)
        if isinstance(o, dict):
            is_exit = bool(o.get("reduceOnly"))
            kind = "reduce" if is_exit else "entry"
            try:
                px = float(o.get("price")) if o.get("price") is not None else None
            except (TypeError, ValueError):
                px = None
            try:
                q = abs(float(o.get("qty", 0)))
            except (TypeError, ValueError):
                q = 0.0
            conv.append(mirror.Order(str(o.get("orderLinkId", "")), sym,
                                     str(o.get("side", "Buy")), q, kind,
                                     price=px, reduce_only=is_exit,
                                     meta=dict(kind="carry")))
        else:
            conv.append(o)
    try:
        allowed_syms = tuple(risk_guard.ALLOWED_SYMBOLS) + tuple(sorted(syms))
    except Exception:
        allowed_syms = None
    try:
        allowed_o, rejected = risk_guard.check(conv, ledger, eq, dict(prices or {}),
                                               limits=dict(allowed_symbols=allowed_syms) if allowed_syms else None)
    except Exception:
        return [], [dict(link=getattr(o, "link", "?"), symbol=getattr(o, "symbol", None),
                          reason="guard_error") for o in conv]
    keep = {id(o) for o in (allowed_o or [])}
    allowed, rej = [], list(rejected or [])
    raw = list(orders or [])
    for o, c in zip(raw, conv):
        if id(c) not in keep:
            continue
        try:
            is_short_open = (not bool(c.reduce_only)) and str(c.side).lower().startswith("sell")
        except Exception:
            is_short_open = False
        if is_short_open:
            try:
                px = float(c.price) if c.price is not None else float((prices or {}).get(c.symbol, 0) or 0)
            except (TypeError, ValueError):
                px = 0.0
            if not carry_cap_ok(c.qty, px, eq):
                link = o.get("orderLinkId") if isinstance(o, dict) else getattr(o, "link", "?")
                rej.append(dict(link=link, symbol=c.symbol, reason="carry_cap"))
                continue
        allowed.append(o)
    return allowed, rej


def _pos_open(pos: dict) -> bool:
    return bool(pos.get("spot_filled")) and bool(pos.get("fut_filled"))


def decide(now, equity: float, f: float, cstate: dict, expiries_by_coin: dict,
           quotes_by_coin: dict) -> tuple[list, list]:
    """Pure carry decision for one cycle.

    expiries_by_coin: {coin: [{symbol, category, delivery_ms}, ...]}.
    quotes_by_coin: {coin: {spot_ask, spot_bid, spot_mid,
      fut_by_sym: {fut_sym: {bid, ask, mid}}}}; missing quotes -> no entry.

    Returns (want_payloads, logs). want_payloads are raw exchange payloads
    (with category + orderLinkId prefix ``c``). logs are dicts with op in
    {carry_entry, carry_unhedged, carry_close, carry_settle, carry_skip,
    carry_cap} for the runner to emit. cstate is mutated (positions/entered).
    """
    import pandas as pd

    now = pd.Timestamp(now)
    now_ms = _now_ms(now)
    try:
        f = float(f)
    except (TypeError, ValueError):
        f = 0.0
    want, logs = [], []
    if not (f > 0):
        return want, logs
    positions = cstate.setdefault("positions", {})
    for coin in list(RULE_PARAMS.get("coins", []) or []):
        pos = positions.get(coin)
        if isinstance(pos, dict):
            dlv = int(pos.get("delivery_ms", 0) or 0)
            if dlv and now_ms >= dlv and _pos_open(pos) and not pos.get("settling"):
                qty = float(pos.get("qty", 0) or 0)
                if qty > 0:
                    s_link = f"{LINK_PREFIX}{coin}X{mirror.t36(now)}S"
                    f_link = f"{LINK_PREFIX}{coin}X{mirror.t36(now)}F"
                    want.append(market_payload(pos.get("spot_symbol", spot_symbol(coin)),
                                               "Sell", qty, s_link, "spot"))
                    want.append(market_payload(pos.get("symbol"), "Buy", qty, f_link,
                                               pos.get("category", "linear"),
                                               reduce_only=True, position_idx=2))
                    pos["settling"] = True
                    pos["spot_sale_link"] = s_link
                    pos["fut_close_link"] = f_link
                    try:
                        s_del = float((quotes_by_coin.get(coin) or {}).get("spot_mid") or pos.get("S_entry") or 0)
                        pnl, ret = realised_pnl_pair(float(pos.get("f", f)),
                                                     float(pos.get("equity_entry", equity)),
                                                     float(pos.get("S_entry", 0)),
                                                     float(pos.get("F_entry", 0)),
                                                     float(s_del))
                    except (TypeError, ValueError):
                        pnl, ret = 0.0, 0.0
                    logs.append(dict(op="carry_settle", coin=coin, symbol=pos.get("symbol"),
                                     S_del=float(s_del) if s_del else None,
                                     realised_pnl=round(float(pnl), 4),
                                     ret_alloc=round(float(ret), 6)))
                continue
            if pos.get("settling"):
                continue
            sf, ff = bool(pos.get("spot_filled")), bool(pos.get("fut_filled"))
            if sf and ff:
                continue
            if sf != ff:
                try:
                    n = int(pos.get("unhedged_cycles", 0) or 0) + 1
                except (TypeError, ValueError):
                    n = 1
                pos["unhedged_cycles"] = n
                qty = float(pos.get("qty", 0) or 0)
                if n > MAX_UNHEDGED_CYCLES:
                    if sf:
                        link = f"{LINK_PREFIX}{coin}U{mirror.t36(now)}S"
                        want.append(market_payload(pos.get("spot_symbol", spot_symbol(coin)),
                                                   "Sell", qty, link, "spot"))
                    else:
                        link = f"{LINK_PREFIX}{coin}U{mirror.t36(now)}F"
                        want.append(market_payload(pos.get("symbol"), "Buy", qty, link,
                                                   pos.get("category", "linear"),
                                                   reduce_only=True, position_idx=2))
                    logs.append(dict(op="carry_close", coin=coin, symbol=pos.get("symbol"),
                                     reason="unhedged_timeout", cycles=n))
                    continue
                if sf:
                    link = f"{LINK_PREFIX}{coin}H{mirror.t36(now)}F"
                    want.append(market_payload(pos.get("symbol"), "Sell", qty, link,
                                               pos.get("category", "linear"),
                                               position_idx=2))
                    logs.append(dict(op="carry_unhedged", coin=coin, symbol=pos.get("symbol"),
                                     missing="fut", cycles=n))
                else:
                    link = f"{LINK_PREFIX}{coin}H{mirror.t36(now)}S"
                    want.append(market_payload(pos.get("spot_symbol", spot_symbol(coin)),
                                               "Buy", qty, link, "spot"))
                    logs.append(dict(op="carry_unhedged", coin=coin, symbol=pos.get("symbol"),
                                     missing="spot", cycles=n))
                continue
            continue
        expiries = list((expiries_by_coin or {}).get(coin, []) or [])
        cand = roll_candidate(expiries, now_ms, has_history(cstate, coin))
        if cand is None:
            continue
        q = (quotes_by_coin or {}).get(coin) or {}
        try:
            fut_q = (q.get("fut_by_sym") or {}).get(cand["symbol"]) or {}
            s_ask = float(q.get("spot_ask") or q.get("spot_mid") or 0)
            f_bid = float(fut_q.get("bid") or fut_q.get("mid") or 0)
            s_mid = float(q.get("spot_mid") or s_ask)
            f_mid = float(fut_q.get("mid") or f_bid)
        except (TypeError, ValueError, AttributeError, KeyError):
            continue
        if not (s_mid > 0 and f_mid > 0 and s_ask > 0 and f_bid > 0):
            continue
        dte = (int(cand["delivery_ms"]) - now_ms) / MS_DAY
        try:
            basis = annualised_basis(float(f_mid), float(s_mid), float(dte))
        except (TypeError, ValueError):
            continue
        if basis < float(RULE_PARAMS.get("basis_threshold", 0.04)):
            logs.append(dict(op="carry_skip", coin=coin, symbol=cand["symbol"],
                             ann_basis=round(float(basis), 6)))
            continue
        qty = qty_for(f, equity, s_ask)
        if not (qty > 0):
            continue
        if not carry_cap_ok(qty, f_bid, equity):
            logs.append(dict(op="carry_cap", coin=coin, symbol=cand["symbol"],
                             reason="carry_cap"))
            continue
        spot_p, fut_p = entry_payloads(coin, cand, s_ask, f_bid, qty, now)
        want.extend([spot_p, fut_p])
        positions[coin] = dict(coin=coin, symbol=cand["symbol"],
                               category=cand.get("category", "linear"),
                               spot_symbol=spot_symbol(coin),
                               S_entry=float(s_mid), F_entry=float(f_mid),
                               S_ask=float(s_ask), F_bid=float(f_bid),
                               qty=float(qty), equity_entry=float(equity), f=float(f),
                               delivery_ms=int(cand["delivery_ms"]),
                               entry_time=str(now),
                               spot_filled=False, fut_filled=False,
                               S_fill=None, F_fill=None,
                               spot_link=spot_p["orderLinkId"], fut_link=fut_p["orderLinkId"],
                               unhedged_cycles=0, ann_basis=round(float(basis), 6),
                               dte_days=round(float(dte), 2))
        logs.append(dict(op="carry_entry", coin=coin, symbol=cand["symbol"],
                         category=cand.get("category", "linear"),
                         S_entry=float(s_mid), F_entry=float(f_mid),
                         ann_basis=round(float(basis), 6),
                         dte_days=round(float(dte), 2),
                         qty=float(qty)))
    return want, logs


def note_exec(cstate: dict, link: str, qty: float, price: float):
    """Record a fill of a carry link (prefix ``c``) into the carry state."""
    if not str(link or "").startswith(LINK_PREFIX):
        return None
    positions = (cstate or {}).get("positions") or {}
    for coin, pos in list(positions.items()):
        if not isinstance(pos, dict):
            continue
        try:
            q = float(qty)
            px = float(price)
        except (TypeError, ValueError):
            return None
        if link == pos.get("spot_sale_link"):
            try:
                pnl, ret = realised_pnl_pair(float(pos.get("f", 0)),
                                             float(pos.get("equity_entry", 0)),
                                             float(pos.get("S_entry", 0) or pos.get("S_fill", 0)),
                                             float(pos.get("F_entry", 0) or pos.get("F_fill", 0)),
                                             float(px))
            except (TypeError, ValueError):
                pnl, ret = 0.0, 0.0
            rec = dict(pos)
            rec.update(status="delivered", S_del=float(px),
                       realised_pnl=round(float(pnl), 4),
                       realised_ret_alloc=round(float(ret), 6))
            cstate.setdefault("history", []).append(rec)
            ent = f"{coin}:{pos.get('symbol')}"
            if ent not in cstate.setdefault("entered", []):
                cstate["entered"].append(ent)
            positions.pop(coin, None)
            return dict(op="carry_settled", coin=coin, symbol=pos.get("symbol"),
                        S_del=float(px), realised_pnl=round(float(pnl), 4))
        if link == pos.get("spot_link"):
            if not pos.get("spot_filled"):
                pos["spot_filled"] = True
                pos["S_fill"] = px
                if not pos.get("S_entry"):
                    pos["S_entry"] = px
                return dict(op="carry_fill", coin=coin, symbol=pos.get("spot_symbol"),
                            leg="spot", price=float(px))
            continue
        if link == pos.get("fut_link"):
            if not pos.get("fut_filled"):
                pos["fut_filled"] = True
                pos["F_fill"] = px
                if not pos.get("F_entry"):
                    pos["F_entry"] = px
                ent = f"{coin}:{pos.get('symbol')}"
                if ent not in cstate.setdefault("entered", []):
                    cstate["entered"].append(ent)
                if _pos_open(pos):
                    pos["unhedged_cycles"] = 0
                return dict(op="carry_fill", coin=coin, symbol=pos.get("symbol"),
                            leg="fut", price=float(px))
            continue
        if str(link).startswith(f"{LINK_PREFIX}{coin}") and str(link).endswith("S"):
            if not pos.get("spot_filled"):
                pos["spot_filled"] = True
                pos["S_fill"] = px
                if _pos_open(pos):
                    pos["unhedged_cycles"] = 0
                return dict(op="carry_fill", coin=coin, symbol=pos.get("spot_symbol"),
                            leg="spot", price=float(px))
            continue
        if str(link).startswith(f"{LINK_PREFIX}{coin}") and str(link).endswith("F"):
            if not pos.get("fut_filled"):
                pos["fut_filled"] = True
                pos["F_fill"] = px
                if _pos_open(pos):
                    pos["unhedged_cycles"] = 0
                ent = f"{coin}:{pos.get('symbol')}"
                if ent not in cstate.setdefault("entered", []):
                    cstate["entered"].append(ent)
                return dict(op="carry_fill", coin=coin, symbol=pos.get("symbol"),
                            leg="fut", price=float(px))
            continue
    return None


def fetch_contracts(public_client) -> dict:
    """{coin: [{symbol, category, delivery_ms}]} for quarterly dated futures."""
    try:
        from scripts.carry_paper import fetch_dated_contracts
    except Exception:
        return {}
    try:
        contracts = fetch_dated_contracts(public_client)
    except Exception:
        return {}
    out = {}
    for c in contracts or []:
        try:
            if not is_quarterly_delivery(int(c.get("delivery_ms", 0))):
                continue
            out.setdefault(str(c.get("coin", "")).upper(), []).append(
                dict(symbol=str(c.get("symbol")), category=str(c.get("category", "linear")),
                     delivery_ms=int(c.get("delivery_ms"))))
        except (TypeError, ValueError, AttributeError):
            continue
    for v in out.values():
        v.sort(key=lambda e: int(e["delivery_ms"]))
    return out


def fetch_quotes(public_client, contracts_by_coin: dict) -> dict:
    """Best-effort mids/bids/asks: {coin: {spot_mid/ask/bid, fut_by_sym: ...}}."""
    out = {}
    for coin, contracts in (contracts_by_coin or {}).items():
        entry = dict(spot_mid=None, spot_ask=None, spot_bid=None, fut_by_sym={})
        try:
            from scripts.carry_paper import fetch_mid
        except Exception:
            out[coin] = entry
            continue
        try:
            s_mid, s_row = fetch_mid(public_client, "spot", spot_symbol(coin))
        except Exception:
            s_mid, s_row = None, None
        try:
            entry["spot_mid"] = float(s_mid) if s_mid else None
            if isinstance(s_row, dict):
                try:
                    entry["spot_ask"] = float(s_row.get("ask1Price") or 0) or entry["spot_mid"]
                except (TypeError, ValueError):
                    entry["spot_ask"] = entry["spot_mid"]
                try:
                    entry["spot_bid"] = float(s_row.get("bid1Price") or 0) or entry["spot_mid"]
                except (TypeError, ValueError):
                    entry["spot_bid"] = entry["spot_mid"]
            else:
                entry["spot_ask"] = entry["spot_bid"] = entry["spot_mid"]
        except (TypeError, ValueError):
            pass
        for c in contracts or []:
            try:
                f_mid, f_row = fetch_mid(public_client, c.get("category", "linear"), c.get("symbol"))
            except Exception:
                continue
            try:
                fq = dict(mid=float(f_mid) if f_mid else None, bid=None, ask=None)
                if isinstance(f_row, dict):
                    try:
                        fq["ask"] = float(f_row.get("ask1Price") or 0) or fq["mid"]
                    except (TypeError, ValueError):
                        fq["ask"] = fq["mid"]
                    try:
                        fq["bid"] = float(f_row.get("bid1Price") or 0) or fq["mid"]
                    except (TypeError, ValueError):
                        fq["bid"] = fq["mid"]
                else:
                    fq["ask"] = fq["bid"] = fq["mid"]
                entry["fut_by_sym"][c.get("symbol")] = fq
            except (TypeError, ValueError):
                continue
        out[coin] = entry
    return out
