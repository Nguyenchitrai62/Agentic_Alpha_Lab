"""bot_exitsoak: regression soak for bot-side market exits (time exits, close5 stops).

Covers assignment OPENCODE_W_bot_exitsoak (2026-10-07): a deterministic soak over a
paper-rule matching exchange (same fill rules as bot/paper.py and
tests/mock_bybit_v5.py: limits fill only on a strict 1m trade-through in a minute
starting after placement, markets fill at the next bar open, conditional stops with
stop-first, reduce-only capped at the position) that forces:

  (a) dip pieces reaching their 4h time exit,
  (b) close5 stop-outs,
  (c) a book plan_closed_divergence exit,
  (d) a runner restart between sending a market exit and its fill,
  (e) a partially filled market exit.

WITH the leader fix (current tree, `_acts_without_exit_cancel`): every exit completes
within <= 2 cycles, no open piece spends more than one cycle with neither S/T nor an
in-flight exit resting, and no piece is ever over-sold.
WITHOUT the fix (tmp/run_nofix.py = byte-exact `git show HEAD~1:bot/run.py`, which has
zero `exit_cancel` refs; `git diff HEAD~1 HEAD -- bot/run.py` is purely additive, so an
identity patch of the filter is behaviour-identical): the exit is cancelled in the
same cycle it is sent and never completes.

bot/ is NOT modified here (read-only); the nofix driver is loaded from the tmp copy.
No network, no keys, no exchange orders: the exchange below is in-process.
"""

import importlib.util
import json
import uuid
from dataclasses import asdict
from pathlib import Path

import pandas as pd

import bot.run as run_fix
from bot import mirror

ROOT = Path(__file__).resolve().parents[1]
NOFIX_PATH = ROOT / "research/diagnostics/bot_exitsoak/tmp/run_nofix.py"

INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}
SYM = "BTCUSDT"
PX = 80000.0


