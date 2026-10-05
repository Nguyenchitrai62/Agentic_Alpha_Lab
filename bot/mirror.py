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
A piece with a market exit in flight (exit_sent < 2 min old) carries no other resting order, so the market exit and a
TP/stop/reduce can never both fill for the full piece qty out of the shared (symbol, positionIdx) net (bot_bookgap).
Fill remainders at/below 1e-9 of the piece size are float dust and are clamped to exactly 0, so closed pieces never
refire exits every 2 minutes (bot_bookgap).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

GRACE_MIN = 3
BUDGET, GAP = 0.26, 0.02
ENTRY_DELAY_MIN = 5  # user rule: no new order fills in the first 5 minutes after the 4h close
DIP_SL_DEFAULT = 4.0  # global dip close-stop multiple (v417 row X overrides per coin)
DUST_REL = 1e-9  # remainders at/below this fraction of the piece size are float dust, not money (bot_bookgap)
EXIT_INFLIGHT_MIN = 2.0  # runner market-exit throttle: a piece with exit_sent this fresh has an exit in flight (bot_bookgap)


def _market_inflight(pc: dict, now) -> bool:
    """True while a market exit of this piece may still be in flight (exit_sent < 2 min old).

    While in flight the piece must carry no other resting order (no TP/stop/reduce/add,
    no entry remainder): otherwise the market exit and the resting order can both fill
    for the full piece qty (market sorts before limits in the same minute), spending the
    shared (symbol, positionIdx) net twice and stranding the victim piece whose exchange
    balance was consumed (bot_bookgap: 25,435 exit placements for 143 fills). Once the
    marker is stale the protection is emitted again, so a failed exit never disarms a piece.
    """
    try:
        sent = pc.get("exit_sent")
        if sent is None:
            return False
        age_min = (pd.Timestamp(now) - pd.Timestamp(sent)).total_seconds() / 60.0
        return 0.0 <= age_min < EXIT_INFLIGHT_MIN
    except (TypeError, ValueError, AttributeError):
        return False


def _zero_dust(left: float, ref: float) -> float:
    """Clamp a ULP-level remainder to exactly 0 (bot_bookgap: 1.5e-12 leftovers refired exits every 2 min)."""
    try:
        if left <= DUST_REL * max(abs(ref), 1e-18):
            return 0.0
    except (TypeError, ValueError):
        pass
    return max(0.0, left)


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


def _open_sigma(row: dict) -> tuple[float, float]:
    """Bar open and 4h sigma implied by a dip row: buy_limit = open(1 - rung*sigma), stop = buy_limit(1 - 4*sigma)."""
    lv = float(row["buy_limit"])
    if not lv:
        return 0.0, 0.0
    sigma = (1.0 - float(row["stop"]) / lv) / 4.0
    rung = float(row.get("rung", 0.0))
    denom = 1.0 - rung * sigma
    if denom <= 0:
        return 0.0, 0.0
    return lv / denom, sigma


def _dip_M(sym: str, dip_sl_coin) -> float:
    """Per-coin dip close-stop multiple (default 4 sigma; v417 row X: XRP 5.5)."""
    if not dip_sl_coin:
        return DIP_SL_DEFAULT
    try:
        v = dip_sl_coin.get(sym, DIP_SL_DEFAULT)
    except AttributeError:
        return DIP_SL_DEFAULT
    try:
        return float(v)
    except (TypeError, ValueError):
        return DIP_SL_DEFAULT


def dip_stop_price(row: dict, sym: str, dip_sl_coin=None) -> float:
    """Dip close-stop price with the per-coin multiple: stop = buy_limit * (1 - M * sigma4),
    sigma4 = (1 - row_stop / buy_limit) / 4. Default (M == 4) returns the row stop bit-for-bit."""
    base = float(row["stop"])
    m = _dip_M(sym, dip_sl_coin)
    if m == DIP_SL_DEFAULT:
        return base
    lv = float(row["buy_limit"])
    if not lv:
        return base
    sigma4 = (1.0 - base / lv) / 4.0
    if not sigma4 > 0:
        return base
    return lv * (1.0 - m * sigma4)


