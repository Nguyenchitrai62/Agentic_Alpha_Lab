"""bot_exitstuck (2026-10-08): time-exit market orders re-sent for hours without filling.

Root cause (code-cited, see research/diagnostics/bot_exitstuck/ROOT_CAUSE.md):
paper/mock fill rule (bot/paper.py `_minute`, tests/mock_bybit_v5.py
`process_bar`, tests/soak_bot.py replay) fills an order only in a minute that
STARTS after placement (`o t_ms < bar t`), and the soak replays newly closed
bars AFTER the runner cycle. A market exit placed at 19:00:00 therefore needs
the 19:01 bar, which is processed after the 19:02:00 cycle's check -- but the
pre-fix runner re-sent a new exit as soon as EXIT_INFLIGHT_MIN (2 min, expired:
bot/mirror.py `_market_inflight`) and cancelled the predecessor in the same
cycle (have() was polled AFTER the exits loop, and `_acts_without_exit_cancel`
kept only the newest exit_link). Every 2 min the previous X-link was cancelled
before its fill bar was ever processed: deterministic cancel-before-fill
livelock (soak_flush_base: 3532 exit_resend_overflow, 4 ETH pieces x 0.11 stuck
5 h; paper_d17bfg2 d3SOL 27 sends). On the REAL exchange (Bybit V5) a market
fills immediately or is rejected and never rests, so waiting for the resting
exit (never cancelling a market that may already be filled) is also the
correct live behaviour.

The fix (bot/run.py): poll have() BEFORE the exits loop, skip re-sending while
the piece's exit_link still rests (`_exit_resting` -> op=exit_wait), and keep
every state-known reduce (X/D/U) link of an open piece out of diff cancels.
Re-sends still happen when the old exit is GONE (filled/rejected/lost).

The dust_skip side observation: the 0.11 ETH piece WAS protected (TP+SL
placed); the per-cycle dust_skip for link d0ETH25hgr50E is the 0.01 remainder
(planned 0.12 - filled 0.11 = 0.009999999999999995 < 0.01 lot, rounds DOWN to
0 in bot/bybit_v5.py `round_step`) re-wanted every cycle while its rung is
active. Harmless log spam, no trading effect; pinned by a test, not changed.

Mock / paper only. No network, no keys.
"""

import torch  # noqa: F401  (Windows DLL load order: torch before pandas)

import json
import uuid
from dataclasses import asdict
from pathlib import Path

import pandas as pd

import bot.run as run_fix
from bot import mirror
from bot.run import _acts_without_exit_cancel, _exit_resting

SYM = "BTCUSDT"
PX = 80000.0
INST = {"BTCUSDT": dict(qty_step="0.001", min_qty="0.001", min_notional="5", tick="0.1")}


# ----------------------------------------------------------------------------
# deterministic paper-rule exchange (same matching as bot/paper.py)
# ----------------------------------------------------------------------------
class DetExchange:
    def __init__(self, equity=10000.0):
        self.inst_map = dict(INST)
        self.cash = float(equity)
        self.orders = {}
        self.pos = {}
        self.execs = []
        self.px = {SYM: PX}
        self.last5map = {}
        self._now_ms = 1_700_000_000_000

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
        o = dict(p, t_ms=self._now_ms)
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
            if x.get("orderType") == "Market":
                self._fill(k, x, qty, o, t_ms)
            else:
                px = float(x["price"])
                if (x["side"] == "Buy" and l < px) or (x["side"] == "Sell" and h > px):
                    self._fill(k, x, qty, px, t_ms)
                else:
                    continue
            self.orders.pop(k, None)


def _mk(tmp_path, plan, state, ex, tag):
    d = tmp_path / f"exs_{tag}"
    d.mkdir(parents=True, exist_ok=True)
    pf = d / "plan.json"
    pf.write_text(json.dumps(plan, default=str))
    r = run_fix.Runner.__new__(run_fix.Runner)
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