# ----------------------------------------------------------------------------
# deterministic paper-rule exchange (no network)
# ----------------------------------------------------------------------------
class DetExchange:
    """Paper-rule matching (bot/paper.py): markets fill at the next bar open,
    PostOnly crossing limits reject, reduce-only capped at the position."""

    def __init__(self, equity=10000.0):
        self.inst_map = dict(INST)
        self.cash = float(equity)
        self.orders = {}  # link -> payload + t_ms
        self.pos = {}  # (sym, idx) -> {qty, avg}
        self.execs = []
        self.px = {SYM: PX}
        self.last5map = {}  # sym -> (close_time Timestamp, close px)
        self.place_calls = []
        self._now_ms = 1_700_000_000_000

    # -- Runner interface ----------------------------------------------------
    def instruments(self, symbols):
        return {s: self.inst_map[s] for s in symbols}

    def equity_usdt(self):
        eq = self.cash
        for (sym, idx), p in self.pos.items():
            last = self.px.get(sym)
            if last and p["qty"]:
                eq += (float(last) - p["avg"]) * p["qty"] * (1 if idx == 1 else -1)
        return eq

    def step(self, now=None):
        return None

    def save(self):
        return None

    def klines(self, symbol, interval="5", limit=3):
        if symbol in self.last5map and int(limit) >= 2:
            ct, c = self.last5map[symbol]
            open_ms = int(pd.Timestamp(ct).timestamp() * 1000) - 300_000
            prog_ms = int(pd.Timestamp(ct).timestamp() * 1000) + 60_000
            closed = [str(open_ms), "80000", "80100", "79900", str(c), "1", "1"]
            prog = [str(prog_ms), str(c), str(c), str(c), str(c), "1", "1"]
            return [prog, closed]
        return []

    def open_orders(self):
        return [dict(orderLinkId=k, symbol=v["symbol"], price=v.get("price"),
                      triggerPrice=v.get("triggerPrice"), qty=v.get("qty"))
                for k, v in self.orders.items()]

    def executions(self, start_ms):
        return [e for e in self.execs if int(e["execTime"]) >= int(start_ms)]

    def place(self, p):
        link = p.get("orderLinkId")
        self.place_calls.append(link)
        o = dict(p, t_ms=self._now_ms)
        if o.get("timeInForce") == "PostOnly":
            last = self.px.get(o["symbol"])
            if last is not None:
                px = float(o["price"])
                if (o["side"] == "Buy" and px >= last) or (o["side"] == "Sell" and px <= last):
                    return None  # PostOnly would cross: rejected like paper.py
        self.orders[link] = o
        return dict(orderLinkId=link)

    def amend(self, symbol, link, **kw):
        o = self.orders.get(link)
        if o is None:
            return None
        o.update(kw)
        return dict(orderLinkId=link)

    def cancel(self, symbol, link):
        return self.orders.pop(link, None) and dict(orderLinkId=link)

    # -- matching -------------------------------------------------------------
    def seed_pos(self, sym, idx, qty, avg):
        self.pos[(sym, idx)] = dict(qty=float(qty), avg=float(avg))

    def _fill(self, link, o, qty, px, t_ms):
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
                return 0.0
            self.cash += (px - p["avg"]) * qty * sgn
            p["qty"] -= qty
        self.execs.append(dict(execId=uuid.uuid4().hex, orderLinkId=link,
                               execQty=str(qty), execPrice=str(px), execTime=str(t_ms)))
        return qty

    def process_bar(self, sym, o, h, l, c, t_ms):
        """Fill resting orders of sym against one CLOSED 1m bar (stop-first)."""
        self.px[sym] = float(c)
        mine = [(k, x) for k, x in self.orders.items()
                if x["symbol"] == sym and int(x.get("t_ms", 0)) < int(t_ms)]
        mine.sort(key=lambda kv: 0 if kv[1].get("triggerPrice")
                  else (1 if kv[1].get("orderType") == "Market" else 2))
        for k, x in mine:
            if k not in self.orders:
                continue
            idx = int(x.get("positionIdx", 1))
            qty = float(x["qty"])
            if x.get("reduceOnly"):
                have = self.pos.get((sym, idx), {}).get("qty", 0.0)
                if have <= 0:
                    self.orders.pop(k, None)
                    continue
                qty = min(qty, have)
            if x.get("triggerPrice"):
                tr = float(x["triggerPrice"])
                td = int(x.get("triggerDirection", 2))
                if td == 2 and l <= tr:
                    self._fill(k, x, qty, min(tr, o), t_ms)
                elif td == 1 and h >= tr:
                    self._fill(k, x, qty, max(tr, o), t_ms)
                else:
                    continue
            elif x.get("orderType") == "Market":
                self._fill(k, x, qty, o, t_ms)
            else:
                px = float(x["price"])
                if (x["side"] == "Buy" and l < px) or (x["side"] == "Sell" and h > px):
                    self._fill(k, x, qty, px, t_ms)
                else:
                    continue
            self.orders.pop(k, None)

    def manual_partial(self, link, qty, price, t_ms):
        """Partially fill one resting order (remainder keeps resting)."""
        o = self.orders.get(link)
        assert o is not None, link
        qty = min(float(qty), float(o["qty"]))
        if o.get("reduceOnly"):
            qty = min(qty, self.pos.get((o["symbol"], int(o.get("positionIdx", 1))),
                                       {}).get("qty", 0.0))
        self._fill(link, o, qty, float(price), t_ms)
        rest = float(o["qty"]) - qty
        if rest <= 1e-12:
            self.orders.pop(link, None)
        else:
            o["qty"] = str(rest)
        return rest


# ----------------------------------------------------------------------------
# drivers
# ----------------------------------------------------------------------------
_nofix_cache = {}


