"""Independent PRE-TRADE risk guard for live mode (to be wired in later by the leader).

Pure functions, no I/O. `check` filters a desired order set before anything is
sent to the exchange. Protection (kind tp/stop) and any reduce-only order are
never blocked; everything else is checked against hard rejects first, then
against notional caps on a worst-case (all fill) basis.
"""

from __future__ import annotations

__all__ = ["DEFAULT_LIMITS", "ALLOWED_SYMBOLS", "check"]

ALLOWED_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")

DEFAULT_LIMITS = dict(
    per_coin_gross=2.5,   # per-coin gross notional <= 2.5 x equity
    dip_gross=2.0,         # total dip notional (open + resting entry bids) <= 2.0 x equity
    total_gross=4.0,       # total gross notional <= 4.0 x equity
    single_order=1.0,      # any single order notional <= 1.0 x equity
    fat_finger=0.15,       # reject orders whose price deviates > 15% from the last price
    allowed_symbols=tuple(ALLOWED_SYMBOLS),
)

_PROTECTION_KINDS = frozenset({"tp", "stop"})


def _limits(limits) -> dict:
    out = dict(DEFAULT_LIMITS)
    if not limits:
        return out
    try:
        items = dict(limits).items()
    except (TypeError, ValueError, AttributeError):
        return out
    alias = {
        "per_coin": "per_coin_gross", "per_coin_mult": "per_coin_gross",
        "per_coin_gross_mult": "per_coin_gross",
        "dip": "dip_gross", "dip_mult": "dip_gross", "dip_cap": "dip_gross",
        "total": "total_gross", "total_mult": "total_gross",
        "single": "single_order", "single_mult": "single_order",
        "fat": "fat_finger", "fat_finger_pct": "fat_finger",
        "allowed": "allowed_symbols", "symbols": "allowed_symbols",
    }
    for k, v in items:
        key = alias.get(k, k)
        if key in out:
            out[key] = v
    return out


def _orders_list(orders):
    if orders is None:
        return []
    if isinstance(orders, dict):
        return list(orders.values())
    return list(orders)


def _pieces_list(positions):
    if positions is None:
        return []
    if isinstance(positions, dict):
        return [v for v in positions.values() if isinstance(v, dict)]
    return [v for v in list(positions) if isinstance(v, dict)]


def _link(o, i: int) -> str:
    try:
        link = getattr(o, "link", None) or (o.get("link") if isinstance(o, dict) else None)
    except Exception:
        link = None
    return str(link) if link is not None else f"order_{i}"


def _sym(o) -> str | None:
    try:
        return getattr(o, "symbol", None) if not isinstance(o, dict) else o.get("symbol")
    except Exception:
        return None


def _kind(o) -> str:
    try:
        k = getattr(o, "kind", None) if not isinstance(o, dict) else o.get("kind")
    except Exception:
        k = None
    return str(k) if k is not None else ""


def _reduce_only(o) -> bool:
    try:
        r = getattr(o, "reduce_only", None) if not isinstance(o, dict) else o.get("reduce_only")
    except Exception:
        r = None
    return bool(r)


def _meta(o) -> dict:
    try:
        m = getattr(o, "meta", None) if not isinstance(o, dict) else o.get("meta")
    except Exception:
        m = None
    return dict(m) if isinstance(m, dict) else {}


def _qty(o) -> float:
    try:
        q = getattr(o, "qty", None) if not isinstance(o, dict) else o.get("qty")
        return abs(float(q))
    except (TypeError, ValueError):
        return 0.0


def _px_field(o, name: str):
    try:
        v = getattr(o, name, None) if not isinstance(o, dict) else o.get(name)
    except Exception:
        v = None
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _is_market(o) -> bool:
    """An Order is exchange-Market iff kind == stop (conditional market), its
    meta says Market, or it carries neither a limit price nor a stop trigger
    (the runner's market-exit shape)."""
    if _kind(o) == "stop":
        return True
    try:
        mt = _meta(o).get("orderType")
        if isinstance(mt, str) and mt.lower() == "market":
            return True
    except Exception:
        pass
    return _px_field(o, "price") is None and _px_field(o, "trigger") is None


def _is_dip_order(o) -> bool:
    try:
        return str(_meta(o).get("kind", "")).lower() == "dip"
    except Exception:
        return False


def _order_px(o, last) -> float | None:
    for name in ("price", "trigger"):
        v = _px_field(o, name)
        if v is not None and v > 0:
            return v
    try:
        v = float(last)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _pos_sym_qty(pc: dict):
    try:
        sym = pc.get("symbol")
    except AttributeError:
        return None, 0.0
    try:
        qty = abs(float(pc.get("qty", 0.0) or 0.0))
    except (TypeError, ValueError):
        qty = 0.0
    return sym, qty


