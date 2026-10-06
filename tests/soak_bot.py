"""Accelerated BOT soak harness (assignments OPENCODE_W_bot_soak / bot_soak2).

Replays 24h of real historical 1m klines of the five majors through the fake
Bybit V5 exchange (tests/mock_bybit_v5.py; prices follow the replay, limit
fills on 1m trade-through, stop-first), with synthetic hourly phase plans
generated from the stored research plan format
(artifacts/research/advisor_shadow/trade_plan_v376.json shape), running
bot.run.Runner in testnet mode with the deployment flags
(--corr-size --dip-mult 1.7 --bear-book --dip-gross-cap 2.0 --adopt-fresh
--carry-f 0.25) on a fake clock (one Runner.cycle per simulated 20 s).

Not collected by pytest by default (name does not start with test_). The
2-hour mini version lives in tests/test_bot_soak_smoke.py.

Usage (wrapped in the shared semaphore, MEDIUM, RAM < 2 GB):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag bot_soak2 \\
    --min-free-gb 2.0 -- .venv/Scripts/python.exe tests/soak_bot.py \\
    --hours 24 --step-s 20 --workdir <dir>

Only runtime outputs go to <workdir>; this module never edits bot/ code.
"""

import torch  # noqa: F401  (Windows DLL load order: torch before pandas)

import argparse
import copy
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mock_bybit_v5 import MockBybitV5  # noqa: E402

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
BTC_PARQUET_DIR = ROOT / "data/raw/btc_intraday_20260924"
MAJORS_PARQUET_DIR = ROOT / "data/raw/majors_intraday_20260924"
# NOTE: synthetic plans are generated in the trade_plan_v376.json shape
# (same top-level keys, subs, and dip rows; see make_plan), not copied from a
# frozen fixture, so every hourly plan is re-anchored to replay prices.

# 24h window containing the 2025-10-10 flush (BTC -14.9% to 21:19 UTC,
# ~-29 sigma vs trailing 4h sigma 0.00514; verified offline in
# research/tournament/bot_soak2/tmp/check_window.py). Reduced from 72h for
# bot_soak2 so the replay finishes in < 90 min.
WINDOW_START = pd.Timestamp("2025-10-10 00:00:00+00:00")
DIP_GROSS_CAP_G = 2.0  # deployment flag --dip-gross-cap 2.0
PHASE_CAPITAL = 0.25
DIP_RUNGS = (2.5, 3.0, 4.0)  # 60 dip bids/cycle: enough to bind the guard/cap, not drown the log
# bot_soakfix B3 (test-only): clamp synthetic buy_limit to a positive tick so the
# harness never emits buy_limit = 0 (rung 4.0 x sigma cap 0.25); the bot still
# guards non-positive plan prices with plan_reject.
_SOAK_TICK = {"BTCUSDT": 0.1, "ETHUSDT": 0.01, "SOLUSDT": 0.01, "BNBUSDT": 0.01, "XRPUSDT": 0.0001}


# ----------------------------------------------------------------------------
# replay loading (RAM < 2 GB: parquet pushdown filters, only the window)
# ----------------------------------------------------------------------------
def _year_files(sym: str, start: pd.Timestamp, end: pd.Timestamp) -> list:
    """Only the yearly 1m files overlapping [start, end) (fast startup)."""
    if sym == "BTCUSDT":
        files = sorted(BTC_PARQUET_DIR.glob("klines_1m_*.parquet"))
        pre = "klines_1m_"
    else:
        files = sorted(MAJORS_PARQUET_DIR.glob(f"{sym}_1m_*.parquet"))
        pre = f"{sym}_1m_"
    out = []
    for f in files:
        try:
            y = int(f.stem[len(pre):len(pre) + 4])
        except ValueError:
            continue
        y0, y1 = pd.Timestamp(f"{y}-01-01", tz="UTC"), pd.Timestamp(f"{y + 1}-01-01", tz="UTC")
        if y0 < end and y1 > start:
            out.append(f)
    return out