def nofix_mod():
    """Pre-fix driver: tmp/run_nofix.py (byte-exact HEAD~1:bot/run.py, no filter)."""
    if "mod" not in _nofix_cache:
        assert NOFIX_PATH.exists(), NOFIX_PATH
        src = NOFIX_PATH.read_text(encoding="utf-8")
        assert "exit_cancel" not in src  # without-fix baseline sanity
        spec = importlib.util.spec_from_file_location("bot_run_nofix_tmp", NOFIX_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert not hasattr(mod, "_acts_without_exit_cancel")
        _nofix_cache["mod"] = mod
    return _nofix_cache["mod"]


def _mk(mod, tmp_path, plan, state, ex, tag, subdir=None):
    d = (tmp_path if subdir is None else tmp_path / subdir) / f"exs_{tag}"
    d.mkdir(parents=True, exist_ok=True)
    pf = d / "plan.json"
    pf.write_text(json.dumps(plan, default=str))
    r = mod.Runner.__new__(mod.Runner)
    r.mode = "paper"
    r.plan_path = pf
    r.risk_mult, r.corr, r.tag = 1.0, False, None
    r.dip_mult, r.bear_book = 1.0, False
    r.dip_cooldown_h, r.dip_sl_coin, r.dip_gross_cap = 0.0, {}, 0.0
    r.adopt_fresh, r.no_risk_guard, r.carry_f = False, True, 0.0
    r._bear_at, r._bear, r._last_plan, r._skip_logged = None, False, None, {}
    r.maint_start = r.maint_end = None
    r._maint_active = False
    r._kline_cache_dir_override = None
    r.dir, r.state_f = d, d / "state.json"
    r.state = json.loads(json.dumps(state, default=str))
    r.state_f.write_text(json.dumps(r.state, default=str))
    r.ex, r.equity_arg, r.inst, r.logs = ex, 10000.0, dict(INST), []

    def _log(rec):
        r.logs.append(rec)
        with open(r.dir / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    r.log = _log
    return r


def _plan(now):
    # phase-0 book slot is NOT live (only phase 1 holds a position) so the
    # seeded phase-0 book piece diverges; no dip rows -> no new bids.
    return {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25},
                                                 {"phase": 1, "capital": 0.25}],
            "coins": {SYM: {"price": PX, "subs": [
                {"phase": 1, "state": "position",
                 "position": {"side": "LONG", "weight": 0.03, "avg_entry": PX,
                              "sl": 70000.0, "tp": 95000.0,
                              "opened": str(now - pd.Timedelta(hours=5))}}],
                "dips": []}}}


def _ledger(now):
    return {
        # (a) time exit: t_exit past, stop5 far below any 5m close
        "dA": dict(kind="dip", phase=0, symbol=SYM, side=1, qty=0.01, entry=78000.0,
                   tp=78780.0, stop5=70000.0, backstop=69000.0,
                   t_exit=str(now - pd.Timedelta(minutes=5)),
                   frac=0.05, dist=0.04, opened=str(now - pd.Timedelta(hours=5))),
        # (b) close5: scripted 5m close 74800 <= stop5 74880, t_exit in future
        "dB": dict(kind="dip", phase=0, symbol=SYM, side=1, qty=0.01, entry=78000.0,
                   tp=78780.0, stop5=74880.0, backstop=71760.0,
                   t_exit=str(now + pd.Timedelta(hours=3)),
                   frac=0.05, dist=0.04, opened=str(now - pd.Timedelta(minutes=30))),
        # (c) book divergence: (0, BTC) not live, gone 10 min (> GRACE 3 min)
        "bC": dict(kind="book", phase=0, symbol=SYM, side=1, qty=0.02, entry=80000.0,
                   sl=70000.0, tp=95000.0, opened=str(now - pd.Timedelta(hours=5)),
                   plan_gone_since=str(now - pd.Timedelta(minutes=10))),
    }


def _seed(mod, tmp_path, tag, pieces=("dA", "dB", "bC"), rest_protection=True):
    now = pd.Timestamp.now(tz="UTC")
    led = {k: v for k, v in _ledger(now).items() if k in pieces}
    ex = DetExchange()
    tot = sum(v["qty"] for v in led.values())
    ex.seed_pos(SYM, 1, tot, 79000.0)
    # a live runner would have S/T resting for every open piece
    state_links = {}
    if rest_protection:
        for pid, pc in led.items():
            for suffix, kind, px, trg in (("S", "stop", None, "sl" if pc["kind"] == "book" else "backstop"),
                                          ("T", "tp", "tp", None)):
                price = pc[px] if px else None
                trigger = pc[trg] if trg else None
                link = pid + suffix
                o = mirror.Order(link, SYM, "Sell", pc["qty"], kind, price=price,
                                 trigger=trigger, reduce_only=True, position_idx=1, piece=pid)
                ex.orders[link] = {"symbol": SYM, "price": price, "triggerPrice": trigger,
                                   "qty": str(pc["qty"]), "orderLinkId": link,
                                   "orderType": "Market" if kind == "stop" else "Limit",
                                   "side": "Sell", "positionIdx": 1, "reduceOnly": True,
                                   "t_ms": ex._now_ms - 120_000}
                state_links[link] = {"order": asdict(o),
                                     "rest": {"symbol": SYM, "price": price,
                                              "trigger": trigger, "qty": pc["qty"]}}
    # scripted last-closed-5m: close 74800 after dB.opened -> close5 for dB only
    # (74800 > dA.stop5 70000, so dA exits by time, not by stop).
    ex.last5map[SYM] = (now - pd.Timedelta(minutes=20), 74800.0)
    state = {"ledger": led, "links": state_links, "last_exec_ms": 0, "seen_exec": []}
    return _mk(mod, tmp_path, _plan(now), state, ex, tag), ex