def _seed(tmp_path, tag):
    now = pd.Timestamp.now(tz="UTC")
    led = {"dA": dict(kind="dip", phase=0, symbol=SYM, side=1, qty=0.01, entry=78000.0,
                       tp=78780.0, stop5=70000.0, backstop=69000.0,
                       t_exit=str(now - pd.Timedelta(minutes=5)),
                       frac=0.05, dist=0.04, opened=str(now - pd.Timedelta(hours=5)))}
    ex = DetExchange()
    ex.seed_pos(SYM, 1, 0.01, 79000.0)
    ex.last5map[SYM] = (now - pd.Timedelta(minutes=20), 74800.0)  # above stop5: time exit only
    plan = {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {SYM: {"price": PX, "subs": [], "dips": []}}}
    state = {"ledger": led, "links": {}, "last_exec_ms": 0, "seen_exec": []}
    return _mk(tmp_path, plan, state, ex, tag), ex


def _market_exits(r):
    return [rec["payload"]["orderLinkId"] for rec in r.logs
            if rec.get("op") == "market_exit"]


# ----------------------------------------------------------------------------
# helper unit tests
# ----------------------------------------------------------------------------
def test_exit_resting_helper():
    assert _exit_resting({"exit_link": "dAX1"}, {"dAX1": {}}) == "dAX1"
    assert _exit_resting({"exit_link": "dAX1"}, {"other": {}}) is None
    assert _exit_resting({"exit_link": None}, {"dAX1": {}}) is None
    assert _exit_resting({}, {"dAX1": {}}) is None
    assert _exit_resting(None, {"dAX1": {}}) is None
    assert _exit_resting({"exit_link": "dAX1"}, None) is None


def test_keep_covers_older_reduce_links_of_open_pieces():
    # post-restart pre-fix state: two resting X-links for one open piece; the
    # filter must keep BOTH (cancelling either risks killing a live fill).
    led = {"dA": dict(symbol=SYM, side=1, qty=0.01, kind="dip", exit_link="dAXnew"),
           "dB": dict(symbol=SYM, side=1, qty=0.0, kind="dip", exit_link="dBX")}
    links = {"dAXnew": {"order": {"kind": "reduce", "piece": "dA"}},
             "dAXold": {"order": {"kind": "reduce", "piece": "dA"}},
             "dBXdust": {"order": {"kind": "reduce", "piece": "dB"}},
             "dAT": {"order": {"kind": "tp", "piece": "dA"}}}
    acts = [dict(op="cancel", link=k, symbol=SYM)
            for k in ("dAXnew", "dAXold", "dBXdust", "dAT", "zzz")]
    kept = _acts_without_exit_cancel(acts, led, links)
    kept_links = {a["link"] for a in kept if a["op"] == "cancel"}
    assert "dAXnew" not in kept_links
    assert "dAXold" not in kept_links  # older reduce link of an OPEN piece: kept
    assert "dBXdust" in kept_links  # closed piece: may be cancelled
    assert "dAT" in kept_links and "zzz" in kept_links
    # backwards compatible: links omitted behaves like cb14cb7
    kept2 = _acts_without_exit_cancel(
        [dict(op="cancel", link="dAXnew", symbol=SYM)], led)
    assert kept2 == []


# ----------------------------------------------------------------------------
# fixed-runner behaviour: wait, fill exactly once, resend only when gone
# ----------------------------------------------------------------------------
def test_no_resend_while_exit_rests(tmp_path):
    # the soak signature: first exit sent, still resting, inflight marker
    # expired -> the fixed runner waits (exit_wait), never re-sends nor
    # cancels. Pre-fix code sent a new link and cancelled the old one here.
    r, ex = _seed(tmp_path, "wait")
    r.cycle()
    (link,) = _market_exits(r)
    assert link in ex.orders
    r.state["ledger"]["dA"]["exit_sent"] = str(
        pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5))
    n0 = len(_market_exits(r))
    acts = r.cycle()
    assert _market_exits(r)[n0:] == [], "no duplicate exit while one rests"
    assert link in ex.orders, "resting exit must not be cancelled"
    assert not [a for a in acts
                if a.get("op") == "cancel" and a.get("link") == link]
    assert any(rec.get("op") == "exit_wait" and rec.get("piece") == "dA"
               for rec in r.logs)