def _read_window(sym: str, start: pd.Timestamp, hours: float) -> pd.DataFrame:
    end = start + pd.Timedelta(hours=hours)
    files = _year_files(sym, start, end)
    frames = []
    for f in files:
        try:
            df = pd.read_parquet(
                f,
                columns=["open_time", "open", "high", "low", "close"],
                filters=[("open_time", ">=", start.to_pydatetime()),
                         ("open_time", "<", end.to_pydatetime())],
            )
        except Exception:
            continue
        if len(df):
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"no 1m bars for {sym} in {start} +{hours}h")
    out = pd.concat(frames, ignore_index=True).sort_values("open_time").reset_index(drop=True)
    out = out[(out["open_time"] >= start) & (out["open_time"] < end)]
    return out


def load_replay(start: pd.Timestamp, hours: float) -> dict:
    return {s: _read_window(s, start, hours) for s in SYMS}


def trailing_sigma(replay: dict, sym: str, sim_now: pd.Timestamp, lookback_min: int = 240) -> float:
    """4h sigma from trailing 1m log returns (offline, causal: only bars < sim_now)."""
    df = replay[sym]
    past = df[df["open_time"] < sim_now.floor("min")]
    if len(past) < 30:
        return 0.008
    tail = past.tail(lookback_min + 1)
    import math

    rets = [math.log(c / p) for p, c in zip(tail["close"].values[:-1], tail["close"].values[1:]) if p > 0 and c > 0]
    if len(rets) < 10:
        return 0.008
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    sig = math.sqrt(max(var, 0.0)) * math.sqrt(240.0)
    if not (0.001 < sig < 0.25):
        return min(max(sig, 0.001), 0.25)
    return sig


# ----------------------------------------------------------------------------
# synthetic hourly phase plans in the stored research plan shape
# ----------------------------------------------------------------------------
def make_plan(sim_hour: pd.Timestamp, replay: dict, hour_idx: int) -> dict:
    """One hourly plan shaped like trade_plan_v376.json, anchored to replay closes.

    Method: generated offline from replay closes/sigmas only (no network). Mix
    of pending book entries and LONG/SHORT book positions across the 4 phases
    (one fresh position per coin for --adopt-fresh), plus 5 dip rungs per
    coin/phase with engine-style active windows. Deterministic in hour_idx.
    """
    closes, sigmas = {}, {}
    for s in SYMS:
        df = replay[s]
        past = df[df["open_time"] <= sim_hour]
        closes[s] = float(past["close"].iloc[-1]) if len(past) else 100.0
        sigmas[s] = trailing_sigma(replay, s, sim_hour + pd.Timedelta(seconds=1))
    phases = []
    for p in range(4):
        phases.append({
            "phase": p, "label": f"khung +{p}h", "capital": PHASE_CAPITAL,
            "freeze": str(sim_hour - pd.Timedelta(hours=48)),
            "decision_bar": str(sim_hour),
            "next_decision": str(sim_hour + pd.Timedelta(hours=4)),
            "generated_at": str(sim_hour + pd.Timedelta(minutes=4)),
            "started": True,
        })
    coins = {}
    for ci, s in enumerate(SYMS):
        px = closes[s]
        sig = sigmas[s]
        subs = []
        for p in range(4):
            slot = (hour_idx + p + ci) % 4
            if slot == 0:
                # pending book entry (resting below market for BUY so PostOnly holds)
                side = "BUY" if (hour_idx + p + ci) % 2 == 0 else "SELL"
                entry = px * (0.999 if side == "BUY" else 1.001)
                sgn = 1 if side == "BUY" else -1
                subs.append({
                    "phase": p, "label": f"khung +{p}h", "capital": PHASE_CAPITAL,
                    "state": "pending",
                    "order": {
                        "kind": "open", "side": side, "price": entry, "weight": 0.02,
                        "issued": str(sim_hour - pd.Timedelta(minutes=10)),
                        "valid_until": str(sim_hour + pd.Timedelta(hours=4)),
                        "sl_if_filled": entry * (1 - sgn * 0.06),
                        "tp_if_filled": entry * (1 + sgn * 0.08),
                    },
                })
            else:
                # book position; phase 0 of each coin is fresh (opened 30 min ago)
                # so --adopt-fresh has something to adopt at soak start.
                fresh = (p == 0)
                opened = sim_hour - pd.Timedelta(minutes=30 if fresh else 300)
                long = ((hour_idx + p + ci) % 2 == 0)
                entry = px * (1.0005 if long else 0.9995)
                sgn = 1 if long else -1
                subs.append({
                    "phase": p, "label": f"khung +{p}h", "capital": PHASE_CAPITAL,
                    "state": "position",
                    "position": {
                        "side": "LONG" if long else "SHORT",
                        "weight": 0.03,
                        "avg_entry": entry,
                        "sl": entry * (1 - sgn * 3 * sig),
                        "tp": entry * (1 + sgn * 4 * sig),
                        "break_even": False,
                        "opened": str(opened),
                        "upnl_pct": 0.0,
                        "weight_sub": 0.12,
                    },
                })
        dips = []
        bar_open = px  # replay close ~ current 4h bar open proxy (offline)
        for p in range(4):
            for rung in DIP_RUNGS:
                lv = bar_open * (1 - rung * sig)
                # bot_soakfix B3 test-only clamp: keep the synthetic limit on a positive tick.
                try:
                    _tick = float(_SOAK_TICK.get(s, 0.0001))
                except (TypeError, ValueError):
                    _tick = 0.0001
                if not (lv == lv and lv > 0) or lv < _tick:
                    lv = max(_tick, bar_open * 1e-6 if bar_open > 0 else _tick)
                dips.append({
                    "rung": rung, "phase": p,
                    "buy_limit": lv, "tp": lv * 1.008,
                    "stop": lv * (1 - 4 * sig),                     "stop_kind": "close5",
                    "backstop": lv * (1 - 8 * sig),
                    "size_frac": 0.03,
                    "agent_size": 1.0, "agent_tp": 1.0,
                    "active_from": str(sim_hour + pd.Timedelta(minutes=16)),
                    "active_until": str(sim_hour + pd.Timedelta(hours=4) - pd.Timedelta(minutes=1)),
                    "filled": False,
                    "size_frac_sub": 0.08, "label": f"khung +{p}h",
                })
        coins[s] = {"symbol": s, "price": px, "target_weight": 0.0,
                    "state": "position", "subs": subs, "dips": dips,
                    "dip_size": 1.0, "position": None}
    return {"generated_at": str(sim_hour + pd.Timedelta(minutes=4)),
            "phases": phases, "coins": coins, "soak_synthetic": True,
            "soak_hour_idx": hour_idx}