def _exit_links(r):
    return [rec["payload"]["orderLinkId"] for rec in r.logs
            if rec.get("op") == "market_exit"]


def _new_exits(r, n0):
    """market_exit links sent after log position n0 (logs accumulate per cycle)."""
    return _exit_links(r)[n0:]


def _calm_bar(ex):
    ex.process_bar(SYM, PX, PX + 10, PX - 10, PX, ex._now_ms + 60_000)


def _protection_snapshot(r, ex, pid):
    pc = r.state["ledger"].get(pid, {})
    qty = float(pc.get("qty", 0.0) or 0.0)
    if qty <= 0:
        return "flat"
    rest = set(ex.orders)
    if pid + "T" in rest and pid + "S" in rest:
        return "protected"
    if pc.get("exit_link") in rest:
        return "exit_inflight"
    return "BARE"


# ----------------------------------------------------------------------------
# with-fix: all three exits complete within <= 2 cycles, never bare, no double
# ----------------------------------------------------------------------------
def test_all_exits_complete_with_fix(tmp_path):
    r, ex = _seed(run_fix, tmp_path, "with")
    assert mirror.exits  # sanity
    r.cycle()  # cycle 1: all three market exits sent, none cancelled
    sent = _exit_links(r)
    assert len(sent) == 3, [rec.get("op") for rec in r.logs]
    for link in sent:
        assert link in ex.orders, (link, sorted(ex.orders))
    # in-flight pieces carry the exit instead of S/T (designed, bot_bookgap)
    for pid in ("dA", "dB", "bC"):
        assert _protection_snapshot(r, ex, pid) == "exit_inflight", pid
    _calm_bar(ex)  # next 1m bar: all three markets fill at the open
    r.cycle()  # cycle 2: fills sync -> all flat
    for pid in ("dA", "dB", "bC"):
        assert _protection_snapshot(r, ex, pid) == "flat", (pid, r.state["ledger"][pid])
    assert ex.pos[(SYM, 1)]["qty"] == 0.0
    # exactly one fill per piece, full qty, never over-sold
    by_link = {}
    for e in ex.execs:
        by_link.setdefault(e["orderLinkId"], 0.0)
        by_link[e["orderLinkId"]] += float(e["execQty"])
    assert len(by_link) == 3, by_link
    assert abs(sum(by_link.values()) - 0.04) < 1e-9, by_link
    assert min(ex.pos[(SYM, 1)]["qty"], 0.0) == 0.0


def test_no_bare_cycle_with_fix(tmp_path):
    r, ex = _seed(run_fix, tmp_path, "bare")
    seen = []
    for _ in range(3):
        r.cycle()
        seen.append({pid: _protection_snapshot(r, ex, pid) for pid in ("dA", "dB", "bC")})
        _calm_bar(ex)
        if all(v == "flat" for v in seen[-1].values()):
            break
    assert all(v == "flat" for v in seen[-1].values()), seen
    assert not any(v == "BARE" for snap in seen for v in snap.values()), seen


