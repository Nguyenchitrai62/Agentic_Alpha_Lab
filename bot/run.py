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
import copy
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
# Maintenance window (bot_maint): opt-in only. From 30 minutes before the window
# start until the window end the bot places no new dip bids / book entries and
# cancels resting dip bids + unfilled book entry limits. Protection (TP/SL /
# backstops) and carry legs are untouched. Default (no flags, no file): inactive.
MAINT_PRE_MIN = 30.0
# Cycle instrumentation (bot_cycletime): wall-time budget per stage. Thresholds
# match the assignment: slow_cycle > 60 s, lock_wait > 10 s (cache-lock wait).
SLOW_CYCLE_S = 60.0
LOCK_WAIT_WARN_S = float(KLINE_CACHE_LOCK_WARN_S)

# bot_k2flag (2026-10-07): optional Kronos K2 dip-size tilt, default OFF.
# Parquet rows: sym (e.g. BTCUSDT), shift (0..3 clock shift = plan phase),
# T (holding-bar open), k2_mult, mode in {prospective, late, backfill}.
K2_ALLOWED_MODES = ("prospective", "late")
K2_DIP_BAR_OFFSET = pd.Timedelta(minutes=16)


def _k2_norm_sym(coin) -> str:
    """Parquet sym for a plan coin key: BTC -> BTCUSDT, BTCUSDT -> BTCUSDT."""
    try:
        s = str(coin or "").strip().upper()
    except Exception:
        return ""
    return s if s.endswith("USDT") else (s + "USDT" if s else "")


def _k2_norm_T(t):
    """Holding-bar open as a UTC Timestamp (None when unparseable)."""
    if t is None:
        return None
    try:
        ts = pd.Timestamp(t)
    except (TypeError, ValueError, AttributeError):
        return None
    try:
        if pd.isna(ts):
            return None
    except (TypeError, ValueError):
        return None
    try:
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    except (TypeError, ValueError, AttributeError):
        pass
    try:
        if pd.isna(ts):
            return None
    except (TypeError, ValueError):
        return None
    return ts


def _k2_bar_of_dip(d):
    """Holding-bar open T for a plan dip row: active_from - 16 min (None when missing)."""
    try:
        a0 = d.get("active_from")
    except (AttributeError, TypeError):
        return None
    ts = _k2_norm_T(a0)
    if ts is None:
        return None
    try:
        return ts - K2_DIP_BAR_OFFSET
    except (TypeError, ValueError):
        return None


def _k2_load_map(path):
    """Read the K2 parquet once into {(sym, shift, T_ns): (mult, mode)}.

    Raises on missing / locked / unreadable files (caller logs k2_missing).
    Row-level problems never raise: that row simply maps to (1.0, mode).
    """
    df = pd.read_parquet(path, columns=["sym", "shift", "T", "k2_mult", "mode"])
    out: dict = {}
    try:
        syms = list(df["sym"])
        shifts = list(df["shift"])
        ts = list(df["T"])
        mults = list(df["k2_mult"])
        modes = list(df["mode"])
    except (KeyError, TypeError, AttributeError):
        return out
    for s, sh, t, m, mo in zip(syms, shifts, ts, mults, modes):
        try:
            sym = str(s).strip().upper()
        except Exception:
            continue
        try:
            shift = int(sh)
        except (TypeError, ValueError):
            continue
        tn = _k2_norm_T(t)
        if tn is None:
            continue
        try:
            key = (sym, shift, int(tn.value))
        except (TypeError, ValueError, AttributeError):
            continue
        try:
            mf = float(m)
        except (TypeError, ValueError):
            mf = 1.0
        try:
            mode = str(mo).strip().lower() if mo is not None else ""
        except Exception:
            mode = ""
        out[key] = (mf, mode)
    return out


def _k2_mult_for(coin, phase, bar, k2map) -> tuple:
    """(multiplier, mode_str) for one (coin, phase, bar); missing/backfill -> (1.0, mode)."""
    if bar is None or not isinstance(k2map, dict):
        return 1.0, "missing"
    try:
        sym = _k2_norm_sym(coin)
        shift = int(phase)
        key = (sym, shift, int(bar.value))
    except (TypeError, ValueError, AttributeError):
        return 1.0, "missing"
    hit = k2map.get(key)
    if hit is None:
        return 1.0, "missing"
    try:
        mult, mode = hit
    except (TypeError, ValueError):
        return 1.0, "missing"
    try:
        mode_s = str(mode).strip().lower()
    except Exception:
        mode_s = ""
    if mode_s not in K2_ALLOWED_MODES:
        return 1.0, mode_s or "missing"
    try:
        mf = float(mult)
    except (TypeError, ValueError):
        return 1.0, mode_s
    import math as _math
    if not (_math.isfinite(mf) and mf > 0):
        return 1.0, mode_s
    return mf, mode_s


def _cycle_now() -> float:
    """Monotonic clock for cycle timing (patched with fake clocks in tests)."""
    return time.perf_counter()


def _parse_maint_ts(x):
    """Parse an opt-in maintenance ISO timestamp (UTC) or None when unset/invalid."""
    if x is None:
        return None
    try:
        if isinstance(x, str) and not x.strip():
            return None
    except AttributeError:
        pass
    try:
        t = pd.Timestamp(x)
    except (TypeError, ValueError):
        return None
    try:
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
    except (TypeError, ValueError, AttributeError):
        pass
    return t


def maint_active_at(now, start, end, pre_min: float = MAINT_PRE_MIN) -> bool:
    """True while a maintenance window suppresses new entries: start-30min <= now <= end.

    Pure function of explicit timestamps (tests use fake clocks); invalid or
    missing bounds are inactive.
    """
    if start is None or end is None:
        return False
    try:
        n, s, e = pd.Timestamp(now), pd.Timestamp(start), pd.Timestamp(end)
    except (TypeError, ValueError):
        return False
    try:
        return (s - pd.Timedelta(minutes=float(pre_min))) <= n <= e
    except (TypeError, ValueError):
        return False


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


