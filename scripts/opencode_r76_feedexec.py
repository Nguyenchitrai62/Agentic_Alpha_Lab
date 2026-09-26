"""R76 feed + execution core: official USD-M feed + engine-parity incremental execution.

EXPLORATORY (research plumbing, not a production bot). Paper/simulated only:
public klines GET (no keys), no orders, no exchange credentials, no scheduler.

FEED (mission item 3):
  - Official USD-M endpoint GET https://fapi.binance.com/fapi/v1/klines
    (doc: Binance Open Platform USD-S-M Futures Market Data REST API,
    "Kline Candlestick Data"). Fixes round75 Spot /api/v3/klines misuse.
  - Forming candle dropped; only closed candles ingested.
  - observed_at (fetch time) recorded separately from decision_time (stride fire).
  - Reject with DISTINCT status codes: STALE / DUPLICATE / OUT_OF_ORDER /
    INCOMPLETE / MARKET_MISMATCH; WARMUP until warmup_bars accepted.
  - Full decision only on anchor/stride bars (declared stride, W1 manifest
    absent); other bars settle execution with SKIP_CLOCK.
  - Replay vs fresh get DISTINCT manifests; fresh mode REFUSES replay inputs
    (no stored signals/predictions/control-exit CSVs, no bar-index matching).

EXECUTION (mission item 4):
  - Fill helpers imported from the audited engine bit-for-bit (next-bar entry,
    pending expiry/cancel, stop-first, entry-bar target suppression,
    fees/funding, timeout, truncated-window rejection).
  - TP1 50% partial exit THEN TP2 (fixes the v1/v2/v21 TP1 omission).
  - Causal separate control account iso4_only_1x (own realized equity only;
    no future expected-equity reference). Guards reuse v1.DdGuard,
    v2.DailyLossHalt and v2.1 OneSidedDivergenceMonitor.check() UNMODIFIED;
    only expected_at() is repointed to the causal control account.
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from agentic_alpha_lab.backtest import engine as bt_engine  # noqa: E402
import opencode_paper_trader as v1  # noqa: E402  (v1 stays UNMODIFIED)
import opencode_paper_trader_v2 as v2  # noqa: E402  (v2 stays UNMODIFIED)
import opencode_paper_trader_v21 as v21  # noqa: E402  (v2.1 stays UNMODIFIED)

MODE_LABEL = "SIMULATED/PAPER-research-feedexec"
STATE_VERSION = "r76_feedexec_state/1"
ALERT_PREFIX = "r76-"

# Official USD-M public klines endpoint (doc-verified 2026-09-11).
FAPI_HOST = "https://fapi.binance.com"
FAPI_PATH = "/fapi/v1/klines"
FAPI_DOC = ("https://developers.binance.com/docs/derivatives/usds-margined-futures/"
            "market-data/rest-api/Kline-Candlestick-Data")

STATUS_OK = "OK"
STATUS_SKIP_CLOCK = "SKIP_CLOCK"
STATUS_WARMUP = "WARMUP"
STATUS_STALE = "STALE"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_OUT_OF_ORDER = "OUT_OF_ORDER"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_MARKET_MISMATCH = "MARKET_MISMATCH"

CANDLE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time"]

# Replay-only input keys that fresh mode must never touch.
REPLAY_INPUT_KEYS = ("signals", "predictions", "control_exits", "baseline",
                     "baseline_signals", "baseline_trades")


# ---------------------------------------------------------------- feed ---
def build_klines_url(host: str = FAPI_HOST, path: str = FAPI_PATH,
                     symbol: str = "BTCUSDT", interval: str = "5m",
                     limit: int = 500) -> str:
    qs = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": int(limit)})
    return f"{host}{path}?{qs}"


def fetch_public_klines(symbol: str = "BTCUSDT", interval: str = "5m",
                        limit: int = 500, timeout_seconds: int = 20,
                        host: str = FAPI_HOST, path: str = FAPI_PATH) -> tuple[list, str]:
    """Public market-data GET only (no keys, no orders). Returns (raw_rows, url)."""
    url = build_klines_url(host, path, symbol, interval, limit)
    req = urllib.request.Request(url, headers={"User-Agent": "agentic-alpha-lab-r76-feedexec/1"})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        return json.loads(resp.read().decode("utf-8")), url


def row_hash(open_ms: int, o: float, h: float, lo: float, c: float, v: float) -> str:
    body = f"{int(open_ms)}|{float(o):.8f}|{float(h):.8f}|{float(lo):.8f}|{float(c):.8f}|{float(v):.8f}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def parse_closed_klines(raw_rows: list, now_ms: int, symbol: str = "BTCUSDT",
                        interval: str = "5m", observed_at: str = "") -> list[dict]:
    """Map raw fapi klines to candle dicts; DROP the forming candle."""
    out = []
    for r in raw_rows:
        open_ms, o, h, lo, c, v, close_ms = (int(r[0]), float(r[1]), float(r[2]),
                                            float(r[3]), float(r[4]), float(r[5]), int(r[6]))
        if close_ms > now_ms:
            continue  # forming candle: not closed yet
        out.append({"open_time": pd.Timestamp(open_ms, unit="ms", tz="UTC"),
                    "open": o, "high": h, "low": lo, "close": c, "volume": v,
                    "close_time": pd.Timestamp(close_ms, unit="ms", tz="UTC"),
                    "symbol": symbol, "interval": interval, "market": "USDM",
                    "observed_at": observed_at,
                    "row_hash": row_hash(open_ms, o, h, lo, c, v)})
    return sorted(out, key=lambda d: d["open_time"])


class FeedState:
    """Causal ingest gate: distinct reject codes, warmup, provenance."""

    def __init__(self, symbol: str = "BTCUSDT", interval: str = "5m",
                 expected_bar_seconds: int = 300, warmup_bars: int = 12):
        self.symbol = symbol
        self.interval = interval
        self.expected_bar_seconds = expected_bar_seconds
        self.warmup_bars = warmup_bars
        self.last_open_ms: int | None = None
        self.seen_hashes: set[str] = set()
        self.n_accepted = 0
        self.counters: dict[str, int] = {}

    def _count(self, status: str) -> str:
        self.counters[status] = self.counters.get(status, 0) + 1
        return status

    def validate(self, candle: dict) -> str:
        if candle.get("symbol") != self.symbol or candle.get("interval") != self.interval:
            return self._count(STATUS_MARKET_MISMATCH)
        try:
            o, h, lo, c, v = (float(candle["open"]), float(candle["high"]),
                              float(candle["low"]), float(candle["close"]),
                              float(candle["volume"]))
            open_ms = int(pd.Timestamp(candle["open_time"]).value // 10 ** 6)
        except (TypeError, ValueError, KeyError):
            return self._count(STATUS_INCOMPLETE)
        if not (h >= lo and h >= o and h >= c and lo <= o and lo <= c and v >= 0):
            return self._count(STATUS_INCOMPLETE)
        digest = candle.get("row_hash") or row_hash(open_ms, o, h, lo, c, v)
        if digest in self.seen_hashes:
            return self._count(STATUS_DUPLICATE)
        if self.last_open_ms is not None and open_ms < self.last_open_ms:
            return self._count(STATUS_OUT_OF_ORDER)
        if self.last_open_ms is not None and open_ms == self.last_open_ms:
            return self._count(STATUS_STALE)
        self.seen_hashes.add(digest)
        self.last_open_ms = open_ms
        self.n_accepted += 1
        if self.n_accepted <= self.warmup_bars:
            return self._count(STATUS_WARMUP)
        return self._count(STATUS_OK)

    def snapshot(self) -> dict:
        return {"symbol": self.symbol, "interval": self.interval,
                "expected_bar_seconds": self.expected_bar_seconds,
                "warmup_bars": self.warmup_bars, "last_open_ms": self.last_open_ms,
                "n_accepted": self.n_accepted, "counters": self.counters}

    def restore(self, snap: dict) -> None:
        if (snap.get("symbol") != self.symbol or snap.get("interval") != self.interval
                or int(snap.get("warmup_bars", -1)) != self.warmup_bars):
            raise ValueError("FeedState mismatch on restore (refusing).")
        self.last_open_ms = snap["last_open_ms"]
        self.n_accepted = int(snap["n_accepted"])
        self.counters = dict(snap.get("counters", {}))


def should_decide(bar_index: int, anchor: int = 0, stride: int = 12) -> bool:
    return (int(bar_index) - int(anchor)) % int(stride) == 0


def save_warmup_cache(path: Path, candles: list[dict], provenance: dict) -> None:
    path = Path(path)
    if path.exists() or path.with_suffix(".provenance.json").exists():
        raise FileExistsError(f"Refusing to overwrite cache: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(candles)
    frame.to_parquet(path, index=False)
    prov = dict(provenance)
    prov["row_hashes"] = [c["row_hash"] for c in candles]
    prov["n_rows"] = len(candles)
    path.with_suffix(".provenance.json").write_text(json.dumps(prov, indent=1, default=str))


def _refuse_replay_inputs(source: dict, mode: str) -> None:
    if mode != "fresh":
        return
    hits = [k for k in REPLAY_INPUT_KEYS if source.get(k)]
    if hits:
        raise ValueError(f"fresh mode REFUSES replay inputs {hits}: no stored signals / "
                         "predictions / control-exit CSVs and no bar-index matching.")


def build_manifest(kind: str, *, config: dict, source: dict, feed_state: FeedState,
                   clock: dict, provenance: dict | None = None) -> dict:
    if kind not in ("replay", "fresh"):
        raise ValueError("manifest kind must be 'replay' or 'fresh' (distinct, never mixed).")
    if kind == "fresh":
        _refuse_replay_inputs(source, "fresh")
    manifest = {"kind": f"{kind.upper()}-OBSERVATION" if kind == "fresh" else "REHEARSAL-NOT-LIVE",
                "mode": MODE_LABEL, "exploratory": True, "live_orders": False,
                "feedexec_version": "r76_feedexec/1",
                "feed": {"host": FAPI_HOST, "path": FAPI_PATH, "doc": FAPI_DOC,
                         "symbol": feed_state.symbol, "interval": feed_state.interval,
                         "market": "USDM"},
                "clock": clock,
                "feed_counters": feed_state.counters,
                "n_accepted": feed_state.n_accepted,
                "source": source}
    if provenance is not None:
        manifest["provenance"] = provenance
    _ = config  # config snapshot is embedded by the caller (summary), not here
    return manifest


# ------------------------------------------------------------ execution ---
class FeedExecAccount:
    """Incremental paper account with EXACT engine ohlc-v2 exit semantics.

    One position at a time (pending XOR open, fail-closed). Exit order per
    bar: funding -> liquidation (None at 1x) -> stop (full) -> TP1 50%
    partial -> TP2 remainder -> timeout at exit-bar open. Entry-bar targets
    suppressed unless entered at/through the open. Reuses bt_engine fill
    helpers bit-for-bit.
    """

    def __init__(self, initial_equity: float, fee_rate: float,
                 funding_long_rate: float, funding_short_rate: float,
                 funding_interval_hours: int, entry_expiry_bars: int,
                 tp1_fraction: float = 0.5, name: str = "operating"):
        self.equity = float(initial_equity)
        self.fee_rate = float(fee_rate)
        self.funding_long_rate = float(funding_long_rate)
        self.funding_short_rate = float(funding_short_rate)
        self.funding_interval_hours = int(funding_interval_hours)
        self.entry_expiry_bars = int(entry_expiry_bars)
        self.tp1_fraction = float(tp1_fraction)
        self.name = name
        self.pending: dict | None = None
        self.open: dict | None = None
        self.exits = 0
        self.rejected = 0
        self.events: list[dict] = []

    # -- helpers ---------------------------------------------------------
    def _funding_charge(self, bar: pd.Series, direction: int, notional: float,
                        entry_price: float, remaining: float) -> float:
        if not bt_engine._is_funding_time(pd.Timestamp(bar["open_time"]),  # noqa: SLF001
                                          self.funding_interval_hours):
            return 0.0
        rate = self.funding_long_rate if direction == 1 else self.funding_short_rate
        charge = notional / entry_price * float(bar["open"]) * remaining * rate
        self.equity -= charge
        return charge

    def _assert_single(self) -> None:
        if self.pending is not None and self.open is not None:
            raise AssertionError(f"[{self.name}] pending AND open set (allows 1).")

    # -- signal intake ----------------------------------------------------
    def arm_pending(self, signal: dict) -> str:
        """Arm a pending entry. Returns 'ARMED' or a skip reason (BUSY)."""
        self._assert_single()
        if self.pending is not None or self.open is not None:
            return "BUSY"
        for key in ("signal_bar", "direction", "entry_limit", "stop_loss",
                    "take_profit_1", "take_profit_2", "holding_bars",
                    "leverage", "notional", "equity_before"):
            if key not in signal:
                raise ValueError(f"[{self.name}] signal lacks {key} (refusing).")
        bar = int(signal["signal_bar"])
        self.pending = {**signal, "signal_bar": bar,
                        "entry_start_bar": bar + 1,
                        "entry_last_bar": bar + self.entry_expiry_bars}
        return "ARMED"

    # -- per-bar settlement ------------------------------------------------
    def on_bar_close(self, bar_idx: int, bar: pd.Series,
                     n_bars: int | None = None) -> list[dict]:
        """Settle pending/open on closed bar ``bar_idx``. Returns fill events."""
        self._assert_single()
        out: list[dict] = []
        if self.pending is not None:
            p = self.pending
            assert bar_idx > p["signal_bar"], "entry sought on/before signal bar (lookahead bug)"
            if bar_idx > p["entry_last_bar"]:
                self.pending = None
                self.rejected += 1
                out.append({"account": self.name, "kind": "CANCEL", "reason": "expired",
                            "signal_bar": p["signal_bar"], "bar_idx": bar_idx})
            else:
                fill = bt_engine._entry_fill(bar, p["direction"], float(p["entry_limit"]))  # noqa: SLF001
                if fill is not None:
                    holding = int(p["holding_bars"])
                    if n_bars is not None and bar_idx + holding >= n_bars:
                        self.pending = None
                        self.rejected += 1
                        out.append({"account": self.name, "kind": "CANCEL",
                                    "reason": "truncated", "signal_bar": p["signal_bar"],
                                    "bar_idx": bar_idx})
                    else:
                        notional = float(p["notional"])
                        entry_fee = notional * self.fee_rate
                        self.equity -= entry_fee
                        liq = bt_engine._liquidation_price(  # noqa: SLF001
                            float(fill), int(p["direction"]), float(p["leverage"]), 0.005)
                        self.open = {**p, "entry_bar": bar_idx,
                                     "entry_price": float(fill), "fees": entry_fee,
                                     "funding": 0.0, "remaining": 1.0, "tp1_done": False,
                                     "gross": 0.0, "entry_open": float(bar["open"]),
                                     "entered_this_bar": True,
                                     "liquidation_price": liq}
                        self.pending = None
                        out.append({"account": self.name, "kind": "ENTRY",
                                    "signal_bar": p["signal_bar"], "bar_idx": bar_idx,
                                    "price": float(fill), "fee": entry_fee})
        if self.open is not None:
            out.extend(self._manage_open(bar_idx, bar))
        return out

    def _close_leg(self, exit_price: float, fraction: float, reason: str,
                   bar_idx: int, final: bool) -> dict:
        o = self.open
        assert o is not None
        notional = float(o["notional"])
        pnl = (int(o["direction"]) * (exit_price - o["entry_price"]) / o["entry_price"]
               * notional * fraction)
        exit_fee = notional * fraction * (exit_price / o["entry_price"]) * self.fee_rate
        o["gross"] += pnl
        o["fees"] += exit_fee
        self.equity += pnl - exit_fee
        o["remaining"] -= fraction
        ev = {"account": self.name, "kind": "EXIT", "reason": reason,
              "signal_bar": o["signal_bar"], "bar_idx": int(bar_idx),
              "price": float(exit_price), "fraction": float(fraction),
              "pnl": float(pnl), "fee": float(exit_fee)}
        if final:
            o["remaining"] = 0.0
            self.exits += 1
            ev["net_pnl"] = float(self.equity - o["equity_before"])
            ev["equity_after"] = float(self.equity)
            self.events.append({**ev, "entry_bar": o["entry_bar"],
                                "entry_price": o["entry_price"],
                                "fees": o["fees"], "funding": o["funding"],
                                "gross": o["gross"]})
            self.open = None
        return ev

    def _manage_open(self, bar_idx: int, bar: pd.Series) -> list[dict]:
        o = self.open
        assert o is not None
        out: list[dict] = []
        direction = int(o["direction"])
        # Timeout bar: engine settles at the exit bar's OPEN with no stop/TP
        # evaluation on that bar (range(entry, exit) excludes it).
        if bar_idx >= o["entry_bar"] + int(o["holding_bars"]):
            o["funding"] += self._funding_charge(bar, direction, float(o["notional"]),
                                                float(o["entry_price"]), float(o["remaining"]))
            reason = "time_after_tp1" if o["tp1_done"] else "time"
            out.append(self._close_leg(float(bar["open"]), float(o["remaining"]),
                                      reason, bar_idx, final=True))
            return out
        if bar_idx > o["entry_bar"]:
            o["funding"] += self._funding_charge(bar, direction, float(o["notional"]),
                                                float(o["entry_price"]), float(o["remaining"]))
        liq_fill = bt_engine._liquidation_fill(bar, direction, o["liquidation_price"])  # noqa: SLF001
        stop_fill = bt_engine._stop_fill(bar, direction, float(o["stop_loss"]))  # noqa: SLF001
        if liq_fill is not None and stop_fill is not None:
            opened_beyond = ((direction == 1 and float(bar["open"]) <= float(o["liquidation_price"]))
                             or (direction == -1 and float(bar["open"]) >= float(o["liquidation_price"])))
            stop_first = direction * (float(o["stop_loss"]) - float(o["liquidation_price"])) > 0
            if not opened_beyond and stop_first:
                liq_fill = None
        if liq_fill is not None:
            out.append(self._close_leg(float(liq_fill), float(o["remaining"]),
                                      "liquidation", bar_idx, final=True))
            return out
        if stop_fill is not None:  # stop-first: full remaining, TP never evaluated
            out.append(self._close_leg(float(stop_fill), float(o["remaining"]),
                                      "stop", bar_idx, final=True))
            return out
        entered_here = bool(o.pop("entered_this_bar", False)) and bar_idx == o["entry_bar"]
        entry_at_open = ((direction == 1 and o["entry_open"] <= float(o["entry_limit"]))
                         or (direction == -1 and o["entry_open"] >= float(o["entry_limit"])))
        allow_targets = (not entered_here) or entry_at_open
        if not o["tp1_done"] and allow_targets:
            tp1 = bt_engine._take_profit_fill(bar, direction, float(o["take_profit_1"]))  # noqa: SLF001
            if tp1 is not None:
                out.append(self._close_leg(float(tp1), self.tp1_fraction,
                                          "tp1", bar_idx, final=False))
                o = self.open
                assert o is not None
                o["tp1_done"] = True
        tp2 = (bt_engine._take_profit_fill(bar, direction, float(o["take_profit_2"]))  # noqa: SLF001
               if allow_targets else None)
        if o["remaining"] > 0 and tp2 is not None:
            out.append(self._close_leg(float(tp2), float(o["remaining"]),
                                      "tp2", bar_idx, final=True))
        return out

    # -- persistence -------------------------------------------------------
    def snapshot(self) -> dict:
        return {"equity": self.equity, "pending": self.pending, "open": self.open,
                "exits": self.exits, "rejected": self.rejected, "events": self.events}

    def restore(self, snap: dict) -> None:
        self.equity = float(snap["equity"])
        self.pending = snap["pending"]
        self.open = snap["open"]
        self.exits = int(snap["exits"])
        self.rejected = int(snap.get("rejected", 0))
        self.events = list(snap.get("events", []))


class ControlDivergenceTrip(v21.OneSidedDivergenceMonitor):
    """UNDER-only trip vs the CAUSAL control account (reuses v2.1 check logic).

    Only override: expected_at() reads the control account's realized equity
    trace (past-only forward-fill) instead of a frozen future curve.
    snapshot()/restore() carry the trace instead of static curve arrays.
    """

    def __init__(self, tolerance_pct: float, initial_equity: float):
        super().__init__([], [], tolerance_pct, initial_equity)
        self._control_trace: list[tuple[int, float]] = []

    def post_control_equity(self, bar_idx: int, equity: float) -> None:
        bar_idx = int(bar_idx)
        if self._control_trace and bar_idx <= self._control_trace[-1][0]:
            raise AssertionError("control trace must advance strictly (causality bug).")
        self._control_trace.append((bar_idx, float(equity)))

    def expected_at(self, bar_idx: int) -> float:
        bar_idx = int(bar_idx)
        past = [e for b, e in self._control_trace if b <= bar_idx]
        if not past:
            return self.initial_equity
        return float(past[-1])

    def snapshot(self) -> dict:
        snap = super().snapshot()
        snap["control_trace"] = [[b, e] for b, e in self._control_trace]
        snap.pop("n_curve_points", None)
        snap["causal_reference"] = "iso4_only_1x realized equity (past-only, no future curve)"
        return snap

    def restore(self, snap: dict) -> None:
        if snap.get("causal_reference") != "iso4_only_1x realized equity (past-only, no future curve)":
            raise ValueError("ControlDivergenceTrip refuses a non-causal snapshot (refusing).")
        super().restore(snap)
        self._control_trace = [(int(b), float(e)) for b, e in snap.get("control_trace", [])]


def deterministic_alert_id(kind: str, bar_idx: int, bar_time: str,
                           equity: float, note: str = "") -> str:
    body = f"{kind}|{int(bar_idx)}|{bar_time}|{float(equity):.6f}|{note}"
    return ALERT_PREFIX + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


class FeedExecStrategy:
    """Operating (gated) + control (ungated 1x) pair behind one on_bar().

    Guard (v1.DdGuard) sizes the operating account live from past-only paper
    equity; the control account stays fixed 1x. Daily-halt (v2) + UNDER-only
    divergence trip (v2.1 logic vs causal control equity) gate NEW intents;
    open positions always settle to exit. Alert IDs deterministic; emission
    exactly-once (dedupe by id).
    """

    INTENT_COLUMNS = ["signal_time", "side", "entry_limit", "tp1", "tp2", "sl",
                      "size", "guard_state", "signal_bar", "current_bar",
                      "entry_start_bar", "confidence", "leverage",
                      "equity_before", "control_equity", "divergence", "mode"]

    def __init__(self, config: dict, n_bars: int | None = None):
        for section in ("guard", "costs", "execution", "account",
                        "kill_switch", "divergence", "decision_clock"):
            if section not in config:
                raise ValueError(f"feedexec config lacks [{section}] (refusing).")
        self.config = config
        self.n_bars = n_bars
        g = config["guard"]
        c = config["costs"]
        pg = config["execution"]
        init = float(config["account"]["initial_equity_indexed"])
        mk = dict(initial_equity=init, fee_rate=c["fee_rate_per_fill"],
                  funding_long_rate=c["funding_long_rate"],
                  funding_short_rate=c["funding_short_rate"],
                  funding_interval_hours=c["funding_interval_hours"],
                  entry_expiry_bars=int(pg.get("entry_expiry_bars", 12)),
                  tp1_fraction=float(pg.get("tp1_fraction", 0.5) or 0.5))
        self.operating = FeedExecAccount(**mk, name="operating")
        self.control = FeedExecAccount(**mk, name="iso4_only_1x")
        self.guard = v1.DdGuard(g["dd_trigger"], g["guard_leverage"],
                                g["full_leverage"], init)
        ks = config["kill_switch"]
        if int(ks.get("max_positions", 1)) != 1:
            raise ValueError("kill_switch.max_positions must be 1.")
        self.daily_halt = v2.DailyLossHalt(ks["daily_loss_halt_pct"])
        dv = config["divergence"]
        self.trip = ControlDivergenceTrip(dv["tolerance_pct"], init)
        self.min_confidence = float(pg.get("min_confidence", 0.25))
        self.max_holding = int(pg.get("max_holding_bars", 2016))
        dc = config["decision_clock"]
        self.clock_anchor = int(dc.get("anchor_bar", 0))
        self.clock_stride = int(dc.get("stride_bars", 12))
        self.intents: list[dict] = []
        self.alerts: list[dict] = []
        self._emitted_ids: set[str] = set()
        self.bars_seen = 0
        self.signals_seen = 0
        self.skipped_clock = 0
        self.skipped_low_conf = 0
        self.skipped_busy = 0
        self.skipped_daily_halt = 0
        self.skipped_divergence = 0
        self._last_bar: int | None = None
        self._open_day: str | None = None

    # -- exactly-once alerts ------------------------------------------------
    def emit_alert(self, alert: dict) -> dict:
        aid = alert.get("alert_id") or deterministic_alert_id(
            alert.get("kind", "?"), alert.get("bar_idx", -1),
            str(alert.get("bar_time", "")), float(alert.get("equity_now",
                  alert.get("paper_equity", 0.0))), str(alert.get("direction", "")))
        alert = {**alert, "alert_id": aid}
        if aid not in self._emitted_ids:
            self._emitted_ids.add(aid)
            self.alerts.append(alert)
        return alert

    # -- strategy tick ------------------------------------------------------
    def on_bar(self, bar_idx: int, bar: pd.Series, decision: dict | None) -> dict | None:
        """One closed bar. ``decision`` is the frozen-policy output for THIS bar
        (or None when SKIP_CLOCK / no signal). Settles both accounts first."""
        if self._last_bar is not None and bar_idx <= self._last_bar:
            raise AssertionError("on_bar bars must be strictly increasing.")
        day = pd.Timestamp(bar["open_time"]).date().isoformat()
        bar_time_iso = pd.Timestamp(bar["close_time"]).isoformat()
        self.daily_halt.roll_day(day, self.operating.equity)
        self._open_day = day
        self.operating.on_bar_close(bar_idx, bar, self.n_bars)
        self.control.on_bar_close(bar_idx, bar, self.n_bars)
        self.trip.post_control_equity(bar_idx, self.control.equity)
        self.bars_seen += 1
        self._last_bar = bar_idx
        div_status = self.trip.check(bar_idx, self.operating.equity, bar_time_iso)
        if div_status is not None and div_status.get("status") == "TRIPPED_NOW":
            self.emit_alert({**div_status, "bar_time": bar_time_iso,
                             "equity_now": self.operating.equity})
        halted = self.daily_halt.evaluate(self.operating.equity, bar_time_iso, bar_idx)
        if halted:
            latest = self.daily_halt.halt_events[-1]
            self.emit_alert({**latest, "bar_idx": bar_idx, "bar_time": bar_time_iso,
                             "equity_now": self.operating.equity})
        for ev in self.trip.drain_over_alerts():
            self.emit_alert({**ev, "equity_now": self.operating.equity})
        if decision is None:
            return None
        if not should_decide(bar_idx, self.clock_anchor, self.clock_stride):
            self.skipped_clock += 1
            return None
        action, conf = decision.get("action", "FLAT"), float(decision.get("confidence", 0.0))
        if action == "FLAT" or conf < self.min_confidence:
            if action != "FLAT":
                self.skipped_low_conf += 1
            return None
        if div_status is not None:
            self.trip.blocks += 1
            self.skipped_divergence += 1
            return None
        if halted:
            self.skipped_daily_halt += 1
            return None
        # MaxPositionGuard is duck-typed on (pending/open): the r76 account carries
        # the same fields, so v2's audited invariant applies UNMODIFIED.
        if v2.MaxPositionGuard.blocks_new_intent(self.operating):
            self.skipped_busy += 1
            return None
        direction = 1 if action == "LONG" else -1
        leverage, state = self.guard.multiplier(pd.Timestamp(bar["close_time"]))
        size = self.operating.equity * leverage
        signal = {"signal_bar": bar_idx, "direction": direction,
                  "entry_limit": float(decision["entry_limit"]),
                  "stop_loss": float(decision["stop_loss"]),
                  "take_profit_1": float(decision["take_profit_1"]),
                  "take_profit_2": float(decision["take_profit_2"]),
                  "holding_bars": min(int(decision.get("holding_bars", self.max_holding)),
                                      self.max_holding),
                  "leverage": leverage, "notional": size,
                  "equity_before": self.operating.equity}
        armed = self.operating.arm_pending(signal)
        if armed != "ARMED":
            self.skipped_busy += 1
            return None
        # Control takes every admitted signal at fixed 1x (ungated mirror).
        self.control.arm_pending({**signal, "leverage": 1.0,
                                  "notional": self.control.equity,
                                  "equity_before": self.control.equity})
        self.signals_seen += 1
        expected = self.trip.expected_at(bar_idx)
        base_div = ((self.operating.equity - expected) / expected) if expected > 0 else 0.0
        intent = {"signal_time": bar_time_iso, "side": action,
                  "entry_limit": signal["entry_limit"], "tp1": signal["take_profit_1"],
                  "tp2": signal["take_profit_2"], "sl": signal["stop_loss"],
                  "size": size, "guard_state": state, "signal_bar": bar_idx,
                  "current_bar": bar_idx, "entry_start_bar": bar_idx + 1,
                  "confidence": conf, "leverage": leverage,
                  "equity_before": self.operating.equity,
                  "control_equity": self.control.equity, "divergence": base_div,
                  "mode": MODE_LABEL}
        assert intent["signal_bar"] < intent["entry_start_bar"]
        self.intents.append(intent)
        return intent

    # -- persistence ---------------------------------------------------------
    def snapshot_state(self) -> dict:
        return {"version": STATE_VERSION, "mode": MODE_LABEL, "exploratory": True,
                "last_bar": self._last_bar, "bars_seen": self.bars_seen,
                "n_bars": self.n_bars, "open_day": self._open_day,
                "operating": self.operating.snapshot(),
                "control": self.control.snapshot(),
                "dd_guard": {"exits": [[t.isoformat(), e] for t, e in self.guard._exits],  # noqa: SLF001
                             "history": self.guard.history,
                             "state_changes": self.guard.state_changes,
                             "last_state": self.guard._last_state},  # noqa: SLF001
                "daily_halt": self.daily_halt.snapshot(),
                "divergence": self.trip.snapshot(),
                "counters": {"signals_seen": self.signals_seen,
                             "skipped_clock": self.skipped_clock,
                             "skipped_low_conf": self.skipped_low_conf,
                             "skipped_busy": self.skipped_busy,
                             "skipped_daily_halt": self.skipped_daily_halt,
                             "skipped_divergence": self.skipped_divergence,
                             "intents": len(self.intents)},
                "intents": self.intents, "alerts": self.alerts,
                "emitted_ids": sorted(self._emitted_ids)}

    def restore_state(self, snap: dict) -> None:
        if snap.get("version") != STATE_VERSION:
            raise ValueError(f"state version mismatch: {snap.get('version')} (refusing).")
        if snap.get("mode") != MODE_LABEL:
            raise ValueError("state mode mismatch (refusing).")
        if snap.get("n_bars") != self.n_bars:
            raise ValueError("state horizon (n_bars) mismatch (refusing).")
        self._last_bar = snap["last_bar"]
        self.bars_seen = int(snap["bars_seen"])
        self._open_day = snap.get("open_day")
        self.operating.restore(snap["operating"])
        self.control.restore(snap["control"])
        gd = snap["dd_guard"]
        self.guard._exits = [(pd.Timestamp(t), float(e)) for t, e in gd["exits"]]  # noqa: SLF001
        self.guard.history = list(gd["history"])
        self.guard.state_changes = int(gd["state_changes"])
        self.guard._last_state = gd["last_state"]  # noqa: SLF001
        self.daily_halt.restore(snap["daily_halt"])
        self.trip.restore(snap["divergence"])
        c = snap["counters"]
        self.signals_seen = int(c["signals_seen"])
        self.skipped_clock = int(c.get("skipped_clock", 0))
        self.skipped_low_conf = int(c["skipped_low_conf"])
        self.skipped_busy = int(c["skipped_busy"])
        self.skipped_daily_halt = int(c["skipped_daily_halt"])
        self.skipped_divergence = int(c["skipped_divergence"])
        self.intents = list(snap.get("intents", []))
        self.alerts = list(snap.get("alerts", []))
        self._emitted_ids = set(snap.get("emitted_ids", []))


def run_replay(candles: pd.DataFrame, decisions: dict[int, dict],
               strategy: FeedExecStrategy) -> pd.DataFrame:
    """Walk closed candles (positional index IS the global bar_index)."""
    candles = candles.sort_values("open_time").reset_index(drop=True)
    for bar_idx in range(len(candles)):
        strategy.on_bar(bar_idx, candles.iloc[bar_idx], decisions.get(bar_idx))
    return pd.DataFrame(strategy.intents, columns=FeedExecStrategy.INTENT_COLUMNS)


def main() -> None:
    ap = argparse.ArgumentParser(description="R76 feed+exec replay/fresh runner (PAPER ONLY).")
    ap.add_argument("--config", type=Path, default=Path("configs/opencode_r76_feedexec.json"))
    ap.add_argument("--mode", choices=("replay", "fresh"), required=True)
    ap.add_argument("--candles", type=str, default="",
                    help="replay: parquet path; fresh: 'live' (public fapi fetch only)")
    ap.add_argument("--signals", type=Path, default=None,
                    help="replay only: frozen signals parquet (REFUSED in fresh mode)")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / a.config).read_text())
    if config.get("allow_live_orders", True):
        raise SystemExit("REFUSED: allow_live_orders must stay false (paper only).")
    out = root / a.out
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {out}")
    feed = FeedState(symbol=config["feed"]["symbol"], interval=config["feed"]["interval"],
                     expected_bar_seconds=config["feed"]["expected_bar_seconds"],
                     warmup_bars=config["feed"]["warmup_bars"])
    if a.mode == "fresh":
        _refuse_replay_inputs({"signals": str(a.signals) if a.signals else ""}, "fresh")
        if a.candles != "live":
            raise SystemExit("REFUSED: fresh mode only ingests live public klines (--candles live).")
        import time
        raw, url = fetch_public_klines(symbol=feed.symbol, interval=feed.interval,
                                       limit=a.limit,
                                       timeout_seconds=config["feed"]["timeout_seconds"])
        observed_at = pd.Timestamp(time.time(), unit="s", tz="UTC").isoformat()
        observed_ms = int(time.time() * 1000)
        parsed = parse_closed_klines(raw, observed_ms, feed.symbol,
                                     feed.interval, observed_at)
        provenance = {"source_url": url, "fetched_at": observed_at,
                      "n_raw": len(raw), "n_closed": len(parsed)}
        ok, rej = [], {}
        for cnd in parsed:
            st = feed.validate(cnd)
            if st in (STATUS_OK, STATUS_WARMUP):
                ok.append(cnd)
            else:
                rej[st] = rej.get(st, 0) + 1
        manifest = build_manifest("fresh", config=config, source={"url": url},
                                  feed_state=feed,
                                  clock={"anchor": 0, "stride": config["decision_clock"]["stride_bars"],
                                         "stride_source": config["decision_clock"]["stride_source"]},
                                  provenance=provenance)
        out.mkdir(parents=True, exist_ok=False)
        (out / "fresh_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
        pd.DataFrame(ok).to_parquet(out / "fresh_closed.parquet", index=False)
        print(f"[{MODE_LABEL}] fresh ingest: {len(ok)} closed, rejects={rej} -> {out}")
        return
    if not a.signals:
        raise SystemExit("REFUSED: replay mode needs --signals (frozen signals parquet).")
    candles = pd.read_parquet(root / a.candles).sort_values("open_time").reset_index(drop=True)
    signals = pd.read_parquet(root / a.signals).sort_values("bar_index").reset_index(drop=True)
    decisions: dict[int, dict] = {}
    for row in signals.itertuples(index=False):
        decisions[int(row.bar_index)] = {
            "action": "LONG" if int(row.direction) == 1 else "SHORT",
            "confidence": 1.0, "entry_limit": float(row.entry_limit),
            "stop_loss": float(row.stop_loss), "take_profit_1": float(row.take_profit_1),
            "take_profit_2": float(row.take_profit_2),
            "holding_bars": int(row.holding_bars)}
    strategy = FeedExecStrategy(config, n_bars=len(candles))
    intents = run_replay(candles, decisions, strategy)
    manifest = build_manifest(
        "replay", config=config,
        source={"candles": str(a.candles), "signals": str(a.signals)},
        feed_state=feed,
        clock={"anchor": strategy.clock_anchor, "stride": strategy.clock_stride,
               "stride_source": config["decision_clock"]["stride_source"]})
    out.mkdir(parents=True, exist_ok=False)
    intents.to_csv(out / "intents.csv", index=False)
    pd.DataFrame(strategy.operating.events).to_csv(out / "operating_exits.csv", index=False)
    pd.DataFrame(strategy.control.events).to_csv(out / "control_exits.csv", index=False)
    (out / "replay_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    summary = {"mode": MODE_LABEL, "exploratory": True, "live_orders": False,
               "feedexec_version": "r76_feedexec/1", "run_mode": "replay",
               "config_snapshot": config, "manifest": manifest,
               "operating_equity": strategy.operating.equity,
               "control_equity": strategy.control.equity,
               "operating_exits": strategy.operating.exits,
               "control_exits": strategy.control.exits,
               "alerts": strategy.alerts}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(f"[{MODE_LABEL}] replay: {len(intents)} intents, op_eq={strategy.operating.equity:.4f}, "
          f"ctrl_eq={strategy.control.equity:.4f} -> {out}")


if __name__ == "__main__":
    main()
