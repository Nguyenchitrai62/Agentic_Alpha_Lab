"""Paper-trading skeleton: simulates the future live bot loop. SIMULATED/PAPER ONLY.

NO live orders, NO exchange credentials, NO network calls to exchanges.
Order "intents" are logged to CSV for plumbing tests only; nothing is executed.

Loop semantics (causal, mirrors research rules):
  - At each step the current bar ``c`` has just CLOSED. The predictor sees ONLY
    bars ``<= c`` (``closed_candles_df``). Anything it emits is a signal at bar
    ``c`` whose earliest entry bar is ``c + 1`` (never sooner).
  - The dd_guard overlay matches scripts/opencode_risk_overlay_probe.py:47-61:
    leverage 0.5x while past-only realized paper equity is >10% under its
    trailing peak, else 1.0x. Guard state is updated on closed bars only, using
    paper exits strictly before the signal time.
  - Paper fills are a SIMULATED approximation reusing the fill helpers from
    src/agentic_alpha_lab/backtest/engine.py (ohlc-v2, stop-first). Documented
    simplification: the full paper position exits at TP2 (no TP1 0.5 split), no
    liquidation branch (leverage <= 1.0). Do NOT compare paper equity 1:1 with
    backtest equity.

Live-signal caveat: true live signals need v29/v33 model weights (cloud), which
are NOT available locally. This skeleton therefore ships a pluggable
``Predictor`` interface plus a clearly-marked ``ReplayPredictor`` that replays
FROZEN historical signals in time order. A real model can be dropped in later
by implementing ``predict_proba`` (see interface docstring below).
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Protocol

import pandas as pd

from agentic_alpha_lab.backtest import engine as bt_engine

MODE_LABEL = "SIMULATED/PAPER"

# Any of these set (non-empty) in the environment aborts the run. Paper only.
LIVE_ENV_BLOCKLIST = (
    "LIVE_TRADING",
    "ENABLE_LIVE",
    "ENABLE_LIVE_ORDERS",
    "LIVE_ORDERS",
    "REAL_MONEY",
    "DEPLOY_LIVE",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "EXCHANGE_API_KEY",
    "EXCHANGE_API_SECRET",
    "BROKER_API_KEY",
    "BROKER_TOKEN",
)

# Substrings that must never appear as CLI flags for this script.
LIVE_ARGV_BLOCKLIST = ("--live", "--real-money", "--deploy-live", "--send-orders")


def assert_no_live_path(config: dict) -> None:
    """Hard interlock: refuse to run if any live-trading flag/env/secret exists."""
    if config.get("allow_live_orders", False):
        raise SystemExit("REFUSED: config allow_live_orders must stay false (paper only).")
    for key in LIVE_ENV_BLOCKLIST:
        if os.environ.get(key):
            raise SystemExit(f"REFUSED: live-trading env var is set: {key} (paper only).")
    for token in sys.argv[1:]:
        if any(token == b or token.startswith(b + "=") for b in LIVE_ARGV_BLOCKLIST):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token}.")
    def _scan(node: object, path: str = "$") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                kl = str(k).lower()
                if any(s in kl for s in ("secret", "api_key", "apikey", "token", "password", "private_key")):
                    raise SystemExit(f"REFUSED: config looks like it holds a secret at {path}.{k}.")
                _scan(v, f"{path}.{k}")
    _scan(config)


class Predictor(Protocol):
    """Interface a future LIVE predictor must implement.

    Method:
        predict_proba(closed_candles_df: pd.DataFrame) -> dict with keys:
            "action": one of "LONG", "SHORT", "FLAT".
            "confidence": float in [0, 1] (calibrated probability-like score).

    Input contract (enforced by PaperTrader):
        - Rows are CLOSED bars only, sorted ascending by time, with the
          DataFrame index carrying the global candle bar_index.
        - Columns include at least: open_time, open, high, low, close, volume,
          close_time. The last row is the most recently closed bar.
    Rules for implementers:
        - Pure function of the provided frame: no peeking at bars beyond the
          last row, no mutable external state, no network/exchange calls.
        - Do NOT mutate the input frame.
        - Load weights once in __init__ (e.g. v29/v33 checkpoints when
          available); per-call work must finish well within one 5m bar.
        - Document what `confidence` means (which event, which calibration)
          and which threshold maps it to LONG/SHORT vs FLAT.
    """

    def predict_proba(self, closed_candles_df: pd.DataFrame) -> dict:
        ...  # pragma: no cover


class ReplayPredictor:
    """DEMO/REPLAY ONLY - replays FROZEN historical signals in time order.

    NOT a live model: it looks up the frozen signals.parquet row whose
    bar_index equals the just-closed bar. Used to test loop plumbing
    (causality, guard state, intent logging) until real weights land.
    """

    def __init__(self, signals_df: pd.DataFrame):
        frame = signals_df.copy()
        if "bar_index" not in frame.columns or "direction" not in frame.columns:
            raise ValueError("ReplayPredictor needs frozen signals with bar_index/direction.")
        self._by_bar = {int(r.bar_index): r for r in frame.itertuples(index=False)}
        self.kind = "REPLAY_FROZEN_SIGNALS_DEMO_ONLY"

    def predict_proba(self, closed_candles_df: pd.DataFrame) -> dict:
        current_bar = int(closed_candles_df.index[-1])
        row = self._by_bar.get(current_bar)
        if row is None:
            return {"action": "FLAT", "confidence": 0.0}
        direction = int(row.direction)
        action = "LONG" if direction == 1 else ("SHORT" if direction == -1 else "FLAT")
        confidence = float(getattr(row, "ohlc_fill_score", 0.0) or 0.0)
        return {"action": action, "confidence": confidence, "_replay_row": row}


class DdGuard:
    """Causal drawdown-guard state machine (closed bars only).

    Matches the probe: multiplier = guard_leverage while past-only realized
    equity is more than dd_trigger under its trailing peak, else full_leverage.
    Equity points come from paper exits strictly before the signal time, plus
    the initial indexed level as the seed point.
    """

    def __init__(self, dd_trigger: float, guard_leverage: float, full_leverage: float,
                 initial_equity: float):
        self.dd_trigger = float(dd_trigger)
        self.guard_leverage = float(guard_leverage)
        self.full_leverage = float(full_leverage)
        self.initial_equity = float(initial_equity)
        self._exits: list[tuple[pd.Timestamp, float]] = []  # (exit_time, equity_after), ascending
        self.history: list[dict] = []  # per-signal record for reporting
        self.state_changes = 0
        self._last_state: str | None = None

    def multiplier(self, signal_time: pd.Timestamp) -> tuple[float, str]:
        past = [(t, e) for t, e in self._exits if t < signal_time]
        if not past:
            level = peak = self.initial_equity
        else:
            level = float(past[-1][1])
            peak = max(self.initial_equity, max(e for _, e in past))
        in_guard = level / peak < 1.0 - self.dd_trigger if peak > 0 else False
        lev = self.guard_leverage if in_guard else self.full_leverage
        state = f"DD_GUARD_{lev}x" if in_guard else f"NORMAL_{lev}x"
        if self._last_state is not None and state != self._last_state:
            self.state_changes += 1
        self._last_state = state
        self.history.append({"signal_time": signal_time.isoformat(), "state": state,
                             "level": level, "peak": peak})
        return lev, state

    def record_exit(self, exit_time: pd.Timestamp, equity_after: float) -> None:
        self._exits.append((exit_time, float(equity_after)))


class PaperAccount:
    """Minimal SIMULATED paper account: one position at a time, indexed equity.

    Fill checks reuse bt_engine helpers (stop-first ordering). Simplifications
    vs engine ohlc-v2, all conservative/documented: full exit at TP2 (no TP1
    split), no liquidation branch (leverage <= 1), timeout exit at the exit
    bar's open, funding charged on closes strictly after the entry bar.
    """

    def __init__(self, initial_equity: float, fee_rate: float, funding_long_rate: float,
                 funding_short_rate: float, funding_interval_hours: int):
        self.equity = float(initial_equity)
        self.fee_rate = float(fee_rate)
        self.funding_long_rate = float(funding_long_rate)
        self.funding_short_rate = float(funding_short_rate)
        self.funding_interval_hours = int(funding_interval_hours)
        self.pending: dict | None = None  # intent awaiting entry from entry_start_bar
        self.open: dict | None = None
        self.exits = 0

    def _funding(self, bar: pd.Series, direction: int, notional: float,
                 entry_price: float, remaining: float) -> float:
        if not bt_engine._is_funding_time(pd.Timestamp(bar["open_time"]),  # noqa: SLF001 (same-repo reuse)
                                          self.funding_interval_hours):
            return 0.0
        rate = self.funding_long_rate if direction == 1 else self.funding_short_rate
        charge = notional / entry_price * float(bar["open"]) * remaining * rate
        self.equity -= charge
        return charge

    def on_bar_close(self, bar_idx: int, bar: pd.Series, guard: DdGuard) -> None:
        # Paper exits settle at this closed bar's open_time; the guard consumes
        # only exits strictly before each signal time (probe semantics).
        exit_time = pd.Timestamp(bar["open_time"])
        # 1) Seek entry for a pending intent. Causality: entry bars are always
        #    strictly after the signal bar (asserted).
        if self.pending is not None:
            p = self.pending
            assert bar_idx > p["signal_bar"], "entry sought on/before signal bar (lookahead bug)"
            if bar_idx > p["entry_last_bar"]:
                self.pending = None  # expired unfilled, like engine expiry
            else:
                fill = bt_engine._entry_fill(bar, p["direction"], p["entry_limit"])  # noqa: SLF001
                if fill is not None:
                    notional = p["equity_before"] * p["leverage"]
                    entry_fee = notional * self.fee_rate
                    self.equity -= entry_fee
                    self.open = {**p, "entry_bar": bar_idx, "entry_price": float(fill),
                                 "fees": entry_fee, "funding": 0.0, "entered_this_bar": True,
                                 "entry_open": float(bar["open"])}
                    self.pending = None
        # 2) Manage the open paper position on this closed bar.
        if self.open is None:
            return
        o = self.open
        if bar_idx > o["entry_bar"]:
            o["funding"] += self._funding(bar, o["direction"], o["notional"],
                                          o["entry_price"], 1.0)
        stop_fill = bt_engine._stop_fill(bar, o["direction"], o["stop_loss"])  # noqa: SLF001
        if stop_fill is not None:
            self._close(float(stop_fill), "stop", guard, exit_time)
            return
        # TP suppressed on the entry candle unless entered at/through the open
        # (same rule as engine ohlc-v2 lines ~291-294).
        entered_here = o.pop("entered_this_bar", False) and bar_idx == o["entry_bar"]
        entry_at_open = ((o["direction"] == 1 and o["entry_open"] <= o["entry_limit"])
                         or (o["direction"] == -1 and o["entry_open"] >= o["entry_limit"]))
        allow_tp = (not entered_here) or entry_at_open
        if allow_tp:
            tp_fill = bt_engine._take_profit_fill(bar, o["direction"], o["take_profit_2"])  # noqa: SLF001
            if tp_fill is not None:
                self._close(float(tp_fill), "tp2", guard, exit_time)
                return
        if bar_idx >= o["entry_bar"] + o["holding_bars"]:
            self._close(float(bar["open"]), "time", guard, exit_time)

    def _close(self, exit_price: float, reason: str, guard: DdGuard, exit_time: pd.Timestamp) -> None:
        o = self.open
        assert o is not None
        assert exit_time is not None, "paper exit needs its closed-bar timestamp"
        pnl = o["direction"] * (exit_price - o["entry_price"]) / o["entry_price"] * o["notional"]
        exit_fee = o["notional"] * (exit_price / o["entry_price"]) * self.fee_rate
        self.equity += pnl - exit_fee
        o["fees"] += exit_fee
        self.exits += 1
        guard.record_exit(exit_time, self.equity)
        self.open = None


class PaperTrader:
    """Simulates the future live bot loop. PAPER ONLY - never sends orders."""

    INTENT_COLUMNS = ["signal_time", "side", "entry_limit", "tp", "sl", "size",
                      "guard_state", "signal_bar", "current_bar", "entry_start_bar",
                      "confidence", "leverage", "equity_before", "predictor", "mode"]

    def __init__(self, candles: pd.DataFrame, predictor: Predictor, config: dict):
        assert_no_live_path(config)
        # Positional index of this frame IS the global bar_index: both the
        # frozen signals and this trader derive positions from the same full
        # candle file sorted by open_time. Always pass the FULL frame here;
        # ReplayPredictor maps closed.index[-1] straight to frozen bar_index.
        self.candles = candles.sort_values("open_time").reset_index(drop=True)
        self.predictor = predictor
        self.config = config
        g = config["guard"]
        c = config["costs"]
        self.guard = DdGuard(g["dd_trigger"], g["guard_leverage"], g["full_leverage"],
                             config["account"]["initial_equity_indexed"])
        self.account = PaperAccount(config["account"]["initial_equity_indexed"],
                                    c["fee_rate_per_fill"], c["funding_long_rate"],
                                    c["funding_short_rate"], c["funding_interval_hours"])
        self.min_confidence = float(config["policy_geometry"]["min_confidence"])
        self.entry_expiry = int(config["policy_geometry"]["entry_expiry_bars"])
        self.max_holding = int(config["policy_geometry"]["max_holding_bars"])
        self.intents: list[dict] = []
        self.signals_seen = 0
        self.skipped_low_conf = 0
        self.skipped_busy = 0

    def on_bar_close(self, bar_idx: int) -> dict | None:
        """One loop tick: bar `bar_idx` has just closed. Returns intent or None."""
        # Settle paper account on this closed bar first (past-only equity for guard).
        bar = self.candles.iloc[bar_idx]
        self.account.on_bar_close(bar_idx, bar, self.guard)
        # Predictor sees only bars <= bar_idx (all closed). Index preserves
        # global bar positions so replay lookup is exact.
        closed = self.candles.iloc[:bar_idx + 1]
        pred = self.predictor.predict_proba(closed)
        action, conf = pred["action"], float(pred["confidence"])
        if action == "FLAT" or conf < self.min_confidence:
            if action != "FLAT":
                self.skipped_low_conf += 1
            return None
        if self.account.pending is not None or self.account.open is not None:
            self.skipped_busy += 1  # one paper position at a time; extra signals logged as skipped
            return None
        row = pred.get("_replay_row")
        if row is not None:
            direction = int(row.direction)
            entry_limit = float(row.entry_limit)
            tp = float(row.take_profit_2)
            sl = float(row.stop_loss)
            holding = min(int(row.holding_bars), self.max_holding)
        else:  # pragma: no cover - live-predictor path wiring point
            raise NotImplementedError("Live predictors must supply geometry via a SignalBuilder (see README notes).")
        self.signals_seen += 1
        signal_time = pd.Timestamp(bar["close_time"])
        leverage, state = self.guard.multiplier(signal_time)
        size = self.account.equity * leverage
        intent = {"signal_time": signal_time.isoformat(), "side": action,
                  "entry_limit": entry_limit, "tp": tp, "sl": sl, "size": size,
                  "guard_state": state, "signal_bar": bar_idx, "current_bar": bar_idx,
                  "entry_start_bar": bar_idx + 1, "confidence": conf,
                  "leverage": leverage, "equity_before": self.account.equity,
                  "predictor": getattr(self.predictor, "kind", type(self.predictor).__name__),
                  "mode": MODE_LABEL}
        assert intent["signal_bar"] < intent["entry_start_bar"]  # causality
        self.intents.append(intent)
        self.account.pending = {"signal_bar": bar_idx, "direction": direction,
                                "entry_limit": entry_limit, "take_profit_2": tp,
                                "stop_loss": sl, "holding_bars": holding,
                                "entry_start_bar": bar_idx + 1,
                                "entry_last_bar": min(bar_idx + self.entry_expiry,
                                                      len(self.candles) - 1),
                                "leverage": leverage, "notional": size,
                                "equity_before": self.account.equity}
        return intent

    def intents_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.intents, columns=self.INTENT_COLUMNS)


def verify_intents(df: pd.DataFrame) -> dict:
    """Causality + sanity checks on the intent log. Raises on violation."""
    if df.empty:
        return {"intents": 0, "causality": "vacuous-pass (no intents emitted)"}
    assert ((df["signal_bar"] < df["entry_start_bar"]).all()
            and (df["entry_start_bar"] == df["signal_bar"] + 1).all()), \
        "intent references a non-past bar (lookahead bug)"
    assert ((df["current_bar"] == df["signal_bar"]).all()), "signal/current bar mismatch"
    assert set(df["mode"].unique()) == {MODE_LABEL}, "intent log must be labelled SIMULATED/PAPER"
    assert (df["leverage"] <= 1.0).all(), "paper leverage cap is 1.0x"
    return {"intents": int(len(df)), "causality": "pass (all signal_bar < entry_start_bar)"}


def run_demo(candles: pd.DataFrame, trader: PaperTrader, start: int, end: int,
             verbose: bool = True) -> pd.DataFrame:
    print(f"[{MODE_LABEL}] walking closed bars {start}..{end - 1} "
          f"({end - start} bars), predictor sees past-only data.", flush=True)
    for i in range(start, end):
        intent = trader.on_bar_close(i)
        if verbose and intent is not None:
            print(f"[{MODE_LABEL}] INTENT signal_bar={intent['signal_bar']} "
                  f"time={intent['signal_time']} side={intent['side']} "
                  f"limit={intent['entry_limit']:.2f} tp={intent['tp']:.2f} "
                  f"sl={intent['sl']:.2f} size={intent['size']:.2f} "
                  f"guard={intent['guard_state']} conf={intent['confidence']:.3f}",
                  flush=True)
    return trader.intents_df()


def main() -> None:
    for token in sys.argv[1:]:  # explicit refusal before argparse (which would also reject these)
        if any(token == b or token.startswith(b + "=") for b in LIVE_ARGV_BLOCKLIST):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token} (paper only).")
    ap = argparse.ArgumentParser(description="Paper-trading loop skeleton (SIMULATED/PAPER ONLY).")
    ap.add_argument("--demo", action="store_true", help="walk closed candles bar-by-bar and log intents")
    ap.add_argument("--config", type=Path, default=Path("configs/opencode_paper_trader.json"))
    ap.add_argument("--output", type=Path, default=Path("artifacts/research/opencode_paper_demo/paper_intents.csv"))
    ap.add_argument("--bars", type=int, default=None, help="window length (default: config demo.bars)")
    ap.add_argument("--start-bar", type=int, default=None, help="testing aid: explicit window start (default: last N)")
    ap.add_argument("--end-bar", type=int, default=None, help="testing aid: explicit window end (default: last close)")
    a = ap.parse_args()
    if not a.demo:
        ap.error("--demo is the only supported mode (paper skeleton has no live path).")
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / a.config).read_text())
    assert_no_live_path(config)
    print(f"[{MODE_LABEL}] PaperTrader demo. No orders, no exchange calls, no credentials.", flush=True)
    candles = pd.read_parquet(root / config["data"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals = pd.read_parquet(root / config["data"]["signals_replay_only"])
    n = len(candles)
    window = int(a.bars or config["demo"]["bars"])
    end = int(a.end_bar if a.end_bar is not None else n - 1)  # last CLOSED bar index, inclusive-safe
    end = min(end, n - 1)
    start = int(a.start_bar if a.start_bar is not None else max(0, end + 1 - window))
    assert 0 <= start < end < n, f"bad window [{start}, {end}] for {n} candles"
    trader = PaperTrader(candles, ReplayPredictor(signals), config)
    df = run_demo(candles, trader, start, end + 1)
    report = verify_intents(df)
    guard_states = [h["state"] for h in trader.guard.history]
    report.update({"bars_walked": end + 1 - start, "window": [start, end],
                   "signals_seen": trader.signals_seen,
                   "skipped_low_conf": trader.skipped_low_conf,
                   "skipped_busy": trader.skipped_busy,
                   "paper_exits": trader.account.exits,
                   "paper_equity": round(trader.account.equity, 4),
                   "guard_state_changes": trader.guard.state_changes,
                   "guard_states_used": sorted(set(guard_states))})
    print(f"[{MODE_LABEL}] " + json.dumps(report), flush=True)
    out = root / a.output
    summary_path = out.with_name(out.stem + "_summary.json")
    for p in (out, summary_path):
        if p.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {p}")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    summary = {"mode": MODE_LABEL, "live_orders": False, "config_snapshot": config,
               "data_range": {"start_open": pd.Timestamp(candles['open_time'].iloc[start]).isoformat(),
                              "end_close": pd.Timestamp(candles['close_time'].iloc[end]).isoformat()},
               "predictor": "ReplayPredictor (FROZEN signals, demo plumbing only)",
               "execution_assumptions": config["policy_geometry"].get("paper_exit_note", ""),
               "stats": report,
               "guard_history": trader.guard.history}
    out.with_name(out.stem + "_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[{MODE_LABEL}] wrote {out} ({len(df)} intents) + {summary_path.name}", flush=True)


if __name__ == "__main__":
    main()
