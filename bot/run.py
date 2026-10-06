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
from bot import carry as carry_mod
from bot import risk_guard
from bot.bybit_v5 import (
    KLINE_CACHE_LOCK_WARN_S,
    MAINNET,
    TESTNET,
    Bybit,
    BybitError,
    cached_call,
    pop_kline_lock_stats,
    round_step,
)
from bot.paper import PaperExchange

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "artifacts/research/advisor_shadow/trade_plan_v376.json"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
STALE_PLAN = pd.Timedelta(hours=4, minutes=30)  # a 4h plan is valid until the next bar plan (+ generation delay)
# Cycle instrumentation (bot_cycletime): wall-time budget per stage. Thresholds
# match the assignment: slow_cycle > 60 s, lock_wait > 10 s (cache-lock wait).
SLOW_CYCLE_S = 60.0
LOCK_WAIT_WARN_S = float(KLINE_CACHE_LOCK_WARN_S)


def _cycle_now() -> float:
    """Monotonic clock for cycle timing (patched with fake clocks in tests)."""
    return time.perf_counter()


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
    if o.reduce_only:
        # TP / reduce / close limits stay GTC (reduce-only, may take on touch).
        p.update(orderType="Limit", price=price, timeInForce="GTC")
        p["reduceOnly"] = True
    else:
        # Book entries / adds and dip rung bids are PostOnly (maker-only, as the
        # research fill rule and the paper exchange assume). A crossing limit is
        # rejected by the exchange instead of taking (see postonly_reject: retry
        # next cycle at the same price, never convert to market/taker).
        p.update(orderType="Limit", price=price, timeInForce="PostOnly")
    return p


def _is_postonly_reject_msg(msg: str) -> bool:
    """True when an exchange error message means a PostOnly order would cross.

    Bybit V5 rejects a PostOnly limit that would take immediately ( maker-only ).
    Known signals: the words postonly / post-only, or retCodes 110079 / 170146.
    """
    try:
        m = str(msg).lower()
    except Exception:
        return False
    if "postonly" in m or "post-only" in m or "post only" in m:
        return True
    if "110079" in m or "170146" in m:
        return True
    return False