# ----------------------------------------------------------------------------
# without-fix: exits are cancelled the same cycle and never complete
# ----------------------------------------------------------------------------
def test_exits_never_complete_without_fix(tmp_path):
    mod = nofix_mod()
    r, ex = _seed(mod, tmp_path, "without")
    r.cycle()  # sends 3 market exits, then diff cancels all 3 same-cycle
    sent = _exit_links(r)
    assert len(sent) == 3
    cancels = {rec["link"] for rec in r.logs if rec.get("op") == "cancel"}
    assert set(sent) <= cancels, (sent, cancels)
    assert not any(link in ex.orders for link in sent)
    for _ in range(3):
        _calm_bar(ex)
        r.cycle()
    for pid in ("dA", "dB", "bC"):
        assert float(r.state["ledger"][pid]["qty"]) > 0, pid  # still open
    assert [e for e in ex.execs if e["orderLinkId"] in sent] == []  # never filled
    assert any(_protection_snapshot(r, ex, pid) == "BARE" for pid in ("dA", "dB", "bC"))


def test_identity_patch_matches_nofix_module(tmp_path, monkeypatch):
    # cb14cb7 is purely additive, so the current tree with the filter patched to
    # identity must behave exactly like the tmp/run_nofix.py module copy.
    monkeypatch.setattr(run_fix, "_acts_without_exit_cancel", lambda acts, led: acts)
    r1, ex1 = _seed(run_fix, tmp_path, "patched")
    r1.cycle()
    r2, ex2 = _seed(nofix_mod(), tmp_path, "copymod")
    r2.cycle()
    got1 = sorted((rec.get("op"), rec.get("link")) for rec in r1.logs
                  if rec.get("op") in ("cancel", "place"))
    got2 = sorted((rec.get("op"), rec.get("link")) for rec in r2.logs
                  if rec.get("op") in ("cancel", "place"))

    def _norm(rows):
        # exit links embed t36(now-minute); both runs share the wall-clock minute
        # in practice, but normalise defensively to (op, class) for exits.
        out = []
        for op, link in rows:
            if link and ("X" in str(link)):
                out.append((op, "EXIT"))
            else:
                out.append((op, link))
        return sorted(out)

    assert _norm(got1) == _norm(got2), (got1, got2)
    assert _exit_links(r1) and _exit_links(r2)


# ----------------------------------------------------------------------------
# (d) restart between send and fill
# ----------------------------------------------------------------------------
def _restart(mod, tmp_path, r, ex, tag):
    state = json.loads((r.dir / "state.json").read_text(encoding="utf-8"))
    return _mk(mod, tmp_path, json.loads(r.plan_path.read_text(encoding="utf-8")),
               state, ex, tag)


def test_restart_keeps_exit_with_fix(tmp_path):
    r, ex = _seed(run_fix, tmp_path, "r1", pieces=("dA",))
    r.cycle()
    (link,) = _exit_links(r)
    assert link in ex.orders
    r2 = _restart(run_fix, tmp_path, r, ex, "r2")
    acts = r2.cycle()  # restart BEFORE the fill bar
    assert link in ex.orders, "restart must not cancel the in-flight exit"
    assert not [a for a in acts if a.get("op") == "cancel"
                and a.get("link") == link]
    assert _exit_links(r2) == [], "no duplicate exit while one is in flight"
    _calm_bar(ex)
    r3 = _restart(run_fix, tmp_path, r2, ex, "r3")
    r3.cycle()
    assert float(r3.state["ledger"]["dA"]["qty"]) == 0.0


def test_restart_cancels_exit_without_fix(tmp_path):
    mod = nofix_mod()
    r, ex = _seed(mod, tmp_path, "n1", pieces=("dA",))
    r.cycle()
    (link,) = _exit_links(r)
    assert link not in ex.orders  # already cancelled same-cycle pre-restart
    r2 = _restart(mod, tmp_path, r, ex, "n2")
    r2.cycle()
    assert float(r2.state["ledger"]["dA"]["qty"]) > 0