def test_first_exit_fills_and_piece_flats(tmp_path):
    r, ex = _seed(tmp_path, "fill")
    r.cycle()
    (link,) = _market_exits(r)
    ex.process_bar(SYM, PX, PX + 10, PX - 10, PX, ex._now_ms + 60_000)
    r.cycle()
    assert float(r.state["ledger"]["dA"]["qty"]) == 0.0
    assert len(_market_exits(r)) == 1, "exactly one send for one exit"
    assert ex.pos[(SYM, 1)]["qty"] == 0.0


def test_resend_when_old_exit_gone(tmp_path):
    # check-status-before-resend: the old exit is nowhere on the exchange
    # (filled externally / rejected / lost) and the marker is stale -> one
    # re-send is allowed.
    r, ex = _seed(tmp_path, "gone")
    r.cycle()
    (link,) = _market_exits(r)
    ex.orders.pop(link, None)
    r.state["ledger"]["dA"]["exit_sent"] = str(
        pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=5))
    n0 = len(_market_exits(r))
    r.cycle()
    new = _market_exits(r)[n0:]
    assert len(new) == 1
    assert new[0] in ex.orders
    ex.process_bar(SYM, PX, PX + 10, PX - 10, PX, ex._now_ms + 60_000)
    r.cycle()
    assert float(r.state["ledger"]["dA"]["qty"]) == 0.0


# ----------------------------------------------------------------------------
# deterministic reproduction of the pre-fix livelock under paper fill timing
# ----------------------------------------------------------------------------
def _paper_livelock_sim(resend_while_resting: bool):
    """Step 20 s cycles over minute bars with the paper rule (an order fills
    only in a bar with bar_t > t_place, processed after the cycle check).

    Returns (fills, sends). Pre-fix policy (resend_while_resting=True: cancel
    the predecessor and send a new exit every 2 min while one rests) starves;
    the fixed policy completes on the first exit.
    """
    resting, sends, fills = {}, 0, 0
    placed_min = None

    def place(t):
        nonlocal sends, placed_min
        sends += 1
        placed_min = t
        resting["X"] = t

    place(0.0)
    t = 0.0
    while t < 10 * 60:
        t += 20.0
        if resting and resend_while_resting and t - resting["X"] >= 120.0:
            del resting["X"]  # cancel predecessor before its fill bar
            place(t)
        # process newly closed bars (bar_t + 60 <= t), fill eligible resting
        bar_t = (t // 60) * 60 - 60
        if resting and bar_t > resting["X"]:
            fills += 1
            resting.clear()
            break
    return fills, sends


def test_prefixed_resend_loop_starves_but_waiting_completes():
    fills_old, sends_old = _paper_livelock_sim(resend_while_resting=True)
    assert fills_old == 0 and sends_old >= 4, (fills_old, sends_old)
    fills_new, sends_new = _paper_livelock_sim(resend_while_resting=False)
    assert (fills_new, sends_new) == (1, 1)


# ----------------------------------------------------------------------------
# dust_skip side observation: pinned explanation, no behaviour change
# ----------------------------------------------------------------------------
def test_dust_skip_is_the_float_remainder_not_the_open_piece():
    eth = dict(qty_step="0.01", min_qty="0.01", min_notional="5", tick="0.01")
    # soak evidence: planned 0.12, filled 0.11 -> remainder 0.00999... < 1 lot
    # (round_step DOWN gives 0, so it can never rest; the guard logs every cycle
    # while the rung is active).
    assert mirror.entry_is_dust(0.12 - 0.11, 4158.97, 3672.96, eth) is True
    # the open 0.11 piece itself is protectable (its TP/SL did rest).
    assert mirror.entry_is_dust(0.11, 4158.97, 3672.96, eth) is False
    assert mirror.protection_is_dust(0.11, 4158.97, 3672.96, eth) is False