def _pos_ref(pc: dict, last) -> float | None:
    if last is not None:
        try:
            v = float(last)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    for k in ("entry", "entry_px", "avg", "price"):
        try:
            v = float(pc.get(k))
            if v > 0:
                return v
        except (TypeError, ValueError, AttributeError):
            continue
    return None


def _is_dip_pos(pc: dict) -> bool:
    try:
        if str(pc.get("kind", "")).lower() == "dip":
            return True
        m = pc.get("meta")
        return isinstance(m, dict) and str(m.get("kind", "")).lower() == "dip"
    except Exception:
        return False


def check(orders, positions=None, equity=None, prices=None, limits=None):
    """Pre-trade filter: (allowed_orders, rejections).

    orders: list[Order] (or dict link -> Order) using the bot's Order fields.
    positions: open pieces (ledger dict pid -> piece, or list of piece dicts)
      with symbol / qty / entry / kind fields.
    equity: account equity in USDT (> 0). Zero/None/invalid -> caps are 0, so
      only reduce-only / protection orders pass.
    prices: {symbol -> last price} used for notionals and the fat-finger check.
    limits: optional dict overriding DEFAULT_LIMITS (all configurable).

    Never blocked: any reduce-only order (this covers every genuine tp/stop
    protection order and every exit — all are reduce-only by construction).
    A non-reduce-only stop is NOT protection: it is a Market order and is
    rejected by the market rule. Rejection reasons: symbol_not_allowed, market_not_reduce_only, fat_finger,
    single_order_too_big, per_coin_cap, total_cap, dip_cap, bad_order.
    """
    lim = _limits(limits)
    try:
        allowed_syms = set(lim.get("allowed_symbols") or ())
    except TypeError:
        allowed_syms = set(ALLOWED_SYMBOLS)
    try:
        eq = float(equity)
    except (TypeError, ValueError):
        eq = 0.0
    if not eq > 0:
        eq = 0.0
    prices = dict(prices or {})

    per_coin_cap = (lim.get("per_coin_gross") or 0.0) * eq
    dip_cap = (lim.get("dip_gross") or 0.0) * eq
    total_cap = (lim.get("total_gross") or 0.0) * eq
    single_cap = (lim.get("single_order") or 0.0) * eq
    try:
        fat = float(lim.get("fat_finger"))
    except (TypeError, ValueError):
        fat = 0.15

    # Open baseline (worst case uses last prices, falling back to entry levels).
    per_coin = {}
    run_total = 0.0
    run_dip = 0.0
    for pc in _pieces_list(positions):
        sym, qty = _pos_sym_qty(pc)
        if not sym or not qty > 0:
            continue
        ref = _pos_ref(pc, prices.get(sym))
        if ref is None or not ref > 0:
            continue
        notional = qty * ref
        per_coin[sym] = per_coin.get(sym, 0.0) + notional
        run_total += notional
        if _is_dip_pos(pc):
            run_dip += notional

    olist = _orders_list(orders)
    allowed, rejections = [], []
    for i, o in enumerate(olist):
        link, sym = _link(o, i), _sym(o)
        # Never block reduce-only exits or protection orders (all genuine
        # protection is reduce-only; a non-reduce-only stop is a Market
        # order and falls through to the market reject below).
        if _reduce_only(o):
            allowed.append(o)
            continue
        if not sym or not _qty(o) > 0:
            rejections.append(dict(link=link, symbol=sym, reason="bad_order"))
            continue
        if sym not in allowed_syms:
            rejections.append(dict(link=link, symbol=sym, reason="symbol_not_allowed"))
            continue
        if _is_market(o):
            rejections.append(dict(link=link, symbol=sym, reason="market_not_reduce_only"))
            continue
        last = prices.get(sym)
        px = _order_px(o, last)
        if px is None or not px > 0:
            rejections.append(dict(link=link, symbol=sym, reason="bad_order"))
            continue
        if last is not None and fat > 0:
            try:
                lv = float(last)
                if lv > 0 and abs(px - lv) / lv > fat:
                    rejections.append(dict(link=link, symbol=sym, reason="fat_finger"))
                    continue
            except (TypeError, ValueError):
                pass
        notional = _qty(o) * px
        if eq <= 0 or notional > single_cap + 1e-9:
            rejections.append(dict(link=link, symbol=sym, reason="single_order_too_big"))
            continue
        dip = _is_dip_order(o)
        if per_coin.get(sym, 0.0) + notional > per_coin_cap + 1e-9:
            rejections.append(dict(link=link, symbol=sym, reason="per_coin_cap"))
            continue
        if run_total + notional > total_cap + 1e-9:
            rejections.append(dict(link=link, symbol=sym, reason="total_cap"))
            continue
        if dip and run_dip + notional > dip_cap + 1e-9:
            rejections.append(dict(link=link, symbol=sym, reason="dip_cap"))
            continue
        per_coin[sym] = per_coin.get(sym, 0.0) + notional
        run_total += notional
        if dip:
            run_dip += notional
        allowed.append(o)
    return allowed, rejections