class Runner:
    def __init__(self, mode: str, plan_path: Path, equity: float | None, risk_mult: float = 1.0, corr: bool = False,
                 tag: str | None = None, dip_mult: float = 1.0, bear_book: bool = False,
                 dip_cooldown_h: float = 0.0, dip_sl_coin: dict | None = None, dip_gross_cap: float | None = None,
                 adopt_fresh: bool = False, no_risk_guard: bool = False, carry_f: float = 0.0):
        self.mode, self.plan_path = mode, plan_path
        self.risk_mult, self.corr, self.tag, self.dip_mult = float(risk_mult), bool(corr), tag or None, float(dip_mult)
        self.bear_book = bool(bear_book)
        self.adopt_fresh = bool(adopt_fresh)
        self.no_risk_guard = bool(no_risk_guard)
        try:
            self.carry_f = float(carry_f or 0.0)
        except (TypeError, ValueError):
            self.carry_f = 0.0
        self.dip_cooldown_h = float(dip_cooldown_h or 0.0)
        self.dip_sl_coin = dict(dip_sl_coin or {})
        try:
            self.dip_gross_cap = float(dip_gross_cap or 0.0)
        except (TypeError, ValueError):
            self.dip_gross_cap = 0.0
        self._bear_at = None
        self._bear = False
        self._last_plan = None
        self._skip_logged = {}
        self._kline_cache_dir_override = None
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
            res = fn(*a, **kw)
            if res is None and getattr(fn, "__name__", "") == "place" and a and isinstance(a[0], dict):
                # Paper PostOnly reject returns None (no exception): a crossing
                # PostOnly limit is rejected maker-only (bot/paper.py). Retry next
                # cycle at the same price; never convert to market/taker.
                pay = a[0]
                if pay.get("timeInForce") == "PostOnly":
                    self.log(dict(op="postonly_reject", link=pay.get("orderLinkId"), symbol=pay.get("symbol"),
                                  price=pay.get("price")))
            return res
        except (BybitError, OSError) as e:
            pay = a[0] if a and isinstance(a[0], dict) else {}
            if isinstance(pay, dict) and pay.get("timeInForce") == "PostOnly" and _is_postonly_reject_msg(str(e)):
                self.log(dict(op="postonly_reject", link=pay.get("orderLinkId"), symbol=pay.get("symbol"),
                              price=pay.get("price"), note=str(e)[:200]))
                return None
            self.log(dict(op="error", call=getattr(fn, "__name__", "?"), note=str(e)))
            return None

    def _guard_prices(self, lc, last5d, plan) -> dict:
        """Last prices for the pre-trade guard: closed 1m closes (lc) falling
        back to 5m closes (last5) and plan coin marks. No extra network calls."""
        prices: dict = {}
        try:
            if isinstance(lc, dict):
                for s, v in lc.items():
                    try:
                        if v is not None:
                            prices[s] = float(v)
                    except (TypeError, ValueError):
                        continue
        except (AttributeError, TypeError):
            pass
        try:
            if isinstance(last5d, dict):
                for s, v in last5d.items():
                    if s in prices:
                        continue
                    try:
                        prices[s] = float(v[1])
                    except (TypeError, ValueError, IndexError):
                        continue
        except (AttributeError, TypeError):
            pass
        try:
            for s, c in ((plan or {}).get("coins") or {}).items():
                if s in prices:
                    continue
                try:
                    px = c.get("price") if isinstance(c, dict) else None
                    if px is not None:
                        prices[s] = float(px)
                except (TypeError, ValueError, AttributeError):
                    continue
        except (AttributeError, TypeError):
            pass
        return prices

    def _apply_risk_guard(self, want: dict, equity: float, prices: dict):
        """Filter `want` through risk_guard.check (defaults: per-coin 2.5x, dip
        2.0x, total 4x, single 1x). Rejects are logged op=risk_reject and not
        sent; protection / reduce-only orders are never blocked by check()."""
        try:
            allowed, rejected = risk_guard.check(want, self.state.get("ledger"), equity, prices)
        except Exception as e:  # guard must never crash the cycle; fail closed for entries
            self.log(dict(op="risk_reject", link=None, symbol=None, reason=f"guard_error:{type(e).__name__}"))
            return {k: o for k, o in want.items() if getattr(o, "reduce_only", False)}
        for r in rejected or []:
            try:
                self.log(dict(op="risk_reject", link=r.get("link"), symbol=r.get("symbol"), reason=r.get("reason")))
            except (AttributeError, TypeError):
                self.log(dict(op="risk_reject", link=None, symbol=None, reason="bad_reject"))
        try:
            keep = {id(o) for o in (allowed or [])}
        except Exception:
            keep = set()
        return {k: o for k, o in want.items() if id(o) in keep}

    # ---- bot_carry sleeve (opt-in --carry-f; off by default, zero behaviour change) ----
    def _carry_sync(self):
        """Apply exchange executions of carry links (prefix ``c``) to carry state."""
        try:
            f = float(getattr(self, "carry_f", 0.0) or 0.0)
        except (TypeError, ValueError):
            return
        if not f > 0 or self.mode == "dry":
            return
        try:
            cstate = carry_mod.carry_state(self.state)
        except Exception:
            return
        last = self.state.get("last_exec_ms")
        try:
            start = int(last) if last is not None else int((time.time() - 3600) * 1000)
            ex = self.ex.executions(start)
        except Exception:
            return
        seen = set(self.state.setdefault("seen_exec", [])[-500:])
        for e in sorted(ex, key=lambda r: int(r.get("execTime", 0) or 0)):
            try:
                link = e.get("orderLinkId") or ""
            except AttributeError:
                continue
            if not link.startswith(carry_mod.LINK_PREFIX):
                continue
            try:
                if e["execId"] in seen:
                    continue
            except KeyError:
                continue
            try:
                rec = carry_mod.note_exec(cstate, link, float(e.get("execQty", 0)), float(e.get("execPrice", 0)))
            except Exception:
                continue
            seen.add(e["execId"])
            if rec is not None:
                self.log(rec)
            try:
                self.state["last_exec_ms"] = max(int(self.state.get("last_exec_ms") or 0), int(e["execTime"]))
            except (TypeError, ValueError):
                pass
        self.state["seen_exec"] = list(seen)

    def _carry_round(self, p: dict):
        """Rounded carry payload or None when below lot / notional minimums."""
        try:
            sym = p.get("symbol")
            qty = float(p.get("qty", 0))
            if not qty > 0:
                return None
        except (TypeError, ValueError, AttributeError):
            return None
        it = self.inst.get(sym)
        if it is None and sym:
            # Dated quarterly (e.g. BTCUSD_...): fall back to the coin's perp lot.
            try:
                pre = str(sym).upper()
            except Exception:
                pre = ""
            for cs in SYMS:
                if pre.startswith(cs[:-4]):
                    it = self.inst.get(cs)
                    break
        if it is None:
            return dict(p, qty=str(qty))
        out = dict(p)
        try:
            out["qty"] = round_step(qty, it["qty_step"])
            if float(out["qty"]) < float(it["min_qty"]) - 1e-12:
                return None
        except (TypeError, ValueError, KeyError):
            return None
        if p.get("orderType") == "Limit" and p.get("price") is not None:
            try:
                up = p.get("side") == "Sell"
                out["price"] = round_step(float(p["price"]), it["tick"], up=up)
            except (TypeError, ValueError, KeyError):
                return None
            if not p.get("reduceOnly") and float(out["qty"]) * float(out["price"]) < float(it["min_notional"]) - 1e-9:
                return None
        return out

    def _carry_cycle(self, now, equity: float, prices: dict):
        """One carry pass: sync fills, decide (frozen rule), guard, place. Returns acts."""
        try:
            f = float(getattr(self, "carry_f", 0.0) or 0.0)
        except (TypeError, ValueError):
            return []
        if not f > 0:
            return []
        self._carry_sync()
        try:
            cstate = carry_mod.carry_state(self.state)
        except Exception:
            return []
        # Test seam: injected contracts/quotes (no network in unit tests).
        contracts = getattr(self, "_carry_contracts_override", None)
        quotes = getattr(self, "_carry_quotes_override", None)
        if contracts is None:
            try:
                pub = getattr(self.ex, "pub", self.ex)
                contracts = carry_mod.fetch_contracts(pub)
            except Exception:
                contracts = {}
        if quotes is None:
            try:
                pub = getattr(self.ex, "pub", self.ex)
                quotes = carry_mod.fetch_quotes(pub, contracts)
            except Exception:
                quotes = {}
        try:
            want, logs = carry_mod.decide(now, equity, f, cstate, contracts or {}, quotes or {})
        except Exception as e:
            self.log(dict(op="carry_error", note=f"{type(e).__name__}: {e}"[:200]))
            return []
        for rec in logs or []:
            try:
                self.log(dict(rec))
            except Exception:
                pass
        if not want:
            return []
        try:
            allowed, rejected = carry_mod.guard_carry(want, self.state.get("ledger"), equity, prices or {})
        except Exception as e:
            self.log(dict(op="risk_reject", link=None, symbol=None, reason=f"carry_guard_error:{type(e).__name__}"))
            return []
        for r in rejected or []:
            try:
                self.log(dict(op="risk_reject", link=r.get("link"), symbol=r.get("symbol"), reason=r.get("reason")))
            except (AttributeError, TypeError):
                pass
        if not allowed:
            return []
        acts = []
        skipped = []
        for p in allowed:
            try:
                link = p.get("orderLinkId")
            except AttributeError:
                continue
            rp = self._carry_round(p)
            if rp is None:
                skipped.append(link)
                continue
            self.log(dict(op="place", payload=rp, carry=True))
            try:
                # Bybit.place hardcodes category="linear" (dict(category=..,
                # **o) raises on a category key), so signed clients go via
                # post() with the carry category; paper/fake exchanges keep
                # the category inside the payload (paper fills branch on it).
                if isinstance(self.ex, Bybit):
                    cat = rp.get("category", "linear")
                    body = {k: v for k, v in rp.items() if k != "category"}
                    body["category"] = cat
                    res = self.send(self.ex.post, "/v5/order/create", body)
                else:
                    res = self.send(self.ex.place, rp)
            except Exception:
                continue
            if res is not None or self.mode == "dry":
                self.state.setdefault("links", {})[link] = dict(order=dict(link=link), carry_payload=rp)
                acts.append(dict(op="place", payload=rp))
        self._log_skipped([s for s in skipped if s], now, equity)
        return acts


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
            if link.startswith(carry_mod.LINK_PREFIX):
                continue  # bot_carry: handled by _carry_sync (carry.note_exec), not the book/dip ledger
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

    def _kline_cache_dir(self):
        return getattr(self, "_kline_cache_dir_override", None)

    def _skip_bar(self, now) -> str:
        try:
            return str(pd.Timestamp(now).floor("4h"))
        except (TypeError, ValueError):
            return str(now)

    def _log_skipped(self, skipped, now, equity) -> None:
        """Log skipped_below_minimum once per (link, 4h bar); repeats in the same bar are dropped."""
        if not skipped:
            return
        bar = self._skip_bar(now)
        seen = getattr(self, "_skip_logged", None)
        if not isinstance(seen, dict):
            seen = self._skip_logged = {}
        new = []
        for k in skipped:
            key = (str(k), bar)
            if key not in seen:
                new.append(k)
            seen[key] = True
        if len(seen) > 2000:  # bound memory: keep the current bar only
            for key in list(seen):
                if key[1] != bar:
                    del seen[key]
        if new:
            self.log(dict(op="skipped_below_minimum", links=new, equity=equity))

    def last_close_1m(self) -> dict:
        """Last CLOSED 1m close per symbol (for correlation-aware dip sizing). Paper: the simulated exchange's
        last_close; testnet / live / dry: Bybit public klines (interval 1, limit 2, take the closed bar),
        shared across runners via the on-disk kline cache (TTL 20 s)."""
        if self.mode == "paper":
            try:
                return {s: float(v) for s, v in self.ex.s.get("last_close", {}).items() if v is not None}
            except (AttributeError, TypeError, ValueError):
                return {}
        out: dict = {}
        for s in SYMS:
            def _fetch(s=s):
                k = self.ex.klines(s, "1", 2)  # newest first: [0] = bar in progress, [1] = last closed bar
                if len(k) > 1:
                    return float(k[1][4])
                raise ValueError("no closed 1m bar")
            try:
                val, _hit = cached_call(s, "close_1m", _fetch, cache_dir=self._kline_cache_dir())
            except Exception:
                continue
            try:
                out[s] = float(val)
            except (TypeError, ValueError):
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
            if fn is None:
                opens = []
            else:
                opens, _hit = cached_call("BTCUSDT", "opens_4h", lambda: fn("BTCUSDT"),
                                          cache_dir=self._kline_cache_dir())
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

    def _cycle_timing_start(self):
        """Init per-cycle wall-time buckets; resets the kline-lock wait baseline."""
        try:
            pop_kline_lock_stats()
        except Exception:
            pass
        try:
            t0 = _cycle_now()
        except Exception:
            t0 = 0.0
        return t0, {"plan_ms": 0.0, "kline_ms": 0.0, "sync_ms": 0.0,
                    "decide_ms": 0.0, "order_ms": 0.0, "state_ms": 0.0}

    def _store_cycle_timing(self, stages, t_all):
        """Write last_cycle_ms + per-stage ms into state.json; log slow/lock.

        Two state writes: a provisional write (so a crash still leaves a
        heartbeat with timing keys) then a final rewrite with the measured
        state_ms included. Trading behaviour is unchanged: orders/logs before
        this point are bit-for-bit identical; only slow (>60 s) or lock-wait
        (>10 s) cycles append one extra op=slow_cycle / op=lock_wait action.
        """
        if not isinstance(stages, dict):
            stages = {"plan_ms": 0.0, "kline_ms": 0.0, "sync_ms": 0.0,
                      "decide_ms": 0.0, "order_ms": 0.0, "state_ms": 0.0}
        t_s0 = _cycle_now()
        try:
            self.state["last_cycle_ms"] = round(float((_cycle_now() - t_all) * 1000.0), 1)
            self.state["last_cycle_stages_ms"] = {k: round(float(v), 1) for k, v in stages.items()}
        except Exception:
            pass
        try:
            self.state_f.write_text(json.dumps(self.state, indent=1, default=str))
        except Exception:
            pass
        if self.mode == "paper":
            try:
                self.ex.save()
            except Exception:
                pass
        try:
            state_ms = (_cycle_now() - t_s0) * 1000.0
        except Exception:
            state_ms = 0.0
        try:
            stages["state_ms"] = float(stages.get("state_ms", 0.0)) + float(state_ms)
            total_ms = (_cycle_now() - t_all) * 1000.0
        except Exception:
            total_ms = 0.0
        try:
            wait_s, timeouts = pop_kline_lock_stats()
        except Exception:
            wait_s, timeouts = 0.0, 0
        try:
            self.state["last_cycle_ms"] = round(float(total_ms), 1)
            self.state["last_cycle_stages_ms"] = {k: round(float(v), 1) for k, v in stages.items()}
            self.state["last_cycle_lock_wait_ms"] = round(float(wait_s) * 1000.0, 1)
        except Exception:
            pass
        try:
            self.state_f.write_text(json.dumps(self.state, indent=1, default=str))
        except Exception:
            pass
        try:
            if float(total_ms) > SLOW_CYCLE_S * 1000.0:
                self.log(dict(op="slow_cycle", total_ms=round(float(total_ms), 1),
                              stages={k: round(float(v), 1) for k, v in stages.items()},
                              lock_wait_ms=round(float(wait_s) * 1000.0, 1), timeouts=int(timeouts)))
            if float(wait_s) > float(LOCK_WAIT_WARN_S):
                self.log(dict(op="lock_wait", lock_wait_ms=round(float(wait_s) * 1000.0, 1),
                              timeouts=int(timeouts), total_ms=round(float(total_ms), 1),
                              stages={k: round(float(v), 1) for k, v in stages.items()}))
        except Exception:
            pass
        return total_ms

    def cycle(self):
        t_all, _stages = self._cycle_timing_start()
        now = pd.Timestamp.now(tz="UTC")
        if getattr(self, "_last_plan", None) is None:
            self._last_plan = None
        plan_ok = True
        _t = _cycle_now()
        try:
            plan = json.loads(self.plan_path.read_text())
            self._last_plan = plan
            _stages["plan_ms"] += (_cycle_now() - _t) * 1000.0
        except (OSError, json.JSONDecodeError, ValueError) as e:
            _stages["plan_ms"] += (_cycle_now() - _t) * 1000.0
            self.log(dict(op="plan_error", note=f"{type(e).__name__}: {e}"))
            if isinstance(self._last_plan, dict):
                plan = self._last_plan
                plan_ok = False
            else:
                # No cached plan: keep protection from the ledger only, place nothing new.
                if self.mode == "paper":
                    _t = _cycle_now()
                    try:
                        self.ex.step(now)
                    except Exception:
                        pass
                    _stages["kline_ms"] += (_cycle_now() - _t) * 1000.0
                _t = _cycle_now()
                try:
                    equity = self.equity_arg if self.mode == "dry" else self.ex.equity_usdt()
                except Exception:
                    equity = self.equity_arg or 0.0
                _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
                _t = _cycle_now()
                try:
                    self.sync_fills()
                except Exception:
                    pass
                _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
                led = self.state["ledger"]
                _t = _cycle_now()
                try:
                    last5 = self.last5()
                except Exception:
                    last5 = {}
                _stages["kline_ms"] += (_cycle_now() - _t) * 1000.0
                _t = _cycle_now()
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
                # PRE-TRADE GUARD (testnet review 2026-10-06 V4): filter `want`
                # before anything is rounded/sent. Protection is reduce-only so
                # check() never blocks it; this insert is a no-op there.
                if not getattr(self, "no_risk_guard", False):
                    try:
                        _lp = last5 if isinstance(last5, dict) else {}
                    except NameError:
                        _lp = {}
                    want = self._apply_risk_guard(want, equity, self._guard_prices(None, _lp, {"coins": {}}))
                rounded, skipped = {}, []
                for k, o in want.items():
                    p = to_exchange(o, self.inst)
                    if p is None:
                        skipped.append(k)
                    else:
                        o = replace(o, qty=float(p["qty"]), price=float(p["price"]) if "price" in p else None,
                                    trigger=float(p["triggerPrice"]) if "triggerPrice" in p else None)
                        rounded[k] = (o, p)
                _stages["decide_ms"] += (_cycle_now() - _t) * 1000.0
                _t = _cycle_now()
                try:
                    have = self.have()
                except Exception:
                    have = {}
                _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
                _t = _cycle_now()
                acts = mirror.diff({k: o for k, (o, _) in rounded.items()}, have)
                _stages["decide_ms"] += (_cycle_now() - _t) * 1000.0
                _t = _cycle_now()
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
                _stages["order_ms"] += (_cycle_now() - _t) * 1000.0
                self._log_skipped(skipped, now, equity)
                if float(getattr(self, "carry_f", 0.0) or 0.0) > 0:
                    _t = _cycle_now()
                    try:
                        _cp = self._guard_prices(None, last5 if isinstance(last5, dict) else {}, {"coins": {}})
                    except NameError:
                        _cp = {}
                    try:
                        acts = list(acts) + list(self._carry_cycle(now, equity, _cp))
                    except Exception:
                        pass
                    _stages["order_ms"] += (_cycle_now() - _t) * 1000.0
                self._store_cycle_timing(_stages, t_all)
                return acts
        stale = now - pd.Timestamp(plan["generated_at"]) > STALE_PLAN
        if self.mode == "paper":
            _t = _cycle_now()
            self.ex.step(now)
            _stages["kline_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        equity = self.equity_arg if self.mode == "dry" else self.ex.equity_usdt()
        _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        self.sync_fills()
        _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
        led = self.state["ledger"]
        live = mirror.plan_book_live(plan)
        for pc in led.values():
            if pc["kind"] == "book" and pc["qty"] > 0:
                if (pc["phase"], pc["symbol"]) in live:
                    pc.pop("plan_gone_since", None)
                else:
                    pc.setdefault("plan_gone_since", str(now))
        _t = _cycle_now()
        try:
            _last5_for_cycle = self.last5()
        except Exception:
            _last5_for_cycle = {}
        _stages["kline_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        for pid, why in mirror.exits(plan, now, led, _last5_for_cycle):
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
        _stages["decide_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        bear = self.bear_now(now)
        _stages["kline_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        lc = self.last_close_1m() if (self.corr or self.bear_book) else None
        _stages["kline_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        _gross = getattr(self, "dip_gross_cap", 0.0) or 0.0
        _adopt = bool(getattr(self, "adopt_fresh", False))
        want = mirror.desired(plan, now, equity, led, risk_mult=self.risk_mult, corr=self.corr,
                              last_close=lc, dip_mult=self.dip_mult,
                              bear_book=self.bear_book, bear=bear,
                              dip_cooldown_h=self.dip_cooldown_h, dip_sl_coin=self.dip_sl_coin,
                              dip_gross_cap=_gross, adopt_fresh=_adopt)
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
        # PRE-TRADE GUARD (testnet review 2026-10-06 V4, exact call site): filter
        # `want` after stale/plan_error trimming and before rounding/diff.
        # Prices = last closed 1m closes (lc) falling back to 5m closes/plan
        # marks; equity = exchange equity. check() never blocks reduce-only
        # exits/protection, so stops/TPs/market exits always pass.
        if not getattr(self, "no_risk_guard", False):
            want = self._apply_risk_guard(want, equity, self._guard_prices(lc, _last5_for_cycle, plan))
        _stages["decide_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        have_before = self.have()
        _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
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
                           amend_entry_qty=(self.corr or self.risk_mult != 1.0 or self.dip_mult != 1.0 or bool(getattr(self, "dip_gross_cap", 0.0))))
        _stages["decide_ms"] += (_cycle_now() - _t) * 1000.0
        failed_stop_pieces, placed_stop_links = set(), set()
        _t = _cycle_now()
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
        self._log_skipped(skipped, now, equity)
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
        _stages["order_ms"] += (_cycle_now() - _t) * 1000.0
        self._log_skipped(skipped, now, equity)
        if float(getattr(self, "carry_f", 0.0) or 0.0) > 0:
            _t = _cycle_now()
            try:
                _cp2 = self._guard_prices(lc, _last5_for_cycle, plan)
            except Exception:
                _cp2 = {}
            try:
                acts = list(acts) + list(self._carry_cycle(now, equity, _cp2))
            except Exception:
                pass
            _stages["order_ms"] += (_cycle_now() - _t) * 1000.0
        self._store_cycle_timing(_stages, t_all)
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
    ap.add_argument("--dip-gross-cap", type=float, default=0.0, metavar="G", help="per-phase dip gross-notional cap: open dip notional + resting dip bids <= G x sub equity (default 0 = off)")
    ap.add_argument("--adopt-fresh", action="store_true", help="adopt a fresh paper book position the bot missed (same limit at the plan entry price inside its 5..65 min window, default off = unchanged)")
    ap.add_argument("--tag", default=None, help="state dir artifacts/bot/<mode>[_<tag>] (default no tag = unchanged paths)")
    ap.add_argument("--no-risk-guard", action="store_true", help="disable the pre-trade risk guard (testnet/live: guard ON by default)")
    ap.add_argument("--risk-guard", action="store_true", help="enable the pre-trade risk guard in paper/dry (default off there so paper stays engine-faithful)")
    ap.add_argument("--carry-f", type=float, default=0.0, metavar="F", help="cash-and-carry sleeve fraction per leg per coin (default 0 = off, orders bit-for-bit unchanged)")
    a = ap.parse_args()
    if a.mode == "live" and os.environ.get("BOT_ALLOW_LIVE") != "yes-real-money":
        sys.exit("live trading is locked: the account owner must set BOT_ALLOW_LIVE=yes-real-money")
    mode_dir = a.mode if not a.tag else f"{a.mode}_{a.tag}"
    (ROOT / "artifacts/bot" / mode_dir).mkdir(parents=True, exist_ok=True)
    _lock = single_instance(ROOT / "artifacts/bot" / mode_dir / "runner.lock") if not a.once else None
    r = Runner(a.mode, Path(a.plan), a.equity, risk_mult=a.risk_mult, corr=a.corr_size, tag=a.tag, dip_mult=a.dip_mult,
             bear_book=a.bear_book, dip_cooldown_h=a.dip_cooldown_h, dip_sl_coin=parse_dip_sl_coin(a.dip_sl_coin),
             dip_gross_cap=a.dip_gross_cap, adopt_fresh=a.adopt_fresh,
             no_risk_guard=a.no_risk_guard or (a.mode in ("paper", "dry") and not a.risk_guard),
             carry_f=a.carry_f)
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