def dip_risk_dist(row: dict, sym: str, dip_sl_coin=None) -> float:
    """Dip budget distance with the per-coin stop: (buy_limit - stop_M) / buy_limit.
    Default returns the row distance bit-for-bit."""
    lv = float(row["buy_limit"])
    if not lv:
        return 0.0
    m = _dip_M(sym, dip_sl_coin)
    if m == DIP_SL_DEFAULT:
        return (lv - float(row["stop"])) / lv
    return (lv - dip_stop_price(row, sym, dip_sl_coin)) / lv


def note_dip_stop(ledger: dict, pid: str, t) -> None:
    """Record a dip stop-out exit time on its piece (bot close5 stop or native backstop fill).
    TP / time exits must never call this. desired() with dip_cooldown_h > 0 blocks new rungs of the
    same (phase, coin) whose holding-bar open B satisfies s < B <= s + H."""
    try:
        pc = ledger.get(pid)
    except AttributeError:
        return
    if not isinstance(pc, dict):
        return
    try:
        pc["stop_exit_t"] = str(pd.Timestamp(t))
    except (TypeError, ValueError):
        return


def _dip_stop_times(ledger: dict) -> list:
    """All recorded dip stop-out times as [(phase, symbol, Timestamp)]."""
    out = []
    try:
        items = list(ledger.items())
    except AttributeError:
        return out
    for _pid, pc in items:
        if not isinstance(pc, dict):
            continue
        if pc.get("kind") != "dip":
            continue
        s_raw = pc.get("stop_exit_t", pc.get("stop_exit"))
        if s_raw is None and pc.get("exit_reason") in ("close5_stop", "stop", "backstop", "rung_sl") and pc.get("exit_t") is not None:
            s_raw = pc.get("exit_t")
        if s_raw is None:
            continue
        try:
            s = pd.Timestamp(s_raw)
        except (TypeError, ValueError):
            continue
        out.append((pc.get("phase"), pc.get("symbol"), s))
    return out


def dip_cooled(symbol: str, phase, bar_open, ledger: dict, dip_cooldown_h) -> bool:
    """True when a new dip rung of (phase, symbol) with holding-bar open bar_open is inside a stop cooldown:
    any stop-out s of the same (phase, coin) with s < bar_open <= s + H hours (v417 row C)."""
    try:
        h = float(dip_cooldown_h or 0.0)
    except (TypeError, ValueError):
        return False
    if not h > 0:
        return False
    try:
        b = pd.Timestamp(bar_open)
    except (TypeError, ValueError):
        return False
    for ph2, sym2, s in _dip_stop_times(ledger):
        if sym2 != symbol or ph2 != phase:
            continue
        try:
            if s < b <= s + pd.Timedelta(hours=h):
                return True
        except (TypeError, ValueError):
            continue
    return False


def corr_mult(plan_dips_for_phase, last_close: dict | None, a_sym: str) -> float:
    """Correlation-aware size multiplier for coin a: 1 / (1 + n), n = number of OTHER majors whose last CLOSED 1m
    close is at least 2.5 sigma_4h below their own current bar open (same phase / sub-book).

    plan_dips_for_phase: {symbol -> dip row or list of dip rows of that phase} (each row has rung / buy_limit / stop;
    any rung row of that coin and phase may be used). A list of dip dicts with a "symbol" key is also accepted.
    last_close: {symbol -> last closed 1m close}. Missing coins are skipped (not counted).
    """
    if not last_close:
        return 1.0
    if isinstance(plan_dips_for_phase, list):
        grouped: dict = {}
        for r in plan_dips_for_phase:
            s = r.get("symbol")
            if s is None:
                continue
            grouped.setdefault(s, []).append(r)
        plan_dips_for_phase = grouped
    n = 0
    for b, rows in (plan_dips_for_phase or {}).items():
        if b == a_sym:
            continue
        if b not in last_close or last_close[b] is None:
            continue
        row = rows[0] if isinstance(rows, list) else rows
        try:
            open_b, sigma_b = _open_sigma(row)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        if sigma_b <= 0 or open_b <= 0:
            continue
        try:
            if float(last_close[b]) <= open_b * (1.0 - 2.5 * sigma_b):
                n += 1
        except (TypeError, ValueError):
            continue
    return 1.0 / (1.0 + n)