# ----------------------------------------------------------------------------
# (e) partially filled market exit: no cancel, no re-send, completes, no double
# ----------------------------------------------------------------------------
def test_partial_fill_completes_with_fix(tmp_path):
    r, ex = _seed(run_fix, tmp_path, "p1", pieces=("dA",), rest_protection=False)
    r.cycle()
    (link,) = _exit_links(r)
    full = float(r.state["ledger"]["dA"]["qty"])
    rest = ex.manual_partial(link, full / 2, PX, ex._now_ms + 30_000)
    assert abs(rest - full / 2) < 1e-12
    n0 = len(_exit_links(r))
    r.cycle()  # syncs the half fill; exit remainder must survive, no re-send
    pc = r.state["ledger"]["dA"]
    assert abs(float(pc["qty"]) - full / 2) < 1e-9
    assert link in ex.orders, "partially filled exit must not be cancelled"
    assert _new_exits(r, n0) == [], "no duplicate exit while the remainder is in flight"
    _calm_bar(ex)
    r.cycle()
    assert float(r.state["ledger"]["dA"]["qty"]) == 0.0
    got = sum(float(e["execQty"]) for e in ex.execs if e["orderLinkId"] == link)
    assert abs(got - full) < 1e-9, (got, full)
    assert ex.pos[(SYM, 1)]["qty"] >= 0.0


# ----------------------------------------------------------------------------
# live/testnet review: stale exits neither block re-sends nor over-sell
# ----------------------------------------------------------------------------
def test_stale_exit_resends_after_inflight(tmp_path):
    # accepted exit that will never fill (externally gone) must not block a
    # re-send past EXIT_INFLIGHT_MIN.
    r, ex = _seed(run_fix, tmp_path, "s1", pieces=("dA",), rest_protection=False)
    r.cycle()
    (link,) = _exit_links(r)
    ex.orders.pop(link, None)  # exchange lost it, no fill will ever come
    pc = r.state["ledger"]["dA"]
    pc["exit_sent"] = str(pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5))
    n0 = len(_exit_links(r))
    r.cycle()
    resent = _new_exits(r, n0)
    assert len(resent) == 1
    assert resent[0] in ex.orders
    _calm_bar(ex)
    r.cycle()
    assert float(r.state["ledger"]["dA"]["qty"]) == 0.0


def test_resend_replaces_stale_resting_exit(tmp_path):
    # stale exit still resting + inflight marker expired -> the cycle sends a new
    # link; diff cancels the replaced (now-unreferenced) old link, so at most
    # one market exit rests per piece after the re-send cycle.
    r, ex = _seed(run_fix, tmp_path, "s2", pieces=("dA",), rest_protection=False)
    r.cycle()
    (link,) = _exit_links(r)
    assert link in ex.orders
    # pretend the first send happened in an earlier wall-clock minute (link ids
    # embed t36(now-minute); backdating exit_sent alone would collide with the
    # re-send id inside one test minute).
    renamed = link + "0"
    ex.orders[renamed] = ex.orders.pop(link)
    r.state["links"][renamed] = r.state["links"].pop(link)
    r.state["ledger"]["dA"]["exit_link"] = renamed
    r.state["ledger"]["dA"]["exit_sent"] = str(
        pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5))
    n0 = len(_exit_links(r))
    r.cycle()
    new = _new_exits(r, n0)
    assert len(new) == 1
    assert renamed not in ex.orders, "replaced exit must be cancelled on re-send"
    assert new[0] in ex.orders
    _calm_bar(ex)
    r.cycle()
    assert float(r.state["ledger"]["dA"]["qty"]) == 0.0


def test_double_market_never_oversells(tmp_path):
    # two resting reduce-only markets for one piece (stale + re-sent, e.g. a
    # cancel that never confirmed): both fill in one bar, position floors at 0.
    r, ex = _seed(run_fix, tmp_path, "m1", pieces=("dA",), rest_protection=False)
    r.cycle()
    (link,) = _exit_links(r)
    qty = float(r.state["ledger"]["dA"]["qty"])
    extra = {"symbol": SYM, "side": "Sell", "orderType": "Market", "qty": str(qty),
             "reduceOnly": True, "orderLinkId": "staleX1", "positionIdx": 1,
             "t_ms": ex._now_ms - 300_000}
    ex.orders["staleX1"] = dict(extra)
    ex.process_bar(SYM, PX, PX + 10, PX - 10, PX, ex._now_ms + 60_000)
    r.cycle()
    assert ex.pos[(SYM, 1)]["qty"] == 0.0
    assert ex.pos[(SYM, 1)]["qty"] >= 0.0
    got = sum(float(e["execQty"]) for e in ex.execs)
    assert abs(got - qty) < 1e-9, got  # second market capped at the remainder (0)
    assert float(r.state["ledger"]["dA"]["qty"]) == 0.0