def _is_carry_link(link) -> bool:
    """True for bot-owned carry links (prefix ``c``): owned by bot/carry.py only."""
    try:
        return str(link or "").startswith(carry_mod.LINK_PREFIX)
    except Exception:
        return str(link or "").startswith("c")


def _have_without_carry(have):
    """Resting set minus carry links (generic diff must never see them)."""
    try:
        items = list((have or {}).items())
    except (AttributeError, TypeError):
        return have
    return {k: v for k, v in items if not _is_carry_link(k)}


def _acts_without_carry_cancel(acts):
    """Drop generic cancel/amend acts targeting carry links (defense in depth)."""
    out = []
    for a in acts or []:
        try:
            if str(a.get("op")) in ("cancel", "amend") and _is_carry_link(a.get("link")):
                continue
        except (AttributeError, TypeError):
            pass
        out.append(a)
    return out


def _acts_without_exit_cancel(acts, led):
    """Never cancel a confirmed market exit of an open piece (leader fix 2026-10-07).

    1c0469a registers the market-exit link in state["links"], so have() lists the exit while the exchange still
    reports it open (paper fills a market order at the next 1m bar; live can report New / PartiallyFilled for a
    moment). mirror.diff then cancelled it in the same cycle, so time exits and close5 stops never executed and the
    piece stayed open without protection, re-sent every EXIT_INFLIGHT_MIN minutes (paper runners 2026-10-07 03:00 UTC).
    """
    try:
        keep = {pc.get("exit_link") for pc in (led or {}).values()
                if isinstance(pc, dict) and pc.get("exit_link") and float(pc.get("qty") or 0) > 0}
    except (AttributeError, TypeError, ValueError):
        return acts
    if not keep:
        return acts
    out = []
    for a in acts or []:
        try:
            if a.get("op") == "cancel" and a.get("link") in keep:
                continue
        except (AttributeError, TypeError):
            pass
        out.append(a)
    return out


# F2: categories polled for carry sync / open orders (spot + linear +
# inverse as used). Book/dip symbols are linear perps; extra categories only
# add carry legs and never change book/dip orders.
EXEC_CATEGORIES = ("linear", "spot", "inverse")


def _execs_category_aware(ex, start_ms):
    """All executions since start_ms across EXEC_CATEGORIES, deduped by execId.

    Works with the live client (executions(start, category=...)), the paper
    client (executions(start) returns all categories) and old fakes
    (executions(start) only): a TypeError on the category kw falls back to a
    single call. Never raises.
    """
    out: list = []
    seen: set = set()
    try:
        start = int(start_ms)
    except (TypeError, ValueError):
        return out
    for cat in EXEC_CATEGORIES:
        try:
            batch = ex.executions(start, category=cat)
        except TypeError:
            try:
                batch = ex.executions(start)
            except Exception:
                batch = []
            for e in batch or []:
                try:
                    eid = e.get("execId")
                except AttributeError:
                    continue
                if eid is None or eid in seen:
                    continue
                seen.add(eid)
                out.append(e)
            break
        except Exception:
            continue
        for e in batch or []:
            try:
                eid = e.get("execId")
            except AttributeError:
                continue
            if eid is None or eid in seen:
                continue
            seen.add(eid)
            out.append(e)
    return out


def _orders_category_aware(ex):
    """All open orders across EXEC_CATEGORIES, keyed by orderLinkId.

    Category-aware for live (open_orders(category=...)); falls back to a
    single open_orders() call for paper/old fakes. Never raises.
    """
    merged: dict = {}
    for cat in EXEC_CATEGORIES:
        try:
            batch = ex.open_orders(category=cat)
        except TypeError:
            try:
                batch = ex.open_orders()
            except Exception:
                batch = []
            try:
                for o in batch or []:
                    try:
                        link = o.get("orderLinkId") or ""
                    except AttributeError:
                        continue
                    if link:
                        merged[link] = o
            except TypeError:
                pass
            break
        except Exception:
            continue
        try:
            for o in batch or []:
                try:
                    link = o.get("orderLinkId") or ""
                except AttributeError:
                    continue
                if link:
                    merged[link] = o
        except TypeError:
            continue
    return list(merged.values())


