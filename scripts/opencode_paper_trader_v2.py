"""Paper-trading v2: event-driven bot loop with kill-switch + divergence-trip. SIMULATED/PAPER ONLY.

EXPLORATORY (research plumbing, not a production bot). No live orders, no exchange
credentials, no network calls to exchanges. Order "intents" are logged to CSV for
plumbing tests only; nothing is executed.

What v2 adds over scripts/opencode_paper_trader.py (v1, UNCHANGED - this module
imports and reuses v1's audited ReplayPredictor/DdGuard/PaperAccount bit-for-bit):

  (1) Event-driven Strategy interface: a single ``on_bar(closed_bars_df)`` method
      used by BOTH the replay loop and the (future) live feed. PaperStrategyV2
      composes v1's ReplayPredictor + DdGuard + PaperAccount behind that one
      method. See "LIVE-FEED WIRING POINT" below.
  (2) Kill-switch: DailyLossHalt (halts NEW intents for the rest of the UTC day
      once paper-equity drawdown from day-open reaches X; X=3% pre-specified in
      configs/opencode_paper_trader_v2.json) + MaxPositionGuard (asserts the
      one-position-at-a-time invariant fail-closed).
  (3) Divergence-trip: paper equity is tracked against the FROZEN backtest equity
      curve (majority_1x normal trades:
      artifacts/research/opencode_v15_mapensemble/majority_1x/normal_trades.csv,
      stepwise forward-filled by exit_index). If |paper-expected|/expected
      exceeds Y (Y=5% pre-specified), the monitor latches a trip: all further new
      intents are blocked and an alert record is logged.
  (4) State persistence: guard/halt/trip state is dumped to JSON every bar
      (config state.persist_every_n_bars=1) so a restart can resume via
      --resume; the replay driver and the future live feed share the same
      snapshot/restore helpers.
  (5) Anti-live interlock: v1's hard interlock is kept and EXTENDED to the new
      paths (kill_switch/divergence/state/live_feed sections, extra CLI flags,
      live_feed.enabled=true is refused).

LIVE-FEED WIRING POINT (future, NOT implemented - paper module has no live path):
  The live loop, when it exists, must do exactly what run_replay() does per bar:
    1. Wait until 5m bar ``c`` is CLOSED (same guarantee as the replay slice).
    2. Append it to a frame with the SAME columns and with the DataFrame index
       continuing the global candle bar_index sequence (no reindexing).
    3. Call ``strategy.on_bar(closed_frame)`` - the SAME method the replay uses.
    4. Call ``strategy.save_state(state_path)`` (same snapshot the replay writes
       every bar) so a restart resumes with --resume semantics.
    5. Emit intents downstream as PAPER records only (mode stays SIMULATED/PAPER).
  Causality contract (enforced): predictor sees only rows <= c; any intent's
  earliest entry bar is c+1 (asserted). A live predictor replaces ReplayPredictor
  by implementing predict_proba(closed_candles_df) per the v1 Predictor protocol
  PLUS supplying signal geometry via a SignalBuilder (v1 raises NotImplementedError
  until then - the wiring point is marked LIVE_WIRING in on_bar).

Loop semantics (causal, mirrors v1 + research rules):
  - Day-open equity for DailyLossHalt is the paper equity carried into the first
    bar of each UTC day (measured BEFORE that bar settles, i.e. past-only).
  - Divergence is evaluated on post-settle realized paper equity each bar.
  - Block precedence per bar after the confidence gate: divergence latch first,
    then daily halt, then max-position (busy). Blocked signals are counted, never
    emitted.
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import bisect
import json
import os
import sys
from pathlib import Path
from typing import Protocol

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:  # allow `import opencode_paper_trader` (v1)
    sys.path.insert(0, str(_SCRIPTS_DIR))

import opencode_paper_trader as v1  # noqa: E402  (v1 stays UNMODIFIED; v2 reuses it)

MODE_LABEL = v1.MODE_LABEL
STATE_VERSION = "paper_v2_state/1"

# Extra CLI flags refused by v2 (on top of v1.LIVE_ARGV_BLOCKLIST).
EXTRA_LIVE_ARGV_BLOCKLIST = ("--live-feed", "--enable-orders", "--resume-live",
                             "--send-orders", "--live")

# Config keys that must never carry a truthy value in this paper-only module.
LIVE_CONFIG_KEY_HINTS = ("exchange", "broker", "websocket", "ws_url", "api_url",
                         "order_endpoint", "send_orders")


def assert_no_live_path_v2(config: dict) -> None:
    """Hard interlock: v1 checks PLUS the v2-only paths. Paper only, always."""
    v1.assert_no_live_path(config)
    live = config.get("live_feed", {})
    if isinstance(live, dict) and live.get("enabled", False):
        raise SystemExit("REFUSED: live_feed.enabled must stay false (paper only).")

    def _scan(node: object, path: str = "$") -> None:
        if isinstance(node, dict):
            for k, val in node.items():
                kl = str(k).lower()
                if kl == "allow_live_orders":
                    if val:
                        raise SystemExit("REFUSED: allow_live_orders must stay false (paper only).")
                elif any(hint in kl for hint in LIVE_CONFIG_KEY_HINTS) and val:
                    raise SystemExit(f"REFUSED: live-trading-looking config at {path}.{k} (paper only).")
                _scan(val, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _scan(item, f"{path}[{i}]")

    for section in ("kill_switch", "divergence", "state", "live_feed"):
        if section in config:
            _scan(config[section], f"$.{section}")
    for token in sys.argv[1:]:
        if any(token == b or token.startswith(b + "=") for b in EXTRA_LIVE_ARGV_BLOCKLIST):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token} (paper only).")


class Strategy(Protocol):
    """Event-driven strategy interface shared by replay loop AND live feed.

    Single method: ``on_bar(closed_bars_df)``. Input contract (enforced):
      - Rows are CLOSED bars only, ascending by time, DataFrame index carrying
        the global candle bar_index (continuing sequence, no reindexing).
      - Columns include at least: open_time, open, high, low, close, volume,
        close_time. Last row is the most recently closed bar.
      - Calls must be strictly increasing in bar_index (asserted).
    Returns the emitted intent dict, or None (FLAT / gated / halted / busy).
    Implementations must be pure past-only: no peeking beyond the last row, no
    exchange/network calls. See module docstring LIVE-FEED WIRING POINT.
    """

    def on_bar(self, closed_bars_df: pd.DataFrame) -> dict | None:
        ...  # pragma: no cover


class DailyLossHalt:
    """Kill-switch leg 1: halt NEW intents for the rest of the UTC day.

    Day-open equity is captured at the first bar of each UTC day BEFORE that bar
    settles (past-only carry). If (day_open - equity_now)/day_open >= X, the halt
    latches for the remainder of that day only; a new UTC day clears it.
    """

    def __init__(self, max_daily_loss_pct: float):
        if not 0.0 < float(max_daily_loss_pct) < 1.0:
            raise ValueError("max_daily_loss_pct (X) must be in (0, 1).")
        self.max_daily_loss_pct = float(max_daily_loss_pct)
        self.current_day: str | None = None
        self.day_open_equity: float | None = None
        self.halted_day: str | None = None
        self.halt_events: list[dict] = []
        self.bars_halted = 0  # bars observed while halted (incl. non-signal bars)

    def roll_day(self, day: str, equity_now: float) -> None:
        if self.current_day is None or day != self.current_day:
            self.current_day = day
            self.day_open_equity = float(equity_now)

    def evaluate(self, equity_now: float, bar_time_iso: str, bar_idx: int) -> bool:
        """True => new intents must stay blocked for the rest of today.

        Called EVERY closed bar (not only signal bars) so the halt event lands
        on the true loss bar. Signal-blocking is counted separately by the caller.
        """
        if self.current_day is None or self.day_open_equity is None:
            return False
        if self.halted_day == self.current_day:
            self.bars_halted += 1
            return True
        base = self.day_open_equity
        dd = (base - float(equity_now)) / base if base > 0 else 0.0
        if dd >= self.max_daily_loss_pct:
            self.halted_day = self.current_day
            self.halt_events.append({"day": self.current_day, "bar_idx": int(bar_idx),
                                     "bar_time": bar_time_iso, "day_open_equity": base,
                                     "equity_now": float(equity_now),
                                     "drawdown_pct": dd, "threshold_pct": self.max_daily_loss_pct,
                                     "kind": "DAILY_LOSS_HALT"})
            self.bars_halted += 1
            return True
        return False

    def snapshot(self) -> dict:
        return {"max_daily_loss_pct": self.max_daily_loss_pct, "current_day": self.current_day,
                "day_open_equity": self.day_open_equity, "halted_day": self.halted_day,
                "halt_events": self.halt_events, "bars_halted": self.bars_halted}

    def restore(self, snap: dict) -> None:
        if abs(float(snap["max_daily_loss_pct"]) - self.max_daily_loss_pct) > 1e-12:
            raise ValueError("DailyLossHalt threshold mismatch on restore (refusing).")
        self.current_day = snap["current_day"]
        self.day_open_equity = snap["day_open_equity"]
        self.halted_day = snap["halted_day"]
        self.halt_events = list(snap.get("halt_events", []))
        self.bars_halted = int(snap.get("bars_halted", snap.get("bars_blocked", 0)))


class MaxPositionGuard:
    """Kill-switch leg 2: exactly one paper position at a time, fail-closed."""

    MAX_POSITIONS = 1

    @staticmethod
    def count(account: v1.PaperAccount) -> int:
        return (1 if account.pending is not None else 0) + (1 if account.open is not None else 0)

    @classmethod
    def assert_invariant(cls, account: v1.PaperAccount) -> None:
        n = cls.count(account)
        if account.pending is not None and account.open is not None:
            raise AssertionError("MaxPositionGuard violated: pending AND open set (paper allows 1).")
        if n > cls.MAX_POSITIONS:
            raise AssertionError(f"MaxPositionGuard violated: {n} positions (paper allows 1).")

    @classmethod
    def blocks_new_intent(cls, account: v1.PaperAccount) -> bool:
        cls.assert_invariant(account)
        return cls.count(account) >= cls.MAX_POSITIONS


def load_expected_curve(trades_csv: Path, initial_equity: float) -> tuple[list[int], list[float]]:
    """Load the FROZEN backtest equity path: stepwise (exit_index -> equity_after).

    Returns (sorted_exit_indices, equities). expected_at(bar) forward-fills the
    last equity_after with exit_index <= bar, else initial_equity.
    """
    trades = pd.read_csv(trades_csv)
    if "exit_index" not in trades.columns or "equity_after" not in trades.columns:
        raise ValueError(f"expected-curve trades need exit_index/equity_after: {trades_csv}")
    ordered = trades.sort_values("exit_index")
    return ([int(i) for i in ordered["exit_index"].tolist()],
            [float(e) for e in ordered["equity_after"].tolist()])


class DivergenceMonitor:
    """Divergence-trip: latch + alert when paper strays from the frozen curve.

    Trip rule (pre-specified): abs(paper_equity - expected_equity)/expected_equity
    > tolerance_pct (Y). expected_equity is the frozen backtest path forward-filled
    by exit_index. Once tripped, ALL further new intents are blocked (latched) and
    the trip event is recorded for the alert log.
    """

    def __init__(self, exit_indices: list[int], equities: list[float],
                 tolerance_pct: float, initial_equity: float):
        if not 0.0 < float(tolerance_pct) < 1.0:
            raise ValueError("tolerance_pct (Y) must be in (0, 1).")
        self._idx = list(exit_indices)
        self._eq = list(equities)
        self.tolerance_pct = float(tolerance_pct)
        self.initial_equity = float(initial_equity)
        self.tripped = False
        self.trip_event: dict | None = None
        self.checks = 0
        self.blocks = 0
        self.max_abs_divergence = 0.0
        self.last_expected: float | None = None
        self.last_divergence: float | None = None

    def expected_at(self, bar_idx: int) -> float:
        i = bisect.bisect_right(self._idx, int(bar_idx)) - 1
        return float(self._eq[i]) if i >= 0 else self.initial_equity

    def check(self, bar_idx: int, paper_equity: float, bar_time_iso: str) -> dict | None:
        """Evaluated EVERY closed bar (not only signal bars).

        None => pass. Dict => new intents must stay blocked (status TRIPPED_NOW
        exactly once, BLOCKED_LATCHED after). The caller counts blocked signals.
        """
        expected = self.expected_at(bar_idx)
        div = (float(paper_equity) - expected) / expected if expected > 0 else 0.0
        self.checks += 1
        self.last_expected = expected
        self.last_divergence = div
        if abs(div) > self.max_abs_divergence:
            self.max_abs_divergence = abs(div)
        if self.tripped:
            return {"status": "BLOCKED_LATCHED", "bar_idx": int(bar_idx),
                    "bar_time": bar_time_iso, "paper_equity": float(paper_equity),
                    "expected_equity": expected, "divergence": div}
        if expected > 0 and abs(div) > self.tolerance_pct:
            self.tripped = True
            self.trip_event = {"kind": "DIVERGENCE_TRIP", "status": "TRIPPED_NOW",
                               "bar_idx": int(bar_idx), "bar_time": bar_time_iso,
                               "paper_equity": float(paper_equity), "expected_equity": expected,
                               "divergence": div, "tolerance_pct": self.tolerance_pct}
            return dict(self.trip_event)
        return None

    def snapshot(self) -> dict:
        return {"tolerance_pct": self.tolerance_pct, "initial_equity": self.initial_equity,
                "tripped": self.tripped, "trip_event": self.trip_event, "checks": self.checks,
                "blocks": self.blocks, "max_abs_divergence": self.max_abs_divergence,
                "n_curve_points": len(self._idx)}

    def restore(self, snap: dict) -> None:
        if abs(float(snap["tolerance_pct"]) - self.tolerance_pct) > 1e-12:
            raise ValueError("DivergenceMonitor tolerance mismatch on restore (refusing).")
        self.tripped = bool(snap["tripped"])
        self.trip_event = snap["trip_event"]
        self.checks = int(snap.get("checks", 0))
        self.blocks = int(snap.get("blocks", 0))
        self.max_abs_divergence = float(snap.get("max_abs_divergence", 0.0))


class PaperStrategyV2:
    """Event-driven paper strategy: ONE on_bar() for replay loop AND live feed.

    Composes v1's audited components unchanged (ReplayPredictor + DdGuard +
    PaperAccount) behind the Strategy interface, adding DailyLossHalt,
    MaxPositionGuard and DivergenceMonitor. See module docstring for the
    LIVE-FEED WIRING POINT: the live loop calls this same on_bar() per closed bar.
    """

    INTENT_COLUMNS = v1.PaperTrader.INTENT_COLUMNS + ["day", "expected_equity", "divergence"]

    def __init__(self, predictor: v1.Predictor, config: dict,
                 expected_curve: tuple[list[int], list[float]] | None = None,
                 alert_sink: list | None = None, n_bars: int | None = None):
        assert_no_live_path_v2(config)
        self.config = config
        self.predictor = predictor
        # Full-horizon bar count for the pending-entry expiry cap (v1 parity:
        # entry_last_bar = min(signal+expiry, N-1)). The replay driver passes
        # len(candles); the future live feed leaves None (open-ended: cap =
        # signal+expiry, which is the binding constraint away from dataset end).
        self.n_bars = n_bars
        g = config["guard"]
        c = config["costs"]
        self.guard = v1.DdGuard(g["dd_trigger"], g["guard_leverage"], g["full_leverage"],
                                config["account"]["initial_equity_indexed"])
        self.account = v1.PaperAccount(config["account"]["initial_equity_indexed"],
                                       c["fee_rate_per_fill"], c["funding_long_rate"],
                                       c["funding_short_rate"], c["funding_interval_hours"])
        ks = config["kill_switch"]
        if int(ks.get("max_positions", 1)) != 1:
            raise ValueError("kill_switch.max_positions must be 1 (paper allows one position).")
        self.daily_halt = DailyLossHalt(ks["daily_loss_halt_pct"])
        dv = config["divergence"]
        if expected_curve is None:
            root = _SCRIPTS_DIR.parent
            curve_path = Path(dv["baseline"])
            if not curve_path.is_absolute():
                curve_path = root / curve_path
            expected_curve = load_expected_curve(curve_path, config["account"]["initial_equity_indexed"])
        self.divergence = DivergenceMonitor(expected_curve[0], expected_curve[1],
                                            dv["tolerance_pct"],
                                            config["account"]["initial_equity_indexed"])
        self.min_confidence = float(config["policy_geometry"]["min_confidence"])
        self.entry_expiry = int(config["policy_geometry"]["entry_expiry_bars"])
        self.max_holding = int(config["policy_geometry"]["max_holding_bars"])
        self.alerts: list = alert_sink if alert_sink is not None else []
        self.intents: list[dict] = []
        self.bars_seen = 0
        self.signals_seen = 0
        self.skipped_low_conf = 0
        self.skipped_busy = 0
        self.skipped_daily_halt = 0
        self.skipped_divergence = 0
        self.day_closes: list[dict] = []  # UTC day-close equity trace (small, for reporting)
        self._open_day: str | None = None
        self._last_bar: int | None = None

    # -- Strategy interface -------------------------------------------------
    def on_bar(self, closed_bars_df: pd.DataFrame) -> dict | None:
        """ONE tick: last row of ``closed_bars_df`` has just CLOSED.

        Shared by the replay driver (which passes ``candles.iloc[:i+1]``) and the
        future live feed (which passes its identically-shaped growing frame).
        Returns the emitted intent dict, or None when FLAT/gated/halted/busy.
        """
        if closed_bars_df.empty:
            raise ValueError("on_bar needs at least one closed bar.")
        bar_idx = int(closed_bars_df.index[-1])
        if self._last_bar is not None and bar_idx <= self._last_bar:
            raise AssertionError("on_bar bars must be strictly increasing (replay/live bug).")
        bar = closed_bars_df.iloc[-1]
        signal_time = pd.Timestamp(bar["close_time"])
        day = pd.Timestamp(bar["open_time"]).date().isoformat()
        # Day boundary BEFORE settlement: day-open = past-only carried equity.
        if self._open_day is not None and day != self._open_day:
            self.day_closes.append({"day": self._open_day, "close_equity": self.account.equity,
                                    "close_bar": self._last_bar})
        self.daily_halt.roll_day(day, self.account.equity)
        self._open_day = day
        # Settle paper account on this closed bar first (past-only equity for guard).
        self.account.on_bar_close(bar_idx, bar, self.guard)
        self.bars_seen += 1
        self._last_bar = bar_idx
        bar_time_iso = signal_time.isoformat()
        # Risk monitors run on EVERY closed bar (even with no signal) so halt /
        # trip events land on the true bar, not on the next signal bar.
        div_status = self.divergence.check(bar_idx, self.account.equity, bar_time_iso)
        if div_status is not None and div_status.get("status") == "TRIPPED_NOW":
            self.alerts.append(div_status)
        halted_today = self.daily_halt.evaluate(self.account.equity, bar_time_iso, bar_idx)
        if halted_today:
            latest = self.daily_halt.halt_events[-1]
            if latest not in self.alerts:
                self.alerts.append(latest)
        # Predictor sees only bars <= bar_idx (all closed). Pure past-only lookup.
        pred = self.predictor.predict_proba(closed_bars_df)
        action, conf = pred["action"], float(pred["confidence"])
        if action == "FLAT" or conf < self.min_confidence:
            if action != "FLAT":
                self.skipped_low_conf += 1
            return None
        # Block precedence after the confidence gate: divergence latch, daily
        # halt, then max-position (busy). Blocked signals are counted, not emitted.
        if div_status is not None:
            self.divergence.blocks += 1
            self.skipped_divergence += 1
            return None
        if halted_today:
            self.skipped_daily_halt += 1
            return None
        if MaxPositionGuard.blocks_new_intent(self.account):
            self.skipped_busy += 1  # one paper position at a time; extras logged as skipped
            return None
        row = pred.get("_replay_row")
        if row is not None:
            direction = int(row.direction)
            entry_limit = float(row.entry_limit)
            tp = float(row.take_profit_2)
            sl = float(row.stop_loss)
            holding = min(int(row.holding_bars), self.max_holding)
        else:  # LIVE_WIRING: live predictors must supply geometry via a
            # SignalBuilder (same wiring point as v1 PaperTrader.on_bar_close).
            raise NotImplementedError("Live predictors must supply geometry via a SignalBuilder.")
        self.signals_seen += 1
        leverage, state = self.guard.multiplier(signal_time)
        size = self.account.equity * leverage
        expected = self.divergence.expected_at(bar_idx)
        base_div = ((self.account.equity - expected) / expected) if expected > 0 else 0.0
        intent = {"signal_time": bar_time_iso, "side": action,
                  "entry_limit": entry_limit, "tp": tp, "sl": sl, "size": size,
                  "guard_state": state, "signal_bar": bar_idx, "current_bar": bar_idx,
                  "entry_start_bar": bar_idx + 1, "confidence": conf,
                  "leverage": leverage, "equity_before": self.account.equity,
                  "predictor": getattr(self.predictor, "kind", type(self.predictor).__name__),
                  "mode": MODE_LABEL, "day": day,
                  "expected_equity": expected, "divergence": base_div}
        assert intent["signal_bar"] < intent["entry_start_bar"]  # causality
        MaxPositionGuard.assert_invariant(self.account)  # fail-closed before arming
        self.intents.append(intent)
        horizon_end = (self.n_bars - 1) if self.n_bars is not None else (bar_idx + self.entry_expiry)
        self.account.pending = {"signal_bar": bar_idx, "direction": direction,
                                "entry_limit": entry_limit, "take_profit_2": tp,
                                "stop_loss": sl, "holding_bars": holding,
                                "entry_start_bar": bar_idx + 1,
                                "entry_last_bar": min(bar_idx + self.entry_expiry, horizon_end),
                                "leverage": leverage, "notional": size,
                                "equity_before": self.account.equity}
        return intent

    def intents_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.intents, columns=self.INTENT_COLUMNS)

    # -- State persistence (shared by replay driver AND future live feed) ----
    def snapshot_state(self) -> dict:
        return {"version": STATE_VERSION, "mode": MODE_LABEL, "exploratory": True,
                "last_bar": self._last_bar, "bars_seen": self.bars_seen,
                "n_bars": self.n_bars,
                "open_day": self._open_day, "day_closes": self.day_closes,
                "equity": self.account.equity,
                "account": {"exits": self.account.exits, "pending": self.account.pending,
                            "open": self.account.open},
                "dd_guard": {"exits": [[t.isoformat(), e] for t, e in self.guard._exits],  # noqa: SLF001
                             "history": self.guard.history,
                             "state_changes": self.guard.state_changes,
                             "last_state": self.guard._last_state},  # noqa: SLF001
                "daily_halt": self.daily_halt.snapshot(),
                "divergence": self.divergence.snapshot(),
                "counters": {"signals_seen": self.signals_seen,
                             "skipped_low_conf": self.skipped_low_conf,
                             "skipped_busy": self.skipped_busy,
                             "skipped_daily_halt": self.skipped_daily_halt,
                             "skipped_divergence": self.skipped_divergence,
                             "intents": len(self.intents)},
                "intents": self.intents,
                "alerts": self.alerts}

    def save_state(self, path: Path | str) -> None:
        path = Path(path)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot_state(), indent=1))

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
        self.day_closes = list(snap.get("day_closes", []))
        self.account.equity = float(snap["equity"])
        self.account.exits = int(snap["account"]["exits"])
        self.account.pending = snap["account"]["pending"]
        self.account.open = snap["account"]["open"]
        gd = snap["dd_guard"]
        self.guard._exits = [(pd.Timestamp(t), float(e)) for t, e in gd["exits"]]  # noqa: SLF001
        self.guard.history = list(gd["history"])
        self.guard.state_changes = int(gd["state_changes"])
        self.guard._last_state = gd["last_state"]  # noqa: SLF001
        self.daily_halt.restore(snap["daily_halt"])
        self.divergence.restore(snap["divergence"])
        c = snap["counters"]
        self.signals_seen = int(c["signals_seen"])
        self.skipped_low_conf = int(c["skipped_low_conf"])
        self.skipped_busy = int(c["skipped_busy"])
        self.skipped_daily_halt = int(c["skipped_daily_halt"])
        self.skipped_divergence = int(c["skipped_divergence"])
        self.intents = list(snap.get("intents", []))
        self.alerts = list(snap.get("alerts", []))


def load_state_file(path: Path | str) -> dict:
    return json.loads(Path(path).read_text())


def verify_intents_v2(df: pd.DataFrame, strategy: PaperStrategyV2) -> dict:
    """v1 causality/sanity checks PLUS v2 halt/trip enforcement checks."""
    report = v1.verify_intents(df)
    if not df.empty:
        if "day" not in df.columns or "expected_equity" not in df.columns:
            raise AssertionError("v2 intent log must carry day/expected_equity/divergence.")
        for ev in strategy.daily_halt.halt_events:
            bad = df[(df["day"] == ev["day"]) & (df["signal_time"] >= ev["bar_time"])]
            if not bad.empty:
                raise AssertionError(f"intent emitted after daily halt on {ev['day']} (kill-switch bug).")
        if strategy.divergence.tripped and strategy.divergence.trip_event is not None:
            trip_bar = int(strategy.divergence.trip_event["bar_idx"])
            bad = df[df["signal_bar"] >= trip_bar]
            if not bad.empty:
                raise AssertionError("intent emitted at/after divergence trip bar (trip-latch bug).")
    report.update({"v2_halt_trip_checks": "pass",
                   "halt_days": sorted({e["day"] for e in strategy.daily_halt.halt_events}),
                   "divergence_tripped": strategy.divergence.tripped})
    return report


def run_replay(candles: pd.DataFrame, strategy: PaperStrategyV2, start: int, end: int,
               state_path: Path | str | None = None, persist_every: int = 1,
               alert_path: Path | str | None = None, verbose: bool = True) -> pd.DataFrame:
    """Replay driver: walk closed bars start..end-1 through strategy.on_bar().

    The future live feed replaces this loop body per bar (see module docstring)
    but calls the SAME on_bar() + save_state() methods.
    """
    flushed_alerts = 0
    alert_fh = None
    if alert_path is not None:
        alert_path = Path(alert_path)
        alert_path.parent.mkdir(parents=True, exist_ok=True)
        alert_fh = alert_path.open("w")
    try:
        print(f"[{MODE_LABEL}] v2 walking closed bars {start}..{end - 1} "
              f"({end - start} bars), predictor sees past-only data.", flush=True)
        for i in range(start, end):
            intent = strategy.on_bar(candles.iloc[:i + 1])
            if verbose and intent is not None:
                print(f"[{MODE_LABEL}] INTENT signal_bar={intent['signal_bar']} "
                      f"time={intent['signal_time']} side={intent['side']} "
                      f"limit={intent['entry_limit']:.2f} tp={intent['tp']:.2f} "
                      f"sl={intent['sl']:.2f} size={intent['size']:.2f} "
                      f"guard={intent['guard_state']} conf={intent['confidence']:.3f} "
                      f"div={intent['divergence']:+.3%}", flush=True)
            if state_path is not None and (i - start) % max(1, persist_every) == 0:
                strategy.save_state(state_path)
            if alert_fh is not None:
                while flushed_alerts < len(strategy.alerts):
                    alert_fh.write(json.dumps(strategy.alerts[flushed_alerts]) + "\n")
                    flushed_alerts += 1
    finally:
        if alert_fh is not None:
            alert_fh.close()
    if state_path is not None:  # final snapshot covers bars skipped by the stride
        strategy.save_state(state_path)
    return strategy.intents_df()


def main() -> None:
    for token in sys.argv[1:]:  # explicit refusal before argparse (mirrors v1)
        if any(token == b or token.startswith(b + "=")
               for b in (*v1.LIVE_ARGV_BLOCKLIST, *EXTRA_LIVE_ARGV_BLOCKLIST)):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token} (paper only).")
    ap = argparse.ArgumentParser(description="Paper-trading loop v2 (SIMULATED/PAPER ONLY).")
    ap.add_argument("--demo", action="store_true", help="walk closed candles bar-by-bar and log intents")
    ap.add_argument("--config", type=Path, default=Path("configs/opencode_paper_trader_v2.json"))
    ap.add_argument("--output", type=Path,
                    default=Path("artifacts/research/opencode_paper_v2/paper_v2_intents.csv"))
    ap.add_argument("--bars", type=int, default=None, help="window length (default: config demo.bars)")
    ap.add_argument("--start-bar", type=int, default=None, help="explicit window start")
    ap.add_argument("--end-bar", type=int, default=None, help="explicit window end (inclusive)")
    ap.add_argument("--resume", action="store_true",
                    help="reload guard/halt state from state.persist_path before walking")
    ap.add_argument("--persist-every", type=int, default=None,
                    help="override state.persist_every_n_bars")
    a = ap.parse_args()
    if not a.demo:
        ap.error("--demo is the only supported mode (paper skeleton has no live path).")
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / a.config).read_text())
    assert_no_live_path_v2(config)
    print(f"[{MODE_LABEL}] PaperTrader v2 demo. No orders, no exchange calls, no credentials.", flush=True)
    candles = pd.read_parquet(root / config["data"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals = pd.read_parquet(root / config["data"]["signals_replay_only"])
    n = len(candles)
    demo_cfg = config.get("demo", {})
    window = int(a.bars or demo_cfg.get("bars", 500))
    default_end = demo_cfg.get("end_bar", n - 1)
    end = int(a.end_bar if a.end_bar is not None else default_end)
    end = min(end, n - 1)
    if a.start_bar is not None:
        start = int(a.start_bar)
    elif "start_bar" in demo_cfg:
        start = int(demo_cfg["start_bar"])
    else:
        start = max(0, end + 1 - window)
    assert 0 <= start < end < n, f"bad window [{start}, {end}] for {n} candles"
    strategy = PaperStrategyV2(v1.ReplayPredictor(signals), config, n_bars=len(candles))
    state_path = root / config["state"]["persist_path"]
    alert_path = root / config["state"]["alert_log"]
    out = root / a.output
    summary_path = out.with_name(out.stem + "_summary.json")
    # No-overwrite guard BEFORE the walk (state file is the resume/persist
    # exception: it is rewritten every bar by design, but refuse to clobber an
    # unrelated previous run unless --resume explicitly continues it).
    for p in (out, summary_path, alert_path):
        if p.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {p}")
    if state_path.exists() and not a.resume:
        raise FileExistsError(f"Refusing to overwrite existing state (use --resume): {state_path}")
    if a.resume:
        if not state_path.exists():
            raise SystemExit(f"REFUSED: --resume asked but no state file at {state_path}.")
        strategy.restore_state(load_state_file(state_path))
        snap_bar = strategy.snapshot_state()["last_bar"]
        if snap_bar is not None and start <= snap_bar:
            print(f"[{MODE_LABEL}] resumed: state ends at bar {snap_bar}; "
                  f"continuing walk at bar {max(start, snap_bar + 1)}.", flush=True)
            start = max(start, snap_bar + 1)
    df = run_replay(candles, strategy, start, end + 1,
                    state_path=state_path,
                    persist_every=int(a.persist_every
                                      if a.persist_every is not None
                                      else config["state"].get("persist_every_n_bars", 1)),
                    alert_path=alert_path)
    report = verify_intents_v2(df, strategy)
    guard_states = [h["state"] for h in strategy.guard.history]
    report.update({"bars_walked": end + 1 - start, "window": [start, end],
                   "signals_seen": strategy.signals_seen,
                   "skipped_low_conf": strategy.skipped_low_conf,
                   "skipped_busy": strategy.skipped_busy,
                   "skipped_daily_halt": strategy.skipped_daily_halt,
                   "skipped_divergence": strategy.skipped_divergence,
                   "daily_halt_events": strategy.daily_halt.halt_events,
                   "daily_halted_bars": strategy.daily_halt.bars_halted,
                   "divergence_trip": strategy.divergence.trip_event,
                   "divergence_blocks": strategy.divergence.blocks,
                   "divergence_max_abs": strategy.divergence.max_abs_divergence,
                   "alerts": len(strategy.alerts),
                   "paper_exits": strategy.account.exits,
                   "paper_equity": round(strategy.account.equity, 4),
                   "guard_state_changes": strategy.guard.state_changes,
                   "guard_states_used": sorted(set(guard_states))})
    print(f"[{MODE_LABEL}] " + json.dumps(report, default=str), flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    summary = {"mode": MODE_LABEL, "exploratory": True, "live_orders": False,
               "bot_version": "paper_trader_v2",
               "config_snapshot": config,
               "data_range": {"start_open": pd.Timestamp(candles['open_time'].iloc[start]).isoformat(),
                              "end_close": pd.Timestamp(candles['close_time'].iloc[end]).isoformat()},
               "predictor": "ReplayPredictor (FROZEN signals, demo plumbing only)",
               "execution_assumptions": config["policy_geometry"].get("paper_exit_note", ""),
               "halt_trip_params": {"daily_loss_halt_X_pct": config["kill_switch"]["daily_loss_halt_pct"],
                                    "max_positions": config["kill_switch"]["max_positions"],
                                    "divergence_tolerance_Y_pct": config["divergence"]["tolerance_pct"],
                                    "divergence_baseline": config["divergence"]["baseline"]},
               "stats": report,
               "guard_history": strategy.guard.history,
               "day_closes": strategy.day_closes,
               "alerts": strategy.alerts}
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[{MODE_LABEL}] wrote {out} ({len(df)} intents) + {summary_path.name} "
          f"+ {Path(alert_path).name} + {Path(state_path).name}", flush=True)


if __name__ == "__main__":
    main()