# ----------------------------------------------------------------------------
# replay-aware fake exchange (prices follow the replay)
# ----------------------------------------------------------------------------
class ReplayMock(MockBybitV5):
    """MockBybitV5 whose public klines serve the replay slice <= sim_now."""

    def __init__(self, replay: dict, start: pd.Timestamp, window_end: pd.Timestamp, **kw):
        super().__init__(**kw)
        self.replay = replay
        self.sim_now = pd.Timestamp(start)
        # precomputed 4h opens per symbol (oldest-first) for the bear regime:
        # only the 2025 1m file (open column), clipped to the window end.
        # Jan-01..Oct-12 2025 gives ~1700 4h bars (>= the 1200 the bot asks for).
        self._opens4h = {}
        self._bars5m = {}
        for s in replay:
            self._opens4h[s] = self._load_opens4h(s, pd.Timestamp(window_end))
            df = replay[s].sort_values("open_time")
            g = df.groupby(df["open_time"].dt.floor("5min"))
            agg = g.agg(o=("open", "first"), h=("high", "max"),
                        l=("low", "min"), c=("close", "last")).reset_index()
            self._bars5m[s] = agg

    @staticmethod
    def _load_opens4h(sym: str, window_end: pd.Timestamp) -> list:
        if sym == "BTCUSDT":
            f = BTC_PARQUET_DIR / "klines_1m_2025.parquet"
        else:
            f = MAJORS_PARQUET_DIR / f"{sym}_1m_2025.parquet"
        df = pd.read_parquet(f, columns=["open_time", "open"],
                             filters=[("open_time", "<", window_end.to_pydatetime())])
        df = df.sort_values("open_time")
        bars = df.groupby(pd.Grouper(key="open_time", freq="4h")).first()
        return [float(x) for x in bars["open"].dropna().values]

    # -- kline serving -------------------------------------------------------
    def _bars_1m_upto(self, sym):
        df = self.replay[sym]
        now_min = self.sim_now.floor("min")
        past = df[df["open_time"] <= now_min]
        return past

    def _kline_rows(self, symbol, limit):
        past = self._bars_1m_upto(symbol)
        rows = []
        for _, r in past.tail(int(limit)).iloc[::-1].iterrows():
            ms = int(pd.Timestamp(r["open_time"]).timestamp() * 1000)
            rows.append([str(ms), str(r["open"]), str(r["high"]), str(r["low"]),
                         str(r["close"]), "1", "1"])
        # pad with flat rows when history is short (first minutes of window)
        while len(rows) < int(limit) and rows:
            rows.append(rows[-1])
        return rows

    def _kline(self, query):
        sym = query.get("symbol")
        interval = str(query.get("interval", "1"))
        limit = int(query.get("limit", 2) or 2)
        if interval == "240":
            end = query.get("end")
            opens = list(self._opens4h.get(sym, []))
            # replay opens are full-year; clip to sim_now's 4h bar count
            try:
                cur_bar = int(self.sim_now.floor("4h").timestamp() // (4 * 3600))
                first = int(pd.Timestamp("2025-01-01 00:00+00:00").timestamp() // (4 * 3600))
                opens = opens[: max(0, cur_bar - first + 1)]
            except Exception:
                pass
            n = min(limit, 1200, len(opens))
            now_ms = int(self.sim_now.timestamp() * 1000)
            rows = [[str(now_ms - (n - 1 - i) * 14_400_000), str(px), str(px),
                     str(px), str(px), "1", "1"] for i, px in enumerate(opens[-n:])]
            return {"list": list(reversed(rows))}
        if interval == "5":
            agg = self._bars5m.get(sym)
            if agg is None or not len(agg):
                return {"list": self._kline_rows(sym, limit)}
            now5 = self.sim_now.floor("5min")
            past = agg[agg["open_time"] <= now5]
            rows = []
            for _, r in past.tail(limit).iloc[::-1].iterrows():
                ms = int(pd.Timestamp(r["open_time"]).timestamp() * 1000)
                rows.append([str(ms), str(r["o"]), str(r["h"]), str(r["l"]),
                             str(r["c"]), "1", "1"])
            while len(rows) < limit and rows:
                rows.append(rows[-1])
            return {"list": rows}
        return {"list": self._kline_rows(sym, limit)}


# ----------------------------------------------------------------------------
# fake clock: Runner.cycle uses pd.Timestamp.now + time.time
# ----------------------------------------------------------------------------
class FakeClock:
    def __init__(self, start: pd.Timestamp):
        self.now = pd.Timestamp(start)
        self._orig_ts_now = pd.Timestamp.now
        self._orig_time = time.time

    def set(self, t: pd.Timestamp):
        self.now = pd.Timestamp(t)

    def install(self):
        now = self.now

        def _ts_now(cls=None, tz=None):
            return now.tz_convert(tz) if getattr(now, "tzinfo", None) is not None and tz else now

        pd.Timestamp.now = classmethod(lambda cls, tz=None: _ts_now(tz=tz))
        time.time = lambda: float(now.timestamp())

    def refresh(self):
        self.install()

    def restore(self):
        pd.Timestamp.now = self._orig_ts_now
        time.time = self._orig_time


def _patch_http(mock: MockBybitV5):
    orig_get, orig_post = requests.Session.get, requests.Session.post

    def fake_get(session_self, url, params=None, **kw):
        return FakeResponse(mock._http("GET", url, params=params, data=None))

    def fake_post(session_self, url, data=None, **kw):
        return FakeResponse(mock._http("POST", url, params=None, data=data))

    requests.Session.get = fake_get
    requests.Session.post = fake_post
    return orig_get, orig_post


class FakeResponse:
    def __init__(self, envelope):
        self._env = envelope

    def raise_for_status(self):
        return None

    def json(self):
        return self._env


# ----------------------------------------------------------------------------
# invariants
# ----------------------------------------------------------------------------
def check_invariants(runner, mock: MockBybitV5, equity: float, first_seen: dict,
                     sim_now: pd.Timestamp) -> list:
    """Return list of violation dicts for this cycle (empty = clean)."""
    viol = []
    ledger = (runner.state or {}).get("ledger") or {}
    resting = dict(mock.orders)
    # 1. every open piece has native protection (TP + stop rest on exchange)
    for pid, pc in ledger.items():
        try:
            qty = float(pc.get("qty", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if not qty > 0:
            continue
        # exit in flight (<2 min): bot_bookgap rule carries no other resting order
        try:
            sent = pc.get("exit_sent")
            if sent is not None and 0 <= (sim_now - pd.Timestamp(sent)).total_seconds() / 60 < 2.0:
                continue
        except (TypeError, ValueError, AttributeError):
            pass
        # 1-cycle placement grace: a piece filled seconds ago has no exits yet
        # (BOT_EXECUTION.md known caveat: <= 20 s until the next cycle places them)
        age_s = (sim_now - pd.Timestamp(first_seen.get(pid, sim_now))).total_seconds()
        has_tp, has_stop = (pid + "T") in resting, (pid + "S") in resting
        if not (has_tp and has_stop):
            if age_s < 90:
                continue
            viol.append({"invariant": "protection", "piece": pid,
                         "symbol": pc.get("symbol"), "qty": qty,
                         "have_tp": has_tp, "have_stop": has_stop,
                         "age_s": round(age_s, 1)})
    # 2. no duplicate links
    if len(resting) != len(set(resting)):
        viol.append({"invariant": "duplicate_links", "n": len(resting)})
    state_links = ((runner.state or {}).get("links") or {})
    for link in resting:
        if link not in state_links:
            viol.append({"invariant": "unknown_link", "link": link})
            break
    # 3. no orders for non-majors
    for link, o in resting.items():
        if o.get("symbol") not in SYMS:
            viol.append({"invariant": "non_major_order", "link": link,
                         "symbol": o.get("symbol")})
            break
    # 4. gross dip notional <= 2 x G x sub equity, per phase (hard safety bound)
    try:
        eq = float(equity)
    except (TypeError, ValueError):
        eq = 0.0
    if eq > 0:
        open_notion = {}
        for pc in ledger.values():
            if not isinstance(pc, dict) or pc.get("kind") != "dip":
                continue
            try:
                q = float(pc.get("qty", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if q <= 0:
                continue
            entry = pc.get("entry", pc.get("entry_px")) or 0.0
            try:
                entry = float(entry)
            except (TypeError, ValueError):
                continue
            ph = pc.get("phase", 0)
            open_notion[ph] = open_notion.get(ph, 0.0) + q * entry
        rest_notion = {}
        links = state_links
        for link in resting:
            try:
                meta = ((links.get(link) or {}).get("order") or {}).get("meta") or {}
            except (AttributeError, TypeError):
                meta = {}
            if meta.get("kind") != "dip":
                continue
            o = resting[link]
            try:
                rest_notion[meta.get("phase", 0)] = rest_notion.get(meta.get("phase", 0), 0.0) + float(o.get("qty", 0)) * float(o.get("price", 0))
            except (TypeError, ValueError):
                continue
        for ph in set(list(open_notion) + list(rest_notion)):
            sub_eq = eq * PHASE_CAPITAL
            bound = 2 * DIP_GROSS_CAP_G * sub_eq
            tot = open_notion.get(ph, 0.0) + rest_notion.get(ph, 0.0)
            if tot > bound + 1e-6:
                viol.append({"invariant": "dip_gross_cap", "phase": ph,
                             "total": round(tot, 2), "bound": round(bound, 2)})
    # 5. carry pair hedged within 2 cycles: no position stays single-filled
    # longer than MAX_UNHEDGED_CYCLES (bot/carry.py: MAX_UNHEDGED_CYCLES = 2).
    # Offline the soak has no dated quotes so positions stay empty; the check
    # still runs every cycle so a future quote source cannot regress silently.
    try:
        cpos = ((runner.state or {}).get("carry") or {}).get("positions") or {}
    except (AttributeError, TypeError):
        cpos = {}
    try:
        citems = list(cpos.items()) if isinstance(cpos, dict) else []
    except AttributeError:
        citems = []
    for coin, pos in citems:
        if not isinstance(pos, dict):
            continue
        try:
            n = int(pos.get("unhedged_cycles", 0) or 0)
        except (TypeError, ValueError):
            n = 0
        try:
            sf = bool(pos.get("spot_filled"))
            ff = bool(pos.get("fut_filled"))
        except AttributeError:
            continue
        if (sf != ff) and n > 2:
            viol.append({"invariant": "carry_unhedged", "coin": coin,
                         "cycles": n, "spot_filled": sf, "fut_filled": ff})
    return viol


# ----------------------------------------------------------------------------
# main soak
# ----------------------------------------------------------------------------
def run_soak(hours: float = 24.0, step_s: float = 20.0, equity: float = 10000.0,
             workdir: str | Path | None = None, tag: str = "soak",
             window_start: pd.Timestamp | None = None,
             plan_every_min: float = 60.0) -> dict:
    """Run the accelerated soak; return a results dict (JSON-serialisable)."""
    tracemalloc.start()
    start_ts = pd.Timestamp(window_start) if window_start is not None else WINDOW_START
    replay = load_replay(start_ts, hours)
    n_minutes = int(hours * 60)
    total_cycles = int(hours * 3600 / step_s)

    workdir = Path(workdir) if workdir else Path.cwd() / f"soak_{tag}"
    workdir.mkdir(parents=True, exist_ok=True)

    import bot.run as runmod

    window_end = start_ts + pd.Timedelta(hours=hours)
    mock = ReplayMock(replay, start_ts, window_end, equity=equity)
    # prices start at the first bar close
    for s in SYMS:
        mock.set_price(s, float(replay[s]["close"].iloc[0]))

    orig_root = runmod.ROOT
    runmod.ROOT = workdir
    for d in ("BYBIT_TESTNET_API_KEY", "BYBIT_TESTNET_API_SECRET"):
        os.environ.setdefault(d, "dummy-soak")
    orig_get, orig_post = _patch_http(mock)
    clock = FakeClock(start_ts)
    clock.install()

    plan_path = workdir / f"plan_{tag}.json"
    plan_path.write_text(json.dumps(make_plan(start_ts.floor("h"), replay, 0), default=str))
    try:
        runner = runmod.Runner("testnet", plan_path, None, tag=tag,
                               risk_mult=1.0, corr=True, dip_mult=1.7,
                               bear_book=True, dip_cooldown_h=0.0,
                               dip_sl_coin={}, dip_gross_cap=DIP_GROSS_CAP_G,
                               adopt_fresh=True, carry_f=0.25)
        runner._kline_cache_dir_override = str(workdir / f"kcache_{tag}")
        # Offline soak: no dated-futures/spot quote source exists, so contract
        # discovery would fail every cycle after 2.4 s of retry sleeps
        # (scripts/carry_paper.py _call_public x bot/carry.py _carry_cycle;
        # reported in BOT_SOAK_20261006.md). The bot's own test seam yields the
        # identical offline outcome (no contracts -> no carry orders) with the
        # _carry_cycle code path (sync/decide/guard) still executed each cycle.
        runner._carry_contracts_override = {}
        runner._carry_quotes_override = {}
        cycle_times, violations = [], []
        first_seen: dict = {}
        last_bar_idx = {s: 0 for s in SYMS}
        state_sizes, log_sizes, mem = [], [], []
        exc_count = 0
        sim_now = pd.Timestamp(start_ts)
        last_plan_hour = None
        hour_idx = 0
        for i in range(total_cycles):
            sim_now = pd.Timestamp(start_ts) + pd.Timedelta(seconds=(i + 1) * step_s)
            clock.set(sim_now)
            clock.refresh()
            mock.sim_now = sim_now
            # hourly synthetic plan refresh (stale threshold is 4h30m)
            cur_hour = sim_now.floor("h")
            if last_plan_hour is None or cur_hour > last_plan_hour:
                hour_idx = int((cur_hour - start_ts).total_seconds() // 3600)
                plan_path.write_text(json.dumps(make_plan(cur_hour, replay, hour_idx), default=str))
                last_plan_hour = cur_hour
            t0 = time.perf_counter()
            # NOTE: time.time is faked; use perf_counter for wall time
            try:
                with outsider_perf():
                    runner.cycle()
            except Exception as e:  # noqa: BLE001 (soak must never die on a cycle)
                exc_count += 1
                violations.append({"invariant": "cycle_exception", "cycle": i,
                                   "error": f"{type(e).__name__}: {e}"[:300]})
            dt_ms = (time.perf_counter() - t0) * 1000.0
            cycle_times.append(round(dt_ms, 2))
            for pid in (runner.state.get("ledger") or {}):
                first_seen.setdefault(pid, sim_now)
            try:
                eq = runner.ex.equity_usdt()
            except Exception:
                eq = equity
            # Check BEFORE replaying bars: the bot's cycle N decides on fills
            # synced at N start; bars replayed after the check create fills for
            # cycle N+1. Checking after process_bar would flag pieces whose
            # stop filled seconds ago but whose ledger syncs next cycle.
            for v in check_invariants(runner, mock, eq, first_seen, sim_now):
                violations.append({"cycle": i, "t": str(sim_now), **v})
            # fill newly closed 1m bars (trade-through, stop-first in mock)
            for s in SYMS:
                df = replay[s]
                while last_bar_idx[s] < len(df):
                    row = df.iloc[last_bar_idx[s]]
                    if pd.Timestamp(row["open_time"]) + pd.Timedelta(minutes=1) > sim_now:
                        break
                    t_ms = int(pd.Timestamp(row["open_time"]).timestamp() * 1000)
                    mock.process_bar(s, float(row["open"]), float(row["high"]),
                                     float(row["low"]), float(row["close"]), t_ms)
                    last_bar_idx[s] += 1
            if i % 180 == 0 or i == total_cycles - 1:  # every simulated hour
                print(f"[soak] cycle {i + 1}/{total_cycles} t={sim_now} "
                      f"resting={len(mock.orders)} ledger={len(runner.state.get('ledger') or {})} "
                      f"eq={round(eq, 1)} viol={len(violations)}", flush=True)
                try:
                    state_sizes.append([str(sim_now), (runner.state_f.stat().st_size)])
                except OSError:
                    pass
                try:
                    alog = runner.dir / "actions.jsonl"
                    log_sizes.append([str(sim_now), alog.stat().st_size if alog.exists() else 0])
                except OSError:
                    pass
                cur, peak = tracemalloc.get_traced_memory()
                mem.append([str(sim_now), cur, peak])
            if i == total_cycles // 2:  # bot_soak2: ONE restart mid-replay
                mid_ledger_before = copy.deepcopy(runner.state.get("ledger"))
                mid_orders_before = sorted(mock.orders.keys())
                runner_mid = runmod.Runner("testnet", plan_path, None, tag=tag,
                                           risk_mult=1.0, corr=True, dip_mult=1.7,
                                           bear_book=True, dip_cooldown_h=0.0,
                                           dip_sl_coin={}, dip_gross_cap=DIP_GROSS_CAP_G,
                                           adopt_fresh=True, carry_f=0.25)
                runner_mid._kline_cache_dir_override = str(workdir / f"kcache_{tag}")
                runner_mid._carry_contracts_override = {}
                runner_mid._carry_quotes_override = {}
                mid_adopted = copy.deepcopy(runner_mid.state.get("ledger"))
                mid_restart_ok = (mid_adopted == mid_ledger_before)
                mid_dup_entry = []
                try:
                    mid_acts = runner_mid.cycle()
                except Exception as e:  # noqa: BLE001
                    mid_acts = None
                    violations.append({"invariant": "restart_exception",
                                       "error": f"{type(e).__name__}: {e}"[:300]})
                if isinstance(mid_acts, list):
                    for a in mid_acts:
                        try:
                            o = a.get("order")
                            if a.get("op") == "place" and getattr(o, "kind", "") == "entry":
                                if getattr(o, "piece", "") in (mid_ledger_before or {}):
                                    mid_dup_entry.append(getattr(o, "link", "?"))
                        except AttributeError:
                            continue
                if not mid_restart_ok:
                    violations.append({"invariant": "restart_ledger_mismatch",
                                       "before_pieces": sorted((mid_ledger_before or {}).keys()),
                                       "after_pieces": sorted((runner_mid.state.get("ledger") or {}).keys())})
                if mid_dup_entry:
                    violations.append({"invariant": "restart_duplicate_entry", "links": mid_dup_entry})
                print(f"[soak] mid-replay restart at cycle {i + 1}/{total_cycles} t={sim_now} "
                      f"ok={bool(mid_restart_ok and not mid_dup_entry)} "
                      f"pieces={len(mid_ledger_before or {})} resting={len(mid_orders_before)}", flush=True)
                runner = runner_mid  # continue the replay on the restarted Runner
                for pid in (runner.state.get("ledger") or {}):
                    first_seen.setdefault(pid, sim_now)
        # mid-replay restart outcome (the single restart for bot_soak2)
        try:
            restart_ok = bool(mid_restart_ok and not mid_dup_entry)
            ledger_before = mid_ledger_before
            orders_before = mid_orders_before
            dup_entry = list(mid_dup_entry)
        except NameError:
            # total_cycles == 0 guard (never in practice): report a failed restart
            restart_ok, ledger_before, orders_before, dup_entry = False, {}, [], []
            violations.append({"invariant": "restart_exception",
                               "error": "mid-replay restart never ran"})
        try:
            final_state_b = runner.state_f.stat().st_size
        except OSError:
            final_state_b = 0
        try:
            alog = runner.dir / "actions.jsonl"
            final_log_b = alog.stat().st_size if alog.exists() else 0
        except OSError:
            final_log_b = 0
        cur, peak = tracemalloc.get_traced_memory()
        import numpy as np

        ct = np.array(cycle_times, dtype=float) if cycle_times else np.array([0.0])
        res = {
            "window_start": str(start_ts), "window_end": str(start_ts + pd.Timedelta(hours=hours)),
            "hours": hours, "step_s": step_s, "cycles": len(cycle_times),
            "minutes_replayed": n_minutes,
            "flags": {"corr": True, "dip_mult": 1.7, "bear_book": True,
                      "dip_gross_cap": DIP_GROSS_CAP_G, "adopt_fresh": True, "carry_f": 0.25},
            "plan": "synthetic hourly plans in trade_plan_v376.json shape (offline; carry legs have no dated quotes offline)",
            "equity_start": equity, "equity_end": runner.ex.equity_usdt(),
            "fills": len(getattr(mock, "execs", [])),
            "resting_end": len(mock.orders),
            "ledger_pieces": len(runner.state.get("ledger") or {}),
            "exceptions": exc_count,
            "violations": violations,
            "cycle_ms": {"mean": round(float(ct.mean()), 2),
                         "p50": round(float(np.median(ct)), 2),
                         "p95": round(float(np.percentile(ct, 95)), 2),
                         "max": round(float(ct.max()), 2),
                         "n": int(ct.size)},
            "state_json_bytes": {"series": state_sizes, "final": final_state_b},
            "actions_log_bytes": {"series": log_sizes, "final": final_log_b},
            "tracemalloc_bytes": {"series": mem, "final_current": cur, "final_peak": peak},
            "restart": {"ok": bool(restart_ok and not dup_entry),
                        "ledger_equal": bool(restart_ok),
                        "duplicate_entries": dup_entry,
                        "resting_before": len(orders_before),
                        "resting_after": len(mock.orders)},
        }
        (workdir / f"soak_result_{tag}.json").write_text(json.dumps(res, indent=1, default=str))
        return res
    finally:
        clock.restore()
        requests.Session.get, requests.Session.post = orig_get, orig_post
        runmod.ROOT = orig_root


class outsider_perf:
    """No-op context: wall time is measured with perf_counter (time.time is faked)."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Accelerated BOT soak (24h replay, fake clock).")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--step-s", type=float, default=20.0)
    ap.add_argument("--equity", type=float, default=10000.0)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--tag", default="soak")
    ap.add_argument("--window-start", default=str(WINDOW_START))
    args = ap.parse_args(argv)
    import tempfile

    wd = args.workdir or tempfile.mkdtemp(prefix="bot_soak_")
    res = run_soak(hours=args.hours, step_s=args.step_s, equity=args.equity,
                   workdir=wd, tag=args.tag,
                   window_start=pd.Timestamp(args.window_start))
    print(json.dumps({k: v for k, v in res.items()
                      if k not in ("violations", "state_json_bytes",
                                  "actions_log_bytes", "tracemalloc_bytes")}, indent=1, default=str))
    print(f"violations={len(res['violations'])} workdir={wd}")
    return 0 if (res["exceptions"] == 0 and res["restart"]["ok"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
