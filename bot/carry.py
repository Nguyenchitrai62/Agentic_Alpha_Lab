"""Cash-and-carry sleeve for the BOT (bot_carry assignment).

Uses the SAME frozen rule as scripts/carry_paper.py: imports RULE_PARAMS and
is_quarterly_delivery (never re-defined) plus the frozen helpers
annualised_basis / pick_candidate / realised_pnl_pair / MS_DAY.

Rule per coin (BTC, ETH): flat + roll due (no open pair and front quarterly
has <= 7 d left, or first availability) + annualised basis ln(F/S)*365/DTE >=
4 %/yr -> spot BUY + quarterly SELL, each leg notional = f x equity, equal
coin quantity. Hold to delivery; from delivery_ms - 30 min the filled spot
qty is sold in 6 equal slices (one per 5-minute bucket at the first cycle
inside each bucket, market IOC on spot, rounded to the spot lot, last slice
= exact remainder, op=carry_slice, restart-safe via the persisted position
state); after delivery the futures leg is settled as before and any unsold
spot remainder is sold at market (fallback, logged). Single-fill opens are
retried at market next cycle (op=carry_unhedged); never left unhedged
> 2 cycles, otherwise the filled leg is closed.

All carry orders use bot-owned link ids with prefix ``c`` and pass through
risk_guard (plus a carry cap: short notional <= 0.30 x equity per coin). They
are never counted in the dip gross cap (added after mirror.desired).

Qty handling (bot_carryqty fix, paper_d17bfg2c 2026-10-06): the pair qty is
floored to the coarser of the spot / future qty steps BEFORE placing (both
legs identical) and stored; fills record the actual filled qty per leg
(``spot_qty_filled`` / ``fut_qty_filled``) and hedge recovery + delivery
settlement size from those. A rounded qty of 0 or below minimum notional
logs carry_skip with reason=min_qty.
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
MAX_ENTRY_ATTEMPTS = 3  # a pending pair with NEITHER leg filled is retried at
# fresh prices up to 3 attempts per roll, then carry_abandon (re-evaluated next cycle)
CARRY_SHORT_CAP = 0.30  # carry short notional <= 0.30 x equity per coin

# bot_carryslice (2026-10-06): sliced spot exit across the settlement index
# window (oc_deliverytrack: 6 slices 07:30-08:00 cuts exit noise 29->6bp,
# worst miss 92->20bp). Delivery at 08:00 UTC; the index averages the window,
# so the spot leg is sold in 6 equal slices, one per 5-minute bucket.
SLICE_WINDOW_MS = 30 * 60 * 1000
SLICE_N = 6
SLICE_BUCKET_MS = 5 * 60 * 1000
SLICE_DUST = 1e-12
SETTLE_GRACE_MS = 60 * 60 * 1000  # zero-remainder settling finalises w/o fut fill after this


def _slice_bucket(now_ms: int, delivery_ms: int):
    """5-minute bucket 0..5 inside [delivery-30min, delivery), else None."""
    try:
        start = int(delivery_ms) - SLICE_WINDOW_MS
        n = int(now_ms)
        d = int(delivery_ms)
    except (TypeError, ValueError):
        return None
    if n < start or n >= d:
        return None
    b = (n - start) // SLICE_BUCKET_MS
    try:
        b = int(b)
    except (TypeError, ValueError):
        return None
    if 0 <= b < SLICE_N:
        return b
    return None


def _floor_to_step(qty: float, step) -> float:
    """Floor qty to one qty step (spot lot for slices); None step -> raw qty."""
    from decimal import ROUND_DOWN, Decimal, InvalidOperation

    try:
        q = Decimal(str(qty))
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return 0.0
    if q <= 0:
        return 0.0
    if step is None:
        return float(q)
    try:
        st = Decimal(str(step))
        if st <= 0:
            return float(q)
        return float((q / st).to_integral_value(rounding=ROUND_DOWN) * st)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return float(q)


def _spot_step_for(coin: str, fut_symbol, lots):
    """Spot qty_step for slice rounding, or None (raw sizing, runner floors)."""
    try:
        s_lot, _f_lot = _lots_for(coin, fut_symbol, lots)
    except Exception:
        return None
    try:
        return (s_lot or {}).get("qty_step")
    except (AttributeError, TypeError):
        return None


def _slice_sold(pos: dict) -> float:
    try:
        return float(pos.get("spot_slice_sold_qty", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _slice_proceeds(pos: dict) -> float:
    try:
        return float(pos.get("spot_slice_proceeds", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _slice_vwap(pos: dict):
    sold = _slice_sold(pos)
    if sold > SLICE_DUST:
        try:
            return float(_slice_proceeds(pos) / sold)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return None


def _acc_slice_fill(pos: dict, qty: float, price: float) -> float:
    """Accumulate a spot-sale (slice or remainder) fill; returns total sold."""
    try:
        q = float(qty)
        px = float(price)
    except (TypeError, ValueError):
        return _slice_sold(pos)
    if not (q > 0 and px > 0):
        return _slice_sold(pos)
    pos["spot_slice_sold_qty"] = _slice_sold(pos) + q
    pos["spot_slice_proceeds"] = _slice_proceeds(pos) + q * px
    return float(pos["spot_slice_sold_qty"])


def _settle_pnl(pos: dict, f: float, s_del: float):
    try:
        pnl, ret = realised_pnl_pair(float(pos.get("f", f)),
                                     float(pos.get("equity_entry", 0)),
                                     float(pos.get("S_entry", 0) or pos.get("S_fill", 0)),
                                     float(pos.get("F_entry", 0) or pos.get("F_fill", 0)),
                                     float(s_del))
    except (TypeError, ValueError):
        pnl, ret = 0.0, 0.0
    return float(pnl), float(ret)


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


def _skip_hour_key(coin: str, now) -> str:
    """Dedupe key for carry_skip: one log per coin per UTC hour."""
    import pandas as pd

    try:
        ts = pd.Timestamp(now)
    except (TypeError, ValueError):
        return f"{coin}:{now}"
    try:
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC")
        h = ts.floor("h")
    except (TypeError, ValueError, AttributeError):
        h = ts
    return f"{coin}:{h}"


def _skip_already(cstate: dict, key: str) -> bool:
    """True when this (coin, hour) skip was already logged; else record it."""
    try:
        seen = cstate.setdefault("skip_logged", {})
    except (AttributeError, TypeError):
        return False
    if not isinstance(seen, dict):
        return False
    if key in seen:
        return True
    seen[key] = True
    if len(seen) > 240:  # bound memory: keep the current hour's keys
        cur_h = key.split(":", 1)[-1] if ":" in key else ""
        for k in list(seen):
            if cur_h and k.endswith(cur_h):
                continue
            del seen[k]
            if len(seen) <= 48:
                break
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


def _coarser_step(spot_step, fut_step):
    """Coarser (larger) of two qty steps as a string, or None when neither is usable."""
    from decimal import Decimal, InvalidOperation

    def _dec(x):
        try:
            d = Decimal(str(x))
        except (InvalidOperation, ValueError, TypeError, AttributeError):
            return None
        return d if d > 0 else None

    ds, df = _dec(spot_step), _dec(fut_step)
    if ds is None:
        return None if df is None else str(fut_step)
    if df is None:
        return str(spot_step)
    return str(spot_step) if ds >= df else str(fut_step)


def round_pair_qty(qty: float, spot_step=None, fut_step=None) -> float:
    """Floor `qty` to the coarser of the spot / future qty steps (both legs share it).

    No usable steps -> the input unchanged. Mirrors bot.bybit_v5.round_step
    (round down) without importing the exchange client.
    """
    from decimal import ROUND_DOWN, Decimal, InvalidOperation

    try:
        q = Decimal(str(qty))
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return 0.0
    if q <= 0:
        return 0.0
    step = _coarser_step(spot_step, fut_step)
    if step is None:
        return float(q)
    try:
        st = Decimal(str(step))
        if st <= 0:
            return float(q)
        return float((q / st).to_integral_value(rounding=ROUND_DOWN) * st)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        return float(q)


def _lots_for(coin: str, fut_symbol, lots):
    """(spot_lot, fut_lot) instrument dicts for a pair from a Runner.inst-style map.

    Falls back to the coin's perp lot for dated symbols (mirrors
    Runner._carry_round); missing/unknown -> ({}, {}), i.e. legacy raw sizing.
    """
    if not isinstance(lots, dict):
        return {}, {}
    try:
        s_lot = lots.get(spot_symbol(coin)) or {}
    except (AttributeError, TypeError):
        s_lot = {}
    try:
        f_lot = lots.get(fut_symbol) or {}
    except (AttributeError, TypeError):
        f_lot = {}
    if not isinstance(s_lot, dict):
        s_lot = {}
    if not isinstance(f_lot, dict):
        if isinstance(s_lot, dict):
            f_lot = s_lot
        else:
            f_lot = {}
    return s_lot, f_lot


def _pair_min_ok(qty: float, s_lot: dict, f_lot: dict, s_px: float, f_px: float) -> bool:
    """True when the rounded pair qty passes both legs' min_qty / min_notional."""
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return False
    if not (q > 0):
        return False
    for lot, px in ((s_lot or {}, s_px), (f_lot or {}, f_px)):
        try:
            mq = float(lot.get("min_qty", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            mq = 0.0
        if mq > 0 and q < mq - 1e-12:
            return False
        try:
            mn = float(lot.get("min_notional", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            mn = 0.0
        try:
            p = float(px)
        except (TypeError, ValueError):
            p = 0.0
        if mn > 0 and p > 0 and q * p < mn - 1e-9:
            return False
    return True


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
            # F1: carry hedge-recovery / timeout-close / delivery-sale markets
            # are non-reduceOnly Markets by construction (spot has no
            # reduceOnly; a hedge short opens a new position). Mark them
            # carry-recovery so risk_guard exempts market_not_reduce_only
            # while keeping single/per-coin/total caps (plus the 0.30x cap
            # below). Reduce-only futures legs (timeout Buy, delivery Buy)
            # already pass via the reduce-only path; pass orderType through
            # so the guard sees them as Markets.
            try:
                _is_rec = (str(o.get("orderType", "")).lower() == "market"
                           and not is_exit)
            except Exception:
                _is_rec = False
            _meta = dict(kind="carry", carry_recovery=bool(_is_rec))
            try:
                if str(o.get("orderType", "")).lower() == "market":
                    _meta["orderType"] = "Market"
            except Exception:
                pass
            conv.append(mirror.Order(str(o.get("orderLinkId", "")), sym,
                                     str(o.get("side", "Buy")), q, kind,
                                     price=px, reduce_only=is_exit,
                                     meta=_meta))
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
           quotes_by_coin: dict, lots=None) -> tuple[list, list]:
    """Pure carry decision for one cycle.

    expiries_by_coin: {coin: [{symbol, category, delivery_ms}, ...]}.
    quotes_by_coin: {coin: {spot_ask, spot_bid, spot_mid,
      fut_by_sym: {fut_sym: {bid, ask, mid}}}}; missing quotes -> no entry.
    lots: optional {symbol: {qty_step, min_qty, min_notional}} map
      (Runner.inst). When lots cover a pair, its qty is floored to the coarser
      of the spot / future qty steps BEFORE placing (both legs identical) and
      stored; a rounded qty of 0 or below minimum notional logs carry_skip
      with reason=min_qty. Without lots the legacy raw qty_for sizing applies
      (Runner._carry_round still rounds what is placed).

    Returns (want_payloads, logs). want_payloads are raw exchange payloads
    (with category + orderLinkId prefix ``c``). logs are dicts with op in
    {carry_entry, carry_unhedged, carry_close, carry_settle, carry_slice,
    carry_skip, carry_cap} for the runner to emit. cstate is mutated
    (positions/entered).
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
    # N3: throttled carry_noquotes log when contracts/quotes are missing
    # (silent ([], []) before); one log per coin per UTC hour via the
    # existing skip-dedupe so testnet triage sees the outage without spam.
    try:
        _noq = not expiries_by_coin or not quotes_by_coin
    except Exception:
        _noq = True
    if _noq:
        if not _skip_already(cstate, "noquotes:" + _skip_hour_key("ALL", now)):
            logs.append(dict(op="carry_noquotes"))
        return want, logs
    positions = cstate.setdefault("positions", {})
    for coin in list(RULE_PARAMS.get("coins", []) or []):
        pos = positions.get(coin)
        if isinstance(pos, dict):
            dlv = int(pos.get("delivery_ms", 0) or 0)
            # Settling grace (bot_carryslice): a zero-remainder settling
            # position whose futures safety Buy never fills (live dated
            # shorts auto-settle) finalises from the slice VWAP after grace.
            if pos.get("settling"):
                try:
                    _sold_g = _slice_sold(pos)
                    _slink_g = pos.get("spot_sale_link")
                    _stot_g = float(pos.get("slice_total", 0) or 0)
                    _sq_g = float(pos.get("spot_qty_filled", 0) or pos.get("qty", 0) or 0)
                    _tgt_g = _stot_g if _stot_g > 0 else _sq_g
                    if (_slink_g is None and _tgt_g > 0
                            and _sold_g + SLICE_DUST >= _tgt_g
                            and dlv and now_ms >= dlv + SETTLE_GRACE_MS):
                        vwap = _slice_vwap(pos)
                        if vwap:
                            pnl, ret = _settle_pnl(pos, f, vwap)
                            rec = dict(pos)
                            rec.update(status="delivered", S_del=float(vwap),
                                       realised_pnl=round(float(pnl), 4),
                                       realised_ret_alloc=round(float(ret), 6),
                                       settle_note="slices_vwap_autosettle")
                            cstate.setdefault("history", []).append(rec)
                            ent = f"{coin}:{pos.get('symbol')}"
                            if ent not in cstate.setdefault("entered", []):
                                cstate["entered"].append(ent)
                            positions.pop(coin, None)
                            logs.append(dict(op="carry_settled", coin=coin,
                                             symbol=pos.get("symbol"), S_del=float(vwap),
                                             realised_pnl=round(float(pnl), 4),
                                             note="slices_vwap_autosettle"))
                except (TypeError, ValueError, AttributeError):
                    pass
                continue
            if dlv and now_ms >= dlv and _pos_open(pos) and not pos.get("settling"):
                qty = float(pos.get("qty", 0) or 0)
                # Settle what actually filled per leg (paper_d17bfg2c: the stored
                # raw qty 0.014546 never filled; the rounded 0.014 did).
                try:
                    spot_q = float(pos.get("spot_qty_filled", 0) or 0)
                except (TypeError, ValueError):
                    spot_q = 0.0
                try:
                    fut_q = float(pos.get("fut_qty_filled", 0) or 0)
                except (TypeError, ValueError):
                    fut_q = 0.0
                if not (spot_q > 0):
                    spot_q = qty
                if not (fut_q > 0):
                    fut_q = qty
                # bot_carryslice: slices already sold part of the spot leg;
                # the post-delivery sale is the unsold remainder (fallback).
                sold = _slice_sold(pos)
                try:
                    remainder = float(spot_q) - float(sold)
                except (TypeError, ValueError):
                    remainder = float(spot_q)
                if remainder < 0:
                    remainder = 0.0
                if max(spot_q, fut_q) > 0:
                    f_link = f"{LINK_PREFIX}{coin}X{mirror.t36(now)}F"
                    if remainder > SLICE_DUST:
                        s_link = f"{LINK_PREFIX}{coin}X{mirror.t36(now)}S"
                        want.append(market_payload(pos.get("spot_symbol", spot_symbol(coin)),
                                                     "Sell", remainder, s_link, "spot"))
                        want.append(market_payload(pos.get("symbol"), "Buy", fut_q, f_link,
                                                   pos.get("category", "linear"),
                                                   reduce_only=True, position_idx=2))
                        pos["settling"] = True
                        pos["spot_sale_link"] = s_link
                        pos["fut_close_link"] = f_link
                    else:
                        # Fully sliced: futures safety Buy only; note_exec
                        # finalises on its fill (or the grace path above).
                        want.append(market_payload(pos.get("symbol"), "Buy", fut_q, f_link,
                                                   pos.get("category", "linear"),
                                                   reduce_only=True, position_idx=2))
                        pos["settling"] = True
                        pos["spot_sale_link"] = None
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
                                     ret_alloc=round(float(ret), 6),
                                     slice_sold=round(float(sold), 8),
                                     spot_remainder=round(float(remainder), 8)))
                continue
            # bot_carryslice: pre-delivery sliced exit, one slice per 5-minute
            # bucket at the first cycle inside the bucket. Restart-safe: the
            # emitted buckets + slice links + sold qty live in pos (state.json).
            if (dlv and _pos_open(pos) and not pos.get("settling")
                    and _slice_bucket(now_ms, dlv) is not None):
                try:
                    spot_qw = float(pos.get("spot_qty_filled", 0) or 0)
                except (TypeError, ValueError):
                    spot_qw = 0.0
                if not (spot_qw > 0):
                    try:
                        spot_qw = float(pos.get("qty", 0) or 0)
                    except (TypeError, ValueError):
                        spot_qw = 0.0
                if spot_qw > 0:
                    bucket = _slice_bucket(now_ms, dlv)
                    try:
                        done = pos.setdefault("slice_buckets_done", [])
                        if not isinstance(done, list):
                            done = pos["slice_buckets_done"] = list(done or [])
                    except (AttributeError, TypeError):
                        done = []
                    if bucket is not None and bucket not in done:
                        try:
                            tot = float(pos.get("slice_total", 0) or 0)
                        except (TypeError, ValueError):
                            tot = 0.0
                        if not (tot > 0):
                            tot = float(spot_qw)
                            pos["slice_total"] = float(tot)
                        try:
                            qmap = pos.setdefault("slice_qtys", {})
                            if not isinstance(qmap, dict):
                                qmap = pos["slice_qtys"] = {}
                        except (AttributeError, TypeError):
                            qmap = {}
                        try:
                            prev = sum(float(qmap.get(str(b), 0) or 0)
                                       for b in range(SLICE_N - 1) if str(b) in qmap)
                        except (TypeError, ValueError):
                            prev = 0.0
                        step = _spot_step_for(coin, pos.get("symbol"), lots)
                        if bucket < SLICE_N - 1:
                            sqty = _floor_to_step(float(tot) / SLICE_N, step)
                        else:
                            sqty = float(tot) - float(prev)
                        if sqty > SLICE_DUST:
                            s_link = f"{LINK_PREFIX}{coin}D{mirror.t36(now)}{bucket}S"
                            p = market_payload(pos.get("spot_symbol", spot_symbol(coin)),
                                               "Sell", float(sqty), s_link, "spot")
                            p["timeInForce"] = "IOC"  # market IOC on spot
                            want.append(p)
                            try:
                                done.append(int(bucket))
                            except (TypeError, ValueError):
                                pass
                            try:
                                qmap[str(bucket)] = float(sqty)
                            except (TypeError, ValueError):
                                pass
                            try:
                                sl = pos.setdefault("slice_links", {})
                                if not isinstance(sl, dict):
                                    sl = pos["slice_links"] = {}
                                sl[s_link] = float(sqty)
                            except (AttributeError, TypeError):
                                pass
                            logs.append(dict(op="carry_slice", coin=coin,
                                             symbol=pos.get("symbol"), bucket=int(bucket),
                                             qty=float(sqty), link=s_link,
                                             delivery_ms=int(dlv)))
                        else:
                            # Dust/zero slice: mark done so the bucket never refires.
                            try:
                                done.append(int(bucket))
                            except (TypeError, ValueError):
                                pass
                            try:
                                qmap[str(bucket)] = 0.0
                            except (TypeError, ValueError):
                                pass
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
                try:
                    spot_fq = float(pos.get("spot_qty_filled", 0) or 0)
                except (TypeError, ValueError):
                    spot_fq = 0.0
                try:
                    fut_fq = float(pos.get("fut_qty_filled", 0) or 0)
                except (TypeError, ValueError):
                    fut_fq = 0.0
                if n > MAX_UNHEDGED_CYCLES:
                    if sf:
                        link = f"{LINK_PREFIX}{coin}U{mirror.t36(now)}S"
                        want.append(market_payload(pos.get("spot_symbol", spot_symbol(coin)),
                                                   "Sell", spot_fq or qty, link, "spot"))
                    else:
                        link = f"{LINK_PREFIX}{coin}U{mirror.t36(now)}F"
                        want.append(market_payload(pos.get("symbol"), "Buy", fut_fq or qty, link,
                                                   pos.get("category", "linear"),
                                                   reduce_only=True, position_idx=2))
                    logs.append(dict(op="carry_close", coin=coin, symbol=pos.get("symbol"),
                                     reason="unhedged_timeout", cycles=n,
                                     qty=float(spot_fq or qty) if sf else float(fut_fq or qty)))
                    continue
                if sf:
                    link = f"{LINK_PREFIX}{coin}H{mirror.t36(now)}F"
                    want.append(market_payload(pos.get("symbol"), "Sell", spot_fq or qty, link,
                                               pos.get("category", "linear"),
                                               position_idx=2))
                    logs.append(dict(op="carry_unhedged", coin=coin, symbol=pos.get("symbol"),
                                     missing="fut", cycles=n, qty=float(spot_fq or qty)))
                else:
                    link = f"{LINK_PREFIX}{coin}H{mirror.t36(now)}S"
                    want.append(market_payload(pos.get("spot_symbol", spot_symbol(coin)),
                                               "Buy", fut_fq or qty, link, "spot"))
                    logs.append(dict(op="carry_unhedged", coin=coin, symbol=pos.get("symbol"),
                                     missing="spot", cycles=n, qty=float(fut_fq or qty)))
                continue
            # NEITHER leg filled (both IOCs missed/cancelled): retry the pair at
            # fresh prices, max MAX_ENTRY_ATTEMPTS per roll, then carry_abandon
            # (position cleared, re-evaluated at the next roll). One-leg-filled
            # keeps the unhedged recovery above.
            try:
                natt = int(pos.get("attempts", 1) or 1)
            except (TypeError, ValueError):
                natt = 1
            if natt >= MAX_ENTRY_ATTEMPTS:
                logs.append(dict(op="carry_abandon", coin=coin, symbol=pos.get("symbol"),
                                 attempts=natt))
                try:
                    positions.pop(coin, None)
                except (AttributeError, TypeError):
                    pass
                continue
            rq = (quotes_by_coin or {}).get(coin) or {}
            try:
                r_fut_q = (rq.get("fut_by_sym") or {}).get(pos.get("symbol")) or {}
                r_s_ask = float(rq.get("spot_ask") or rq.get("spot_mid") or 0)
                r_f_bid = float(r_fut_q.get("bid") or r_fut_q.get("mid") or 0)
                r_s_mid = float(rq.get("spot_mid") or r_s_ask)
                r_f_mid = float(r_fut_q.get("mid") or r_f_bid)
            except (TypeError, ValueError, AttributeError, KeyError):
                continue
            if not (r_s_mid > 0 and r_f_mid > 0 and r_s_ask > 0 and r_f_bid > 0):
                continue
            # Leader fix 2026-10-06: a retry is a NEW entry decision, so the frozen basis threshold applies again
            # (paper_d17bfg2c entered ETH on retry at ~3.8 %/yr after the first attempt passed at 4.02 %).
            try:
                r_dte = (int(pos.get("delivery_ms", 0) or 0) - now_ms) / MS_DAY
                r_basis = annualised_basis(float(r_f_mid), float(r_s_mid), float(r_dte))
            except (TypeError, ValueError, ZeroDivisionError):
                r_basis = float("nan")
            if not (r_basis >= float(RULE_PARAMS.get("basis_threshold", 0.04))):
                logs.append(dict(op="carry_abandon", coin=coin, symbol=pos.get("symbol"), attempts=natt,
                                 reason="basis_below_threshold_on_retry",
                                 ann_basis=None if r_basis != r_basis else round(float(r_basis), 6)))
                try:
                    positions.pop(coin, None)
                except (AttributeError, TypeError):
                    pass
                continue
            r_qty = qty_for(f, equity, r_s_ask)
            if not (r_qty > 0):
                continue
            if lots is not None:
                r_s_lot, r_f_lot = _lots_for(coin, pos.get("symbol"), lots)
                if r_s_lot or r_f_lot:
                    r_qty = round_pair_qty(r_qty, (r_s_lot or {}).get("qty_step"),
                                           (r_f_lot or {}).get("qty_step"))
                    if not _pair_min_ok(r_qty, r_s_lot, r_f_lot, r_s_ask, r_f_bid):
                        if not _skip_already(cstate, _skip_hour_key(coin, now)):
                            logs.append(dict(op="carry_skip", coin=coin, symbol=pos.get("symbol"),
                                             reason="min_qty", qty=float(r_qty)))
                        continue
            if not carry_cap_ok(r_qty, r_f_bid, equity):
                logs.append(dict(op="carry_cap", coin=coin, symbol=pos.get("symbol"),
                                 reason="carry_cap"))
                continue
            r_cand = dict(symbol=pos.get("symbol"), category=pos.get("category", "linear"))
            r_spot, r_fut = entry_payloads(coin, r_cand, r_s_ask, r_f_bid, r_qty, now)
            want.extend([r_spot, r_fut])
            pos.update(qty=float(r_qty), S_entry=float(r_s_mid), F_entry=float(r_f_mid),
                       S_ask=float(r_s_ask), F_bid=float(r_f_bid),
                       spot_link=r_spot["orderLinkId"], fut_link=r_fut["orderLinkId"],
                       spot_filled=False, fut_filled=False, S_fill=None, F_fill=None,
                       spot_qty_filled=0.0, fut_qty_filled=0.0,
                       unhedged_cycles=0, attempts=natt + 1, entry_time=str(now))
            logs.append(dict(op="carry_entry", coin=coin, symbol=pos.get("symbol"),
                             category=pos.get("category", "linear"),
                             S_entry=float(r_s_mid), F_entry=float(r_f_mid),
                             qty=float(r_qty), attempt=natt + 1, retry=True))
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
            if not _skip_already(cstate, _skip_hour_key(coin, now)):
                logs.append(dict(op="carry_skip", coin=coin, symbol=cand["symbol"],
                                 ann_basis=round(float(basis), 6)))
            continue
        qty = qty_for(f, equity, s_ask)
        if not (qty > 0):
            continue
        if lots is not None:
            s_lot, f_lot = _lots_for(coin, cand["symbol"], lots)
            if s_lot or f_lot:
                qty = round_pair_qty(qty, (s_lot or {}).get("qty_step"),
                                     (f_lot or {}).get("qty_step"))
                if not _pair_min_ok(qty, s_lot, f_lot, s_ask, f_bid):
                    if not _skip_already(cstate, _skip_hour_key(coin, now)):
                        logs.append(dict(op="carry_skip", coin=coin, symbol=cand["symbol"],
                                         reason="min_qty", qty=float(qty),
                                         ann_basis=round(float(basis), 6)))
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
                               spot_qty_filled=0.0, fut_qty_filled=0.0,
                                spot_link=spot_p["orderLinkId"], fut_link=fut_p["orderLinkId"],
                                unhedged_cycles=0, attempts=1, ann_basis=round(float(basis), 6),
                                dte_days=round(float(dte), 2))
        logs.append(dict(op="carry_entry", coin=coin, symbol=cand["symbol"],
                         category=cand.get("category", "linear"),
                         S_entry=float(s_mid), F_entry=float(f_mid),
                         ann_basis=round(float(basis), 6),
                         dte_days=round(float(dte), 2),
                         qty=float(qty)))
    return want, logs


def _acc_leg_fill(pos: dict, leg: str, qty: float, price: float) -> float:
    """Accumulate a (possibly partial) fill into the leg's filled qty.

    Tracks ``spot_qty_filled`` / ``fut_qty_filled`` (actual filled quantities
    from the exchange, which is what filled after qty-step rounding) and keeps
    a VWAP in S_fill / F_fill across partials. Returns the leg total.
    """
    key_q = "spot_qty_filled" if leg == "spot" else "fut_qty_filled"
    key_f = "S_fill" if leg == "spot" else "F_fill"
    key_b = "spot_filled" if leg == "spot" else "fut_filled"
    try:
        prev = float(pos.get(key_q, 0) or 0)
    except (TypeError, ValueError):
        prev = 0.0
    tot = prev + float(qty)
    pos[key_q] = float(tot)
    if tot > 0:
        pos[key_b] = True
    try:
        old_px = pos.get(key_f)
        old_px = float(old_px) if old_px is not None else None
    except (TypeError, ValueError):
        old_px = None
    if old_px is None or not (prev > 0):
        pos[key_f] = float(price)
    else:
        try:
            pos[key_f] = float((prev * old_px + float(qty) * float(price)) / tot) if tot > 0 else float(price)
        except (TypeError, ValueError, ZeroDivisionError):
            pos[key_f] = float(price)
    return float(tot)


def _is_slice_link(pos: dict, coin: str, link) -> bool:
    """True for a persisted pre-delivery slice sale link (bot_carryslice)."""
    try:
        sl = pos.get("slice_links") or {}
        if isinstance(sl, dict) and str(link or "") in sl:
            return True
    except (AttributeError, TypeError):
        pass
    try:
        s = str(link or "")
        # Slice links: c<COIN>D<t36><bucket>S (distinct from entry/hedge/settle links).
        if s.startswith(f"{LINK_PREFIX}{coin}D") and s.endswith("S"):
            return True
    except Exception:
        pass
    return False


def note_exec(cstate: dict, link: str, qty: float, price: float):
    """Record a fill of a carry link (prefix ``c``) into the carry state.

    Entry, hedge-retry and recovery fills accumulate the ACTUAL filled qty per
    leg (``spot_qty_filled`` / ``fut_qty_filled``); hedge recovery and delivery
    settlement size from those, never from the pre-rounding ``qty``.

    Slice fills (bot_carryslice) accumulate ``spot_slice_sold_qty`` /
    ``spot_slice_proceeds`` for the settlement VWAP and never touch the entry
    ``spot_qty_filled``; the final spot sale (remainder) finalises with the
    VWAP across slices + remainder once the full filled qty is sold.
    """
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
        if not (q > 0 and px > 0):
            return None
        if link == pos.get("spot_sale_link"):
            # Remainder sale: accumulate (partial fills share one link) and
            # finalise with the VWAP once slices + remainder cover the fill.
            sold = _acc_slice_fill(pos, q, px)
            try:
                spot_q = float(pos.get("spot_qty_filled", 0) or pos.get("qty", 0) or 0)
            except (TypeError, ValueError):
                spot_q = 0.0
            if spot_q > 0 and sold + SLICE_DUST < spot_q:
                return dict(op="carry_fill", coin=coin, symbol=pos.get("spot_symbol"),
                            leg="spot_sale", price=float(px), qty=float(q),
                            sold=float(sold), pending=True)
            vwap = _slice_vwap(pos)
            s_del = float(vwap) if vwap else float(px)
            pnl, ret = _settle_pnl(pos, 0, s_del)
            rec = dict(pos)
            rec.update(status="delivered", S_del=float(s_del),
                       realised_pnl=round(float(pnl), 4),
                       realised_ret_alloc=round(float(ret), 6))
            cstate.setdefault("history", []).append(rec)
            ent = f"{coin}:{pos.get('symbol')}"
            if ent not in cstate.setdefault("entered", []):
                cstate["entered"].append(ent)
            positions.pop(coin, None)
            return dict(op="carry_settled", coin=coin, symbol=pos.get("symbol"),
                        S_del=float(s_del), realised_pnl=round(float(pnl), 4))
        if _is_slice_link(pos, coin, link):
            sold = _acc_slice_fill(pos, q, px)
            return dict(op="carry_fill", coin=coin, symbol=pos.get("spot_symbol"),
                        leg="spot_slice", price=float(px), qty=float(q),
                        sold=float(sold))
        if link == pos.get("fut_close_link") and pos.get("settling") and not pos.get("spot_sale_link"):
            # Fully-sliced position: no remainder sale; the futures safety
            # Buy confirms settlement (slice VWAP is the exit price).
            vwap = _slice_vwap(pos)
            s_del = float(vwap) if vwap else None
            if s_del:
                pnl, ret = _settle_pnl(pos, 0, s_del)
            else:
                pnl, ret = 0.0, 0.0
            rec = dict(pos)
            rec.update(status="delivered",
                       S_del=float(s_del) if s_del else None,
                       realised_pnl=round(float(pnl), 4),
                       realised_ret_alloc=round(float(ret), 6),
                       settle_note="slices_vwap")
            cstate.setdefault("history", []).append(rec)
            ent = f"{coin}:{pos.get('symbol')}"
            if ent not in cstate.setdefault("entered", []):
                cstate["entered"].append(ent)
            positions.pop(coin, None)
            return dict(op="carry_settled", coin=coin, symbol=pos.get("symbol"),
                        S_del=float(s_del) if s_del else None,
                        realised_pnl=round(float(pnl), 4),
                        note="slices_vwap")
        if link == pos.get("spot_link"):
            tot = _acc_leg_fill(pos, "spot", q, px)
            if not pos.get("S_entry"):
                pos["S_entry"] = px
            return dict(op="carry_fill", coin=coin, symbol=pos.get("spot_symbol"),
                        leg="spot", price=float(px), qty=float(q), filled=float(tot))
        if link == pos.get("fut_link"):
            tot = _acc_leg_fill(pos, "fut", q, px)
            if not pos.get("F_entry"):
                pos["F_entry"] = px
            ent = f"{coin}:{pos.get('symbol')}"
            if ent not in cstate.setdefault("entered", []):
                cstate["entered"].append(ent)
            if _pos_open(pos):
                pos["unhedged_cycles"] = 0
            return dict(op="carry_fill", coin=coin, symbol=pos.get("symbol"),
                        leg="fut", price=float(px), qty=float(q), filled=float(tot))
        if str(link).startswith(f"{LINK_PREFIX}{coin}") and str(link).endswith("S"):
            tot = _acc_leg_fill(pos, "spot", q, px)
            if _pos_open(pos):
                pos["unhedged_cycles"] = 0
            return dict(op="carry_fill", coin=coin, symbol=pos.get("spot_symbol"),
                        leg="spot", price=float(px), qty=float(q), filled=float(tot))
        if str(link).startswith(f"{LINK_PREFIX}{coin}") and str(link).endswith("F"):
            tot = _acc_leg_fill(pos, "fut", q, px)
            if _pos_open(pos):
                pos["unhedged_cycles"] = 0
            ent = f"{coin}:{pos.get('symbol')}"
            if ent not in cstate.setdefault("entered", []):
                cstate["entered"].append(ent)
            return dict(op="carry_fill", coin=coin, symbol=pos.get("symbol"),
                        leg="fut", price=float(px), qty=float(q), filled=float(tot))
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