def is_bear(opens) -> bool:
    """Bear regime: latest 4h bar OPEN < simple mean of the last 1200 4h opens including it (min 600 bars)."""
    try:
        seq = list(opens or [])
    except TypeError:
        return False
    if len(seq) < 600:
        return False
    window = seq[-1200:]
    try:
        mean = sum(float(x) for x in window) / len(window)
        return float(window[-1]) < mean
    except (TypeError, ValueError):
        return False


def desired(plan: dict, now, equity: float, ledger: dict, budget: float = BUDGET, risk_mult: float = 1.0,
            corr: bool = False, last_close: dict | None = None, dip_mult: float = 1.0,
            bear_book: bool = False, bear: bool = False, dip_cooldown_h: float = 0.0,
            dip_sl_coin: dict | None = None, dip_gross_cap: float | None = None) -> dict[str, Order]:
    """The order set that should rest on the exchange now (link id -> Order). Quantities are in coins, before exchange rounding."""
    now = pd.Timestamp(now)
    out: dict[str, Order] = {}
    rk = float(risk_mult)
    caps = {p["phase"]: float(p.get("capital", 0.25)) for p in plan.get("phases", [])}
    dips_by_phase: dict = {}
    if corr:
        for s2, c2 in (plan.get("coins") or {}).items():
            for d2 in c2.get("dips", []):
                dips_by_phase.setdefault(d2.get("phase"), {}).setdefault(s2, []).append(d2)
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
                    eqty = float(o["weight"]) * equity / float(o["price"]) * rk
                    if bear_book and bear and sgn > 0:
                        eqty *= 0.5
                    out[pid + "E"] = Order(pid + "E", sym, "Buy" if sgn > 0 else "Sell", eqty,
                                           "entry", price=float(o["price"]), position_idx=_pidx(sgn), piece=pid,
                                           meta=dict(sl=o.get("sl_if_filled"), tp=o.get("tp_if_filled"), phase=ph, kind="book"))
            if piece is None:
                continue
            pc = ledger[piece]
            if _market_inflight(pc, now):
                continue  # a market exit of this piece is in flight: no TP/stop/add/reduce until it fills (bot_bookgap double-spend)
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
                        aqty = float(o["amount"]) * equity / float(o["price"]) * rk
                        if bear_book and bear and pc["side"] > 0:
                            aqty *= 0.5
                        out[tag] = Order(tag, sym, "Buy" if pc["side"] > 0 else "Sell", aqty, "add",
                                         price=float(o["price"]), position_idx=_pidx(pc["side"]), piece=piece)
                    else:
                        q = pc["qty"] if o["kind"] == "close" else pc["qty"] * min(1.0, float(o["amount"]))
                        out[tag] = Order(tag, sym, pc_side, q, "reduce", price=float(o["price"]), reduce_only=True,
                                         position_idx=_pidx(pc["side"]), piece=piece)
        # dip pieces already open: take-profit + native backstop (the 5m-close stop and the time exit are bot actions, see exits())
        # A piece with a market exit in flight carries no other resting order (same double-spend rule as book pieces).
        for pid, pc in ledger.items():
            if pc["kind"] == "dip" and pc["symbol"] == sym and pc["qty"] > 0 and not _market_inflight(pc, now):
                out[pid + "T"] = Order(pid + "T", sym, "Sell", pc["qty"], "tp", price=pc["tp"], reduce_only=True, position_idx=1, piece=pid)
                if pc.get("backstop"):
                    out[pid + "S"] = Order(pid + "S", sym, "Sell", pc["qty"], "stop", trigger=pc["backstop"], reduce_only=True,
                                           position_idx=1, piece=pid)
    # dip bids: admitted shallow-first inside each sub-book's risk budget (open rungs count first).
    # Partially filled rungs count only the filled part (frac scaled by filled/planned).
    used = {ph: 0.0 for ph in caps}
    for pc in ledger.values():
        if pc["kind"] == "dip" and pc["qty"] > 0:
            frac = float(pc["frac"])
            try:
                planned = float(pc.get("planned_qty", pc["qty"]))
            except (TypeError, ValueError):
                planned = float(pc["qty"])
            scale = float(pc["qty"]) / planned if planned > 0 else 1.0
            if scale > 1.0:
                scale = 1.0
            used[pc["phase"]] = used.get(pc["phase"], 0.0) + frac * scale * (pc["dist"] + GAP)
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
        if dip_cooled(sym, ph, bar, ledger, dip_cooldown_h):
            continue  # v417 row C: stop cooldown s < B <= s + H (per phase sub-book); open/resting pieces unaffected
        frac, lv = float(d["size_frac"]), float(d["buy_limit"])
        stop_px = dip_stop_price(d, sym, dip_sl_coin)  # v417 row X: per-coin close-stop (default = row stop)
        dist = (lv - stop_px) / lv if lv else 0.0
        # engine rule (v400 / v406): the budget 0.26 k counts the ACTUAL rung size (risk k, dip_mult and the corr multiplier included), so
        # k and dip_mult cancel (v406 scales the budget by the same dip multiplier):
        # admit while sum(frac * corr_mult * (dist + gap)) <= 0.26 x sub capital
        mult = corr_mult(dips_by_phase.get(ph, {}), last_close, sym) if corr else 1.0
        cost = frac * mult * (dist + GAP)
        if used.get(ph, 0.0) + cost > budget * caps.get(ph, 0.25) + 1e-12:
            continue
        used[ph] = used.get(ph, 0.0) + cost
        out[pid + "E"] = Order(pid + "E", sym, "Buy", frac * equity / lv * rk * mult * float(dip_mult), "entry", price=lv, position_idx=1, piece=pid,
                               meta=dict(kind="dip", phase=ph, tp=float(d["tp"]), stop=stop_px, backstop=d.get("backstop"),
                                         t_exit=str(bar + pd.Timedelta(hours=4)), frac=frac * mult, dist=dist))
    # Partially filled dip entries: the remainder stays resting (same piece/link).
    # Protection (tp/stop above) is already sized to the filled qty; the budget above
    # counts only the filled part, so the remainder does not consume extra budget here.
    # The remainder is re-emitted only while its rung is still active in the current plan
    # (otherwise the plan no longer wants it and the exchange order should cancel).
    active_pids = set()
    for sym2, c2 in (plan.get("coins") or {}).items():
        for d2 in c2.get("dips", []):
            try:
                a0b, a1b = _ts(d2["active_from"]), _ts(d2["active_until"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (a0b <= now < a1b + pd.Timedelta(minutes=1)):
                continue
            try:
                bar2 = a0b - pd.Timedelta(minutes=16)
                active_pids.add(dip_pid(d2.get("phase"), sym2, d2.get("rung"), bar2))
            except (KeyError, TypeError, ValueError):
                continue
    for pid, pc in ledger.items():
        try:
            rem = float(pc.get("entry_remaining", 0.0) or 0.0)
        except (TypeError, ValueError):
            rem = 0.0
        if pc.get("kind") != "dip" or rem <= 1e-12 or float(pc.get("qty", 0.0)) <= 0:
            continue
        if _market_inflight(pc, now):
            continue  # closing in flight: do not re-place the remainder until it fills (bot_bookgap double-spend)
        if pid + "E" in out:
            continue
        if pid not in active_pids:
            continue  # rung gone from the plan: do not re-place, let it cancel
        try:
            t_exit = pd.Timestamp(pc.get("t_exit"))
        except (TypeError, ValueError):
            continue
        bar = t_exit - pd.Timedelta(hours=4)
        a0, a1 = bar + pd.Timedelta(minutes=16), bar + pd.Timedelta(minutes=239)
        if not (a0 <= now < a1 + pd.Timedelta(minutes=1)):
            continue  # expired: let the exchange cancel, do not re-place
        px = pc.get("entry_px")
        try:
            px = float(px)
        except (TypeError, ValueError):
            continue
        if not px > 0:
            continue
        out[pid + "E"] = Order(pid + "E", pc["symbol"], "Buy", rem, "entry", price=px, position_idx=1, piece=pid,
                                meta=dict(kind="dip", phase=pc.get("phase", 0), tp=pc.get("tp"), stop=pc.get("stop5"),
                                          backstop=pc.get("backstop"), t_exit=str(t_exit),
                                          frac=float(pc.get("frac", 0.0)), dist=float(pc.get("dist", 0.0))))
    if dip_gross_cap is not None:
        try:
            _g = float(dip_gross_cap)
        except (TypeError, ValueError):
            _g = 0.0
        if _g > 0:
            # Optional dip gross-notional cap (engine sleeve_gross_cap mirror, conservative):
            # per phase sub-book, open filled dip notional + resting dip entry bids <= G x sub equity,
            # sub equity = equity x the phase cap used by the budget rule. The room left
            # (G x sub equity - open dip notional) is allocated to the resting bids in the same
            # order desired() already admits them (shallow rung first, then phase, then symbol,
            # i.e. out insertion order per phase); the last admitted bid is cut to the remaining
            # room and the rest are dropped. Recomputed every cycle (runner amends qty, never price).
            # Book orders and protection (tp/stop/reduce) are never touched.
            try:
                _eq = float(equity)
            except (TypeError, ValueError):
                _eq = 0.0
            _open: dict = {}
            try:
                _items = list(ledger.values())
            except AttributeError:
                _items = []
            for _pc in _items:
                if not isinstance(_pc, dict) or _pc.get("kind") != "dip":
                    continue
                try:
                    _q = float(_pc.get("qty", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                if _q <= 0:
                    continue
                _px = _pc.get("entry", _pc.get("entry_px"))
                try:
                    _px = float(_px)
                except (TypeError, ValueError):
                    continue
                if not _px > 0:
                    continue
                _ph = _pc.get("phase", 0)
                _open[_ph] = _open.get(_ph, 0.0) + _q * _px
            _by_ph: dict = {}
            for _link, _o in out.items():
                if _o.kind != "entry" or _o.meta.get("kind") != "dip":
                    continue
                _by_ph.setdefault(_o.meta.get("phase", 0), []).append(_link)
            for _ph, _links in _by_ph.items():
                try:
                    _sub_eq = _eq * float(caps.get(_ph, 0.25))
                except (TypeError, ValueError):
                    _sub_eq = _eq * 0.25
                _room = _g * _sub_eq - _open.get(_ph, 0.0)
                for _link in _links:
                    _o = out.get(_link)
                    if _o is None:
                        continue
                    try:
                        _not = float(_o.qty) * float(_o.price)
                    except (TypeError, ValueError):
                        continue
                    if _room <= 1e-12:
                        del out[_link]
                    elif _not <= _room + 1e-12:
                        _room -= _not
                    else:
                        _f = _room / _not if _not > 0 else 0.0
                        try:
                            _old_frac = float(_o.meta.get("frac", 0.0) or 0.0)
                        except (TypeError, ValueError):
                            _old_frac = 0.0
                        _o.qty = _room / float(_o.price) if _o.price else 0.0
                        _o.meta["frac"] = _old_frac * _f
                        _room = 0.0
    if bear_book and bear:
        # Bear-regime trim of open book longs (closes the BOT_EXECUTION.md known gap): the research engine (v410)
        # halves the book LONG target in bear, so existing longs are trimmed toward the halved target. For every open
        # BOOK long whose qty exceeds 0.5 x the plan-implied qty (weight x equity / price x risk_mult), place ONE
        # reduce-only limit sell for the excess (never below half), valid until the end of the current 4h bar; at most
        # one trim per piece per bear episode (ledger flag trimmed_bear, set by the runner, reset on bull).
        try:
            bar_start = pd.Timestamp(now).floor("4h")
        except (TypeError, ValueError):
            bar_start = pd.Timestamp(now)
        bar_end = bar_start + pd.Timedelta(hours=4)
        sub_by_ph_sym = {}
        for sym2, c2 in (plan.get("coins") or {}).items():
            for sub2 in c2.get("subs", []):
                sub_by_ph_sym[(sub2.get("phase"), sym2)] = sub2
        coin_px: dict = {}
        for sym2, c2 in (plan.get("coins") or {}).items():
            try:
                px = float(c2.get("price")) if c2.get("price") is not None else None
            except (TypeError, ValueError):
                px = None
            if px:
                coin_px[sym2] = px
        for pid, pc in list(ledger.items()):
            if pc.get("kind") != "book" or pc.get("side", 0) <= 0 or float(pc.get("qty", 0.0)) <= 0:
                continue
            if pc.get("trimmed_bear"):
                continue
            sub = sub_by_ph_sym.get((pc.get("phase"), pc.get("symbol")))
            if not sub:
                continue
            pos = sub.get("position")
            if not pos or pos.get("weight") is None:
                continue
            try:
                w = float(pos["weight"])
            except (TypeError, ValueError):
                continue
            if not w > 0:
                continue
            ref_px = coin_px.get(pc["symbol"])
            if not ref_px and last_close and pc["symbol"] in last_close:
                try:
                    ref_px = float(last_close[pc["symbol"]])
                except (TypeError, ValueError):
                    ref_px = None
            if not ref_px:
                continue
            implied = w * float(equity) / ref_px * rk
            half = 0.5 * implied
            qty = float(pc["qty"])
            if not qty > half + 1e-12:
                continue
            trim_qty = qty - half
            trim_px = None
            o = sub.get("order")
            if o and o.get("kind") in ("reduce", "close") and o.get("price") is not None:
                try:
                    trim_px = float(o["price"])
                except (TypeError, ValueError):
                    trim_px = None
            if trim_px is None:
                lc = None
                if last_close and pc["symbol"] in last_close:
                    try:
                        lc = float(last_close[pc["symbol"]])
                    except (TypeError, ValueError):
                        lc = None
                if lc is None:
                    lc = ref_px
                if not lc:
                    continue
                trim_px = lc * 1.001
            link = f"{pid}B{t36(bar_start)}"
            if link in out:
                continue
            out[link] = Order(link, pc["symbol"], "Sell", trim_qty, "reduce", price=trim_px, reduce_only=True,
                              position_idx=1, piece=pid, meta=dict(bear_trim=True, valid_until=str(bar_end)))
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


def diff(want: dict[str, Order], have: dict[str, dict], rel_tol: float = 1e-6, amend_entry_qty: bool = False) -> list[dict]:
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
        if abs(float(h.get("qty") or 0) - o.qty) > max(rel_tol * o.qty, 1e-12) and (o.kind in ("tp", "stop") or (amend_entry_qty and o.kind == "entry")):
            ch["qty"] = o.qty
        if ch:
            acts.append(dict(op="amend", link=link, symbol=o.symbol, **ch))
    return acts


def apply_fill(ledger: dict, order: Order, qty: float, price: float, t) -> None:
    """Book a fill of a bot order into the piece ledger (entry / add extend a piece; reduce / tp / stop shrink it).

    Partial entry fills leave the remainder resting: the first entry fill records
    planned_qty (the full order size) and entry_px; entry_remaining = planned - filled.
    desired() re-emits the remainder as an entry order for the same piece, while the
    risk budget counts only the filled part.
    """
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
        if "planned_qty" not in pc:
            try:
                pc["planned_qty"] = float(order.qty)
            except (TypeError, ValueError):
                pc["planned_qty"] = tot
        if "entry_px" not in pc and order.price is not None:
            pc["entry_px"] = order.price
        try:
            pc["entry_remaining"] = _zero_dust(max(0.0, float(pc.get("planned_qty", tot)) - tot),
                                              float(pc.get("planned_qty", tot)))
        except (TypeError, ValueError):
            pc["entry_remaining"] = 0.0
        if pc["entry_remaining"] <= 1e-12:
            pc["entry_remaining"] = 0.0
    elif order.kind == "add" and pid in ledger:
        pc = ledger[pid]
        tot = pc["qty"] + qty
        pc["entry"] = (pc["entry"] * pc["qty"] + price * qty) / tot
        pc["qty"] = tot
    elif pid in ledger:
        pc = ledger[pid]
        try:
            left = float(pc.get("qty", 0.0)) - float(qty)
            pc["qty"] = _zero_dust(left, max(float(pc.get("qty", 0.0)), float(qty)))
        except (TypeError, ValueError):
            ledger[pid]["qty"] = max(0.0, ledger[pid]["qty"] - qty)