class Runner:
    def __init__(self, mode: str, plan_path: Path, equity: float | None, risk_mult: float = 1.0, corr: bool = False,
                 tag: str | None = None, dip_mult: float = 1.0, bear_book: bool = False,
                 dip_cooldown_h: float = 0.0, dip_sl_coin: dict | None = None, dip_gross_cap: float | None = None,
                 adopt_fresh: bool = False, no_risk_guard: bool = False, carry_f: float = 0.0,
                 maint_start=None, maint_end=None, k2_tilt=None):
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
        # bot_maint (opt-in, default inactive): --maint-start/--maint-end flags,
        # or per-cycle maintenance.json in the state dir (file wins when valid).
        self.maint_start = _parse_maint_ts(maint_start)
        self.maint_end = _parse_maint_ts(maint_end)
        self._maint_active = False
        # bot_k2flag (default OFF = None -> bit-identical behaviour, no extra logs).
        try:
            self.k2_tilt = Path(k2_tilt) if k2_tilt else None
        except (TypeError, ValueError):
            self.k2_tilt = None
        self._k2_logged: set = set()
        self._k2_missing_logged: set = set()
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
        # bot_maint: startup protection check after every restart (never fatal).
        try:
            self._startup_protection_check()
        except Exception:
            pass

    def maint_window(self):
        """Effective (start, end) maintenance window: per-cycle maintenance.json wins when valid, else flags.

        File: <state dir>/maintenance.json with {"start": ISO, "end": ISO} (UTC;
        "maint_start"/"maint_end" spellings also accepted). A present-but-empty
        or invalid file means no window (cleared). Missing file -> flag values
        (default None/None = inactive, bit-for-bit unchanged behaviour).
        """
        try:
            mf = self.dir / "maintenance.json"
        except (AttributeError, TypeError):
            mf = None
        if mf is not None:
            try:
                if mf.exists():
                    raw = json.loads(mf.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        s = _parse_maint_ts(raw.get("start", raw.get("maint_start")))
                        e = _parse_maint_ts(raw.get("end", raw.get("maint_end")))
                        if s is not None and e is not None:
                            return s, e
                    return None, None
            except (OSError, ValueError, AttributeError):
                pass
        return getattr(self, "maint_start", None), getattr(self, "maint_end", None)

    def _maint_is_active(self, now) -> bool:
        """True inside the maintenance suppression window; logs op=maint_resume on exit."""
        try:
            s, e = self.maint_window()
        except Exception:
            s, e = None, None
        try:
            active = bool(maint_active_at(now, s, e))
        except Exception:
            active = False
        try:
            was = bool(getattr(self, "_maint_active", False))
        except Exception:
            was = False
        try:
            self._maint_active = bool(active)
        except Exception:
            pass
        if was and not active:
            try:
                self.log(dict(op="maint_resume"))
            except Exception:
                pass
        return active

    def _maint_resting_entries(self, have) -> list:
        """Resting dip-bid / book-entry links (kind == 'entry') present in `have`."""
        out = []
        try:
            links = (self.state or {}).get("links") or {}
        except (AttributeError, TypeError):
            return out
        try:
            items = list((have or {}).items())
        except (AttributeError, TypeError):
            return out
        for link, _h in items:
            try:
                if _is_carry_link(link):
                    continue
            except Exception:
                pass
            try:
                kind = ((links.get(link) or {}).get("order") or {}).get("kind")
            except (AttributeError, TypeError):
                continue
            if kind == "entry":
                out.append(link)
        return out

    def _k2_scaled_plan(self, plan, now, led):
        """Scaled plan copy with the K2 dip tilt applied (bot_k2flag, default OFF).

        For every NEW dip rung (active now, piece not in the ledger) of phase s
        for coin c whose holding bar opens at T = active_from - 16 min, look up
        (sym = c[+USDT], shift = s, T) in the --k2-tilt parquet (read at most
        once per cycle here) and multiply that rung's size_frac by k2_mult
        BEFORE mirror.desired()'s budget / gross-cap logic (so caps still
        bind) and before the runner's dust / guard / lot rounding (so minima
        still bind). Book, carry, exits and protection paths are untouched.

        Uses k2_mult only when the row exists and mode is 'prospective' or
        'late' (both computed from bars closed <= T); else 1.0. A missing /
        locked parquet means 1.0 for every rung (op=k2_missing once per bar).
        Logs op=k2_mult once per (coin, phase, bar) with the multiplier used.
        When the flag is absent the caller never calls this (bit-identical).
        """
        try:
            tilt = getattr(self, "k2_tilt", None)
        except Exception:
            tilt = None
        if not tilt:
            return plan
        try:
            now_ts = pd.Timestamp(now)
        except (TypeError, ValueError):
            return plan
        try:
            k2map = _k2_load_map(tilt)
            file_ok = True
        except Exception as e:
            try:
                bar_key = self._skip_bar(now_ts)
            except Exception:
                bar_key = str(now_ts)
            try:
                if bar_key not in self._k2_missing_logged:
                    self._k2_missing_logged.add(bar_key)
                    self.log(dict(op="k2_missing", bar=bar_key,
                                  note=f"{type(e).__name__}: {e}"[:200]))
            except Exception:
                pass
            return plan
        try:
            scaled = copy.deepcopy(plan)
        except Exception:
            return plan
        try:
            coins = (scaled.get("coins") or {})
        except (AttributeError, TypeError):
            return plan
        seen: dict = {}
        for coin, c in list(coins.items()):
            if not isinstance(c, dict):
                continue
            for d in (c.get("dips") or []):
                if not isinstance(d, dict):
                    continue
                try:
                    a0 = pd.Timestamp(d.get("active_from"))
                    a1 = pd.Timestamp(d.get("active_until"))
                except (TypeError, ValueError, AttributeError):
                    continue
                try:
                    if not (a0 <= now_ts < a1 + pd.Timedelta(minutes=1)):
                        continue
                except (TypeError, ValueError):
                    continue
                try:
                    ph = d.get("phase")
                    rung = d.get("rung")
                    bar = _k2_bar_of_dip(d)
                    if bar is None:
                        continue
                    pid = mirror.dip_pid(int(ph), _k2_norm_sym(coin), rung, bar)
                    if isinstance(led, dict) and pid in led:
                        continue  # already open: not a NEW entry, leave untouched
                except Exception:
                    continue
                mult, mode = _k2_mult_for(coin, ph, bar, k2map)
                try:
                    key = (str(coin), int(ph), str(bar))
                except (TypeError, ValueError):
                    continue
                if key not in seen:
                    seen[key] = (mult, mode, coin, ph, bar)
                try:
                    d["size_frac"] = float(d.get("size_frac")) * float(mult)
                except (TypeError, ValueError, KeyError, AttributeError):
                    continue
        try:
            logged = getattr(self, "_k2_logged", None)
            if not isinstance(logged, set):
                logged = self._k2_logged = set()
        except Exception:
            logged = set()
        for key, (mult, mode, coin, ph, bar) in seen.items():
            if key in logged:
                continue
            logged.add(key)
            try:
                self.log(dict(op="k2_mult", coin=str(coin), sym=_k2_norm_sym(coin),
                              phase=int(ph), bar=str(bar), mult=float(mult), k2_mode=str(mode)))
            except Exception:
                pass
        return scaled

    def _startup_protection_check(self):
        """Startup check after every restart: list each open piece and verify its
        native backstop/TP still rests (op=protection_check).

        An open piece without BOTH a resting stop and TP is already a CRITICAL
        line in scripts/bot_health.py (`unprotected`); this log is the restart
        trigger for that check.
        """
        try:
            have = self.have()
        except Exception as e:
            self.log(dict(op="protection_check", error=f"{type(e).__name__}: {e}"[:200]))
            return dict(open=[], missing=[], error=True)
        try:
            ledger = (self.state or {}).get("ledger") or {}
        except (AttributeError, TypeError):
            ledger = {}
        try:
            links = (self.state or {}).get("links") or {}
        except (AttributeError, TypeError):
            links = {}
        open_pids, missing = [], []
        try:
            items = list(ledger.items())
        except AttributeError:
            items = []
        for pid, pc in items:
            if not isinstance(pc, dict):
                continue
            try:
                qty = float(pc.get("qty", 0.0))
            except (TypeError, ValueError):
                continue
            if not qty > 0:
                continue
            open_pids.append(pid)
            stop_ok = tp_ok = False
            if (pid + "S") in (have or {}):
                stop_ok = True
            if (pid + "T") in (have or {}):
                tp_ok = True
            if not (stop_ok and tp_ok):
                # metadata fallback for nonstandard link ids (same piece/kind)
                for link in (have or {}):
                    try:
                        o = ((links.get(link) or {}).get("order") or {})
                    except (AttributeError, TypeError):
                        continue
                    if o.get("piece") != pid:
                        continue
                    if o.get("kind") == "stop":
                        stop_ok = True
                    elif o.get("kind") == "tp":
                        tp_ok = True
            if not (stop_ok and tp_ok):
                need = "/".join(x for x, ok in (("stop", stop_ok), ("tp", tp_ok)) if not ok)
                missing.append(f"{pid}({pc.get('symbol')}:no-{need})")
        self.log(dict(op="protection_check", open=open_pids, missing=missing))
        return dict(open=open_pids, missing=missing)

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

    def _carry_baseline(self) -> list:
        """Open carry notionals as pseudo-pieces for the guard baseline (N4).

        Each open pair contributes its spot leg (spot_symbol x qty) and its
        futures leg (dated symbol x qty) with entry refs, so the total-gross
        cap sees both sleeves. Empty when carry is off: book/dip behaviour
        bit-for-bit unchanged.
        """
        out: list = []
        try:
            cstate = (self.state or {}).get("carry") or {}
            positions = cstate.get("positions") or {}
            items = list(positions.items()) if isinstance(positions, dict) else []
        except (AttributeError, TypeError):
            return out
        for coin, pos in items:
            if not isinstance(pos, dict):
                continue
            try:
                q = float(pos.get("qty", 0) or 0)
            except (TypeError, ValueError):
                continue
            if not q > 0:
                continue
            try:
                ss = pos.get("spot_symbol") or carry_mod.spot_symbol(coin)
            except Exception:
                continue
            try:
                se = float(pos.get("S_entry", 0) or 0)
            except (TypeError, ValueError):
                se = 0.0
            try:
                fe = float(pos.get("F_entry", 0) or 0)
            except (TypeError, ValueError):
                fe = 0.0
            fs = pos.get("symbol")
            if ss:
                out.append(dict(symbol=ss, qty=q, entry=se or None, kind="carry", phase=-1))
            if fs:
                out.append(dict(symbol=fs, qty=q, entry=fe or None, kind="carry", phase=-1))
        return out

    def _apply_risk_guard(self, want: dict, equity: float, prices: dict):
        """Filter `want` through risk_guard.check (defaults: per-coin 2.5x, dip
        2.0x, total 4x, single 1x). Rejects are logged op=risk_reject and not
        sent; protection / reduce-only orders are never blocked by check()."""
        try:
            led = self.state.get("ledger")
            base = list(led.values()) if isinstance(led, dict) else list(led or [])
            base = [v for v in base if isinstance(v, dict)] + self._carry_baseline()
            allowed, rejected = risk_guard.check(want, base, equity, prices)
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
        """Apply exchange executions of carry links (prefix ``c``) to carry state.

        F2: polls spot + linear + inverse (category-aware) so spot fills are
        seen. F6: uses its own ``carry_last_exec_ms`` cursor (migrated from
        ``last_exec_ms`` once) so book/dip polling can never skip past a
        carry fill and vice versa.
        """
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
        last = self.state.get("carry_last_exec_ms", self.state.get("last_exec_ms"))
        try:
            start = int(last) if last is not None else int((time.time() - 3600) * 1000)
            ex = _execs_category_aware(self.ex, start)
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
                # F6: advance only the carry cursor, only past carry execs.
                cur = self.state.get("carry_last_exec_ms", self.state.get("last_exec_ms") or 0)
                self.state["carry_last_exec_ms"] = max(int(cur or 0), int(e["execTime"]))
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
        # N1: no NEW carry entries inside the maintenance window
        # (recovery/close/settlement still allowed). Fresh entries are the
        # decide carry_entry payloads (per-coin links cCOIN...); unhedged
        # hedges, timeout closes and delivery sales pass through.
        try:
            _maint = bool(self._maint_is_active(now))
        except Exception:
            _maint = False
        if _maint:
            try:
                entry_coins = {str(r.get("coin", "")).upper() for r in (logs or [])
                               if isinstance(r, dict) and r.get("op") == "carry_entry"}
            except Exception:
                entry_coins = set()
            if entry_coins:
                blocked = []
                kept = []
                for p in want:
                    try:
                        link = str(p.get("orderLinkId", ""))
                    except (AttributeError, TypeError):
                        kept.append(p)
                        continue
                    drop = any(link.startswith("c" + c) for c in entry_coins if c)
                    (blocked if drop else kept).append(p)
                if blocked:
                    try:
                        self.log(dict(op="maint_cancel",
                                      carry_blocked=[b.get("orderLinkId") for b in blocked
                                                     if isinstance(b, dict)],
                                      blocked_new=[b.get("orderLinkId") for b in blocked
                                                   if isinstance(b, dict)]))
                    except Exception:
                        pass
                want = kept
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
        # F2: category-aware open-order poll (spot + linear + inverse as
        # used); book/dip callers filter via _have_without_carry, so extra
        # carry legs never change book/dip orders.
        if self.mode == "dry":
            return {k: v["rest"] for k, v in self.state["links"].items() if v.get("rest")}
        out = {}
        try:
            orders = _orders_category_aware(self.ex)
        except Exception:
            orders = []
        for o in orders:
            try:
                link = o.get("orderLinkId") or ""
            except AttributeError:
                continue
            if link in self.state["links"]:
                try:
                    out[link] = dict(symbol=o["symbol"], price=o.get("price"), trigger=o.get("triggerPrice"), qty=o.get("qty"))
                except (KeyError, TypeError, AttributeError):
                    continue
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
        except Exception as e:
            # N2: log the bear fetch fallback once (then stay silent until the
            # next success so a long outage does not spam the action log).
            try:
                if not getattr(self, "_bear_fallback_logged", False):
                    self.log(dict(op="bear_fallback",
                                  note=f"{type(e).__name__}: {e}"[:200],
                                  bear=bool(getattr(self, "_bear", False))))
                    self._bear_fallback_logged = True
            except Exception:
                pass
            return self._bear if self._bear_at is not None else False
        b = bool(mirror.is_bear(opens))
        try:
            n = len(opens)
        except TypeError:
            n = 0
        if self._bear_at is None or b != self._bear:
            self.log(dict(op="bear_state", bear=b, opens=n))
        self._bear, self._bear_at = b, now
        try:
            self._bear_fallback_logged = False
        except Exception:
            pass
        return b

    def _protection_only(self, led, now=None) -> dict:
        """Protection orders from the ledger alone (plan file missing and no cached plan).

        bot_reviewfix2 #3: respects in-flight exits like the main path and
        validates prices (finite_pos), so a plan-outage cycle never re-places
        S/T alongside an in-flight market (double-spend) and a corrupt ledger
        never raises out of the cycle. Dip pieces get TP + native stop
        (backstop else plan stop), never TP-only (#1).
        """
        out = {}
        for pid, pc in (led or {}).items():
            try:
                if not isinstance(pc, dict):
                    continue
                try:
                    qty = float(pc.get("qty", 0.0))
                except (TypeError, ValueError):
                    continue
                if not qty > 0:
                    continue
                sym = pc.get("symbol")
                if not sym or sym not in self.inst:
                    continue
                if now is not None:
                    try:
                        if mirror._market_inflight(pc, now):
                            continue
                    except Exception:
                        pass
                side = pc.get("side", 1)
                pidx = 1 if side > 0 else 2
                if pc.get("kind") == "dip":
                    try:
                        _tp = float(pc.get("tp"))
                    except (TypeError, ValueError):
                        continue
                    if not mirror._finite_pos(_tp):
                        continue
                    out[pid + "T"] = mirror.Order(pid + "T", sym, "Sell", qty, "tp", price=_tp,
                                                 reduce_only=True, position_idx=1, piece=pid)
                    _bs = mirror._dip_native_stop(pc)
                    if _bs is not None:
                        out[pid + "S"] = mirror.Order(pid + "S", sym, "Sell", qty, "stop", trigger=_bs,
                                                     reduce_only=True, position_idx=1, piece=pid)
                elif pc.get("kind") == "book":
                    try:
                        _sl = float(pc.get("sl"))
                        _tp = float(pc.get("tp"))
                    except (TypeError, ValueError):
                        continue
                    if not (mirror._finite_pos(_sl) and mirror._finite_pos(_tp)):
                        continue
                    sell = side > 0
                    out[pid + "S"] = mirror.Order(pid + "S", sym, "Sell" if sell else "Buy", qty, "stop",
                                                 trigger=_sl, reduce_only=True, position_idx=pidx, piece=pid)
                    out[pid + "T"] = mirror.Order(pid + "T", sym, "Sell" if sell else "Buy", qty, "tp",
                                                 price=_tp, reduce_only=True, position_idx=pidx, piece=pid)
            except Exception:
                continue
        return out

    def _guard_phantom_cancels(self, acts, led, have, now):
        """Drop cancels that would strip resting S/T for a phantom exit.

        bot_reviewfix2 #2: a persisted ``exit_sent`` with no confirmed
        ``exit_link`` (logged but never placed, send-failed) must NOT cancel
        still-resting protection. True in-flight pieces (confirmed exit_link)
        still cancel S/T to avoid the shared-net double-spend. Returns the
        filtered acts; dropped cancels log op=exit_revalidate once per piece.
        """
        try:
            acts = list(acts or [])
        except TypeError:
            return acts
        if not acts:
            return acts
        try:
            ledger = led or {}
        except (AttributeError, TypeError):
            return acts
        out, seen = [], set()
        for a in acts:
            try:
                if not isinstance(a, dict) or a.get("op") != "cancel":
                    out.append(a)
                    continue
                link = a.get("link")
                # Carry links never reach here (filtered), but stay safe.
                try:
                    if _is_carry_link(link):
                        out.append(a)
                        continue
                except Exception:
                    pass
                # Find the piece for this resting link (state metadata, else pid prefix).
                pid = None
                try:
                    o = ((self.state or {}).get("links") or {}).get(link) or {}
                    oo = (o.get("order") or {})
                    pid = oo.get("piece")
                except (AttributeError, TypeError):
                    pid = None
                if not pid and isinstance(link, str) and len(link) > 1:
                    pid = link[:-1]
                pc = ledger.get(pid) if isinstance(ledger, dict) else None
                if not isinstance(pc, dict):
                    out.append(a)
                    continue
                try:
                    sent = pc.get("exit_sent")
                    has_link = bool(pc.get("exit_link"))
                except (AttributeError, TypeError):
                    out.append(a)
                    continue
                if sent is None or has_link:
                    out.append(a)
                    continue
                try:
                    age_min = (pd.Timestamp(now) - pd.Timestamp(sent)).total_seconds() / 60.0
                except (TypeError, ValueError, AttributeError):
                    out.append(a)
                    continue
                if not (0.0 <= age_min < mirror.EXIT_INFLIGHT_MIN):
                    out.append(a)
                    continue
                # Phantom fresh exit with no live market order: keep resting S/T.
                if link not in seen:
                    seen.add(link)
                    try:
                        self.log(dict(op="exit_revalidate", piece=pid, link=link,
                                      reason="persisted_exit_without_live_order"))
                    except Exception:
                        pass
                continue
            except Exception:
                try:
                    out.append(a)
                except Exception:
                    pass
                continue
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
                # bot_maint: no entries exist on this path (protection-only), but
                # still track the window so op=maint_resume fires on exit.
                try:
                    self._maint_is_active(now)
                except Exception:
                    pass
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
                    try:
                        if mirror._market_inflight(pc, now):
                            continue  # confirmed market exit in flight; wait for its fill
                    except Exception:
                        pass
                    link = f"{pid}X{mirror.t36(now)}"
                    qty = round_step(pc["qty"], self.inst[pc["symbol"]]["qty_step"])
                    payload = dict(symbol=pc["symbol"], side="Sell" if pc["side"] > 0 else "Buy", orderType="Market",
                                   qty=qty, reduceOnly=True, orderLinkId=link, positionIdx=1 if pc["side"] > 0 else 2)
                    self.log(dict(op="market_exit", piece=pid, reason=why, payload=payload))
                    if self.send(self.ex.place, payload) is not None or self.mode == "dry":
                        # bot_reviewfix2 #2: confirm only after the exchange accepts
                        # (a logged-but-unfilled exit must not strip protection on restart).
                        pc["exit_sent"] = str(now)
                        pc["exit_link"] = link
                        self.state["links"][link] = dict(order=asdict(mirror.Order(link, pc["symbol"], payload["side"], float(qty), "reduce",
                                                                                  reduce_only=True, position_idx=payload["positionIdx"], piece=pid)))
                        if self.mode == "dry":
                            pc["qty"] = 0.0
                want = self._protection_only(led, now)
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
                acts = mirror.diff({k: o for k, (o, _) in rounded.items()}, _have_without_carry(have))
                acts = _acts_without_carry_cancel(acts)
                acts = _acts_without_exit_cancel(acts, led)
                try:
                    acts = self._guard_phantom_cancels(acts, led, have, now)
                except Exception:
                    pass
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
        try:
            equity = self.equity_arg if self.mode == "dry" else self.ex.equity_usdt()
        except Exception as e:
            # F3: one equity blip must not abort protection (ledger-only path
            # already survives it): fall back, log locally, keep the cycle.
            try:
                self.log(dict(op="cycle_error", call="equity_usdt", note=f"{type(e).__name__}: {e}"[:200]))
            except Exception:
                pass
            equity = self.equity_arg or 0.0
        _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        try:
            self.sync_fills()
        except Exception as e:
            try:
                self.log(dict(op="cycle_error", call="sync_fills", note=f"{type(e).__name__}: {e}"[:200]))
            except Exception:
                pass
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
            try:
                if mirror._market_inflight(pc, now):
                    continue  # a confirmed market exit is in flight; wait for its fill before sending another
            except Exception:
                pass
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
                pc["exit_sent"] = str(now)
                pc["exit_link"] = link
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

        def _on_plan_reject(rec):
            try:
                rec = dict(rec or {})
                rec.setdefault("op", "plan_reject")
                self.log(rec)
            except Exception:
                pass

        # bot_k2flag: optional dip-size tilt (default OFF -> plan unchanged).
        # Scaling happens on a plan copy BEFORE desired() so the dip budget,
        # the dip gross-cap, the dust guard, the risk guard and lot rounding
        # all still bind the scaled size. Book / carry / exits untouched.
        try:
            if getattr(self, "k2_tilt", None):
                plan = self._k2_scaled_plan(plan, now, led)
        except Exception:
            pass

        try:
            want = mirror.desired(plan, now, equity, led, risk_mult=self.risk_mult, corr=self.corr,
                                  last_close=lc, dip_mult=self.dip_mult,
                                  bear_book=self.bear_book, bear=bear,
                                  dip_cooldown_h=self.dip_cooldown_h, dip_sl_coin=self.dip_sl_coin,
                                  dip_gross_cap=_gross, adopt_fresh=_adopt, on_reject=_on_plan_reject)
        except Exception as e:
            # bot_soakfix B3: one bad plan row must never kill the cycle; log
            # and keep protection from the ledger so open pieces stay managed.
            try:
                self.log(dict(op="plan_reject", reason=f"desired_error:{type(e).__name__}",
                              note=str(e)[:200]))
            except Exception:
                pass
            try:
                want = self._protection_only(led, now)
            except Exception:
                want = {}
        # bot_soakfix B2a (pre-entry dust guard): never place a book / dip entry
        # whose filled qty could not carry its protection (qty*TP or qty*stop
        # below the symbol minimum notional / lot). Sizing itself is untouched;
        # dust rungs are skipped and logged op=dust_skip (kept in the skipped
        # set too so the existing skipped_below_minimum signal is preserved).
        _dust_skipped_links: list = []
        try:
            _dust_links: list = []
            for _lk, _o in list(want.items()):
                try:
                    if getattr(_o, "kind", None) != "entry":
                        continue
                    _inst = (self.inst or {}).get(_o.symbol)
                    if _inst is None:
                        continue
                    _meta = getattr(_o, "meta", {}) or {}
                    if (_meta.get("kind") == "dip"):
                        _tp, _sp = _meta.get("tp"), _meta.get("stop")
                    else:
                        _tp, _sp = _meta.get("tp"), _meta.get("sl")
                    if mirror.entry_is_dust(getattr(_o, "qty", 0), _tp, _sp, _inst):
                        _dust_links.append(_lk)
                except Exception:
                    continue
            for _lk in _dust_links:
                _o = want.pop(_lk, None)
                try:
                    self.log(dict(op="dust_skip", link=_lk, symbol=getattr(_o, "symbol", None),
                                  reason="entry_protection_below_minimum"))
                except Exception:
                    pass
            _dust_skipped_links = list(_dust_links)
        except Exception:
            pass
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
        # bot_maint (opt-in window): suppress NEW entries (dip bids + book
        # entries, kind == "entry"); protection (tp/stop/reduce) and carry legs
        # are untouched. Resting entries cancel via diff() below; the marker op
        # is logged once have_before is known. Default (no window): unchanged.
        _maint_on = False
        try:
            _maint_on = bool(self._maint_is_active(now))
        except Exception:
            _maint_on = False
        _maint_blocked: list = []
        if _maint_on:
            try:
                _maint_blocked = [k for k, o in want.items() if o.kind == "entry"]
            except (AttributeError, TypeError):
                _maint_blocked = []
            if _maint_blocked:
                want = {k: o for k, o in want.items() if o.kind != "entry"}
        # PRE-TRADE GUARD (testnet review 2026-10-06 V4, exact call site): filter
        # `want` after stale/plan_error trimming and before rounding/diff.
        # Prices = last closed 1m closes (lc) falling back to 5m closes/plan
        # marks; equity = exchange equity. check() never blocks reduce-only
        # exits/protection, so stops/TPs/market exits always pass.
        if not getattr(self, "no_risk_guard", False):
            want = self._apply_risk_guard(want, equity, self._guard_prices(lc, _last5_for_cycle, plan))
        _stages["decide_ms"] += (_cycle_now() - _t) * 1000.0
        _t = _cycle_now()
        try:
            have_before = self.have()
        except Exception as e:
            # F3: one open_orders blip must not abort protection: fall back
            # to empty `have` (all wanted orders place/amend), log locally.
            try:
                self.log(dict(op="cycle_error", call="open_orders", note=f"{type(e).__name__}: {e}"[:200]))
            except Exception:
                pass
            have_before = {}
        _stages["sync_ms"] += (_cycle_now() - _t) * 1000.0
        if _maint_on:
            # bot_maint marker: which new entries were blocked and which resting
            # entry limits will cancel via diff() below (oc_outage runbook rule).
            try:
                _maint_cancels = [l for l in self._maint_resting_entries(have_before) if l not in want]
            except Exception:
                _maint_cancels = []
            if _maint_blocked or _maint_cancels:
                self.log(dict(op="maint_cancel", blocked_new=sorted(_maint_blocked),
                              cancel_resting=sorted(_maint_cancels)))
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
        # bot_soakfix B2a: dust-skipped entries keep the legacy skipped_below_minimum signal too.
        try:
            for _lk in (_dust_skipped_links or []):
                if _lk not in skipped:
                    skipped.append(_lk)
        except NameError:
            pass
        except Exception:
            pass
        acts = mirror.diff({k: o for k, (o, _) in rounded.items()}, _have_without_carry(have_before),
                           amend_entry_qty=(self.corr or self.risk_mult != 1.0 or self.dip_mult != 1.0 or bool(getattr(self, "dip_gross_cap", 0.0))))
        acts = _acts_without_carry_cancel(acts)
        acts = _acts_without_exit_cancel(acts, led)
        try:
            acts = self._guard_phantom_cancels(acts, led, have_before, now)
        except Exception:
            pass
        _stages["decide_ms"] += (_cycle_now() - _t) * 1000.0
        failed_protect_pieces, placed_protect_links = set(), set()
        _t = _cycle_now()
        for a in acts:
            if a["op"] == "place":
                o = a["order"]
                p = rounded[o.link][1]
                self.log(dict(op="place", payload=p))
                if self.send(self.ex.place, p) is not None or self.mode == "dry":
                    self.state["links"][o.link] = dict(order=asdict(o), rest=dict(symbol=o.symbol, price=o.price, trigger=o.trigger, qty=o.qty))
                    if o.kind in ("stop", "tp"):
                        placed_protect_links.add(o.link)
                elif o.kind in ("stop", "tp"):
                    # bot_reviewfix2 #5: TP place-failures count like stops.
                    failed_protect_pieces.add(o.piece)
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
        # bot_soakfix B2b (dust fallback): an open piece whose protection cannot
        # rest on the exchange (qty below lot, or qty*TP / qty*stop below the
        # symbol minimum notional, or non-positive / non-finite TP/stop) is
        # closed with a reduce-only market order in the SAME cycle (taker fee),
        # never left unprotected. Runs before the unprotected retry counter so
        # dust never waits 2 cycles.
        if self.mode != "dry":
            for pid, pc in list(led.items()):
                try:
                    if not isinstance(pc, dict):
                        continue
                    try:
                        _q = float(pc.get("qty", 0.0))
                    except (TypeError, ValueError):
                        continue
                    if not _q > 0:
                        continue
                    _sym = pc.get("symbol")
                    _inst = (self.inst or {}).get(_sym)
                    if _inst is None:
                        continue
                    try:
                        if mirror._market_inflight(pc, now):
                            continue
                    except Exception:
                        pass
                    _tp_px = _sp_px = None
                    try:
                        for _k, _o in want.items():
                            try:
                                if getattr(_o, "piece", None) != pid:
                                    continue
                                if getattr(_o, "kind", None) == "tp" and _tp_px is None:
                                    _tp_px = getattr(_o, "price", None)
                                elif getattr(_o, "kind", None) == "stop" and _sp_px is None:
                                    _sp_px = getattr(_o, "trigger", None)
                            except (AttributeError, TypeError):
                                continue
                    except (AttributeError, TypeError):
                        pass
                    if _tp_px is None:
                        _tp_px = pc.get("tp")
                    if _sp_px is None:
                        for _fk in ("backstop", "sl", "stop5", "stop"):
                            try:
                                _cand = pc.get(_fk)
                            except (AttributeError, TypeError):
                                _cand = None
                            if _cand is not None:
                                _sp_px = _cand
                                break
                    # Only judge dust when BOTH protection prices are known: a piece
                    # with no plan levels yet (e.g. pending sub, no attached sl/tp)
                    # is not dust — divergence / unprotected logic owns it.
                    if _tp_px is None or _sp_px is None:
                        continue
                    try:
                        _is_dust = bool(mirror.protection_is_dust(_q, _tp_px, _sp_px, _inst))
                    except Exception:
                        continue
                    if not _is_dust:
                        continue
                    try:
                        _qq = round_step(_q, self.inst[_sym]["qty_step"])
                        # bot_dustfix 2026-10-07: a float remainder just under one lot (e.g. 0.8999.. - TP 0.8 = 0.0999 SOL)
                        # rounds to 0 and the close was rejected forever; send at least one lot reduce-only (the exchange /
                        # paper caps a reduce-only order at the position, so it closes exactly the remainder, never flips).
                        if float(_qq) < float(self.inst[_sym]["min_qty"]):
                            _qq = str(self.inst[_sym]["min_qty"])
                    except (TypeError, ValueError, KeyError):
                        continue
                    _dlink = f"{pid}D{mirror.t36(now)}"
                    _payload = dict(symbol=_sym, side="Sell" if pc.get("side", 1) > 0 else "Buy",
                                    orderType="Market", qty=_qq, reduceOnly=True, orderLinkId=_dlink,
                                    positionIdx=1 if pc.get("side", 1) > 0 else 2)
                    try:
                        self.log(dict(op="dust_close", piece=pid, payload=_payload, reason="protection_below_minimum"))
                    except Exception:
                        pass
                    try:
                        if self.send(self.ex.place, _payload) is not None:
                            pc["exit_sent"] = str(now)
                            pc["exit_link"] = _dlink
                            self.state["links"][_payload["orderLinkId"]] = dict(order=asdict(
                                mirror.Order(_payload["orderLinkId"], _sym, _payload["side"], float(_qq), "reduce",
                                             reduce_only=True, position_idx=_payload["positionIdx"], piece=pid)))
                    except Exception:
                        continue
                except Exception:
                    continue
        # Unprotected positions: an open piece whose stop or TP is wanted but rests
        # nowhere and whose placement just failed. Retry is automatic next cycle
        # (want still has the order); after > 2 such cycles flatten at market
        # (reduce-only) and log op=unprotected_close. bot_reviewfix2 #5 counts
        # TP failures like stops (a piece with only one leg resting is still
        # unprotected: every position carries native SL+TP).
        if self.mode != "dry":
            for pid, pc in list(led.items()):
                try:
                    qty = float(pc.get("qty", 0.0))
                except (TypeError, ValueError):
                    continue
                if qty <= 0:
                    pc.pop("unprotected_cycles", None)
                    continue
                try:
                    if mirror._market_inflight(pc, now):
                        continue
                except Exception:
                    pass
                protect_links = [k for k, o in want.items() if o.piece == pid and o.kind in ("stop", "tp")]
                if not protect_links:
                    pc.pop("unprotected_cycles", None)
                    continue
                rests = all(k in have_before or k in placed_protect_links for k in protect_links)
                if rests:
                    pc.pop("unprotected_cycles", None)
                    continue
                if pid in failed_protect_pieces or any(k not in have_before for k in protect_links):
                    # No resting protection and none placed successfully this cycle.
                    # Only count cycles where a placement was actually attempted and failed;
                    # a pure have-miss without a place act means the link was skipped below
                    # minimum (already logged) and must not trigger a market close.
                    if pid not in failed_protect_pieces:
                        continue
                    n = int(pc.get("unprotected_cycles", 0) or 0) + 1
                    pc["unprotected_cycles"] = n
                    if n > 2:
                        try:
                            if mirror._market_inflight(pc, now):
                                continue
                        except Exception:
                            pass
                        link = f"{pid}U{mirror.t36(now)}"
                        q = round_step(qty, self.inst[pc["symbol"]]["qty_step"])
                        payload = dict(symbol=pc["symbol"], side="Sell" if pc["side"] > 0 else "Buy",
                                       orderType="Market", qty=q, reduceOnly=True, orderLinkId=link,
                                       positionIdx=1 if pc["side"] > 0 else 2)
                        self.log(dict(op="unprotected_close", piece=pid, payload=payload, cycles=n))
                        if self.send(self.ex.place, payload) is not None:
                            pc["exit_sent"] = str(now)
                            pc["exit_link"] = link
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
    ap.add_argument("--maint-start", default=None, metavar="ISO", help="opt-in maintenance window start, UTC ISO (default off; suppression runs from start-30min until --maint-end)")
    ap.add_argument("--maint-end", default=None, metavar="ISO", help="opt-in maintenance window end, UTC ISO (default off; or use <state dir>/maintenance.json, read each cycle)")
    ap.add_argument("--k2-tilt", default=None, metavar="PATH", help="opt-in Kronos K2 dip-size tilt parquet (default off = unchanged; e.g. artifacts/research/kronos_shadow/kronos_features_live.parquet)")
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
             carry_f=a.carry_f, maint_start=a.maint_start, maint_end=a.maint_end, k2_tilt=a.k2_tilt)
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
