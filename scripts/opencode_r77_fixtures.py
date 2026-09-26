"""W2-FIXTURES: semantic execution fixtures + feed-contract tests support (R77 items 3+4).

RESEARCH ONLY. No live orders, no cloud, no training/fitting/tuning.
Frozen semantics only: ohlc-v2 engine + ohlc-stress-v1, 1x baseline.

Contents:
  - compact deterministic synthetic candle/signal builders (F1..F11)
  - hand-derived normal-scenario expectations, certified against run_backtest
  - feed-contract validator (closed-only, observed_at/decision_time split,
    STALE/DUPLICATE/OUT_OF_ORDER/INCOMPLETE/MARKET_MISMATCH, REPLAY vs FRESH)
  - restart stubs: PendingIntent (entry intent) + PartialPosition (post-TP1)
    with JSON round-trip; continue_partial_position mirrors engine rules for
    the post-checkpoint segment so streaming-vs-batch parity is checkable
  - verifier stub interface verify_parity (W3 uses the real one; this proves
    the concept and supports negative controls)
  - scenario runners: normal / fee_stress / execution_stress
  - certify_all() CLI: runs everything through the AUDITED engine and writes
    artifacts/research/opencode_r77_advisory/parity/fixtures/*.json
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from agentic_alpha_lab.backtest.engine import (
    CostModel,
    ExecutionConfig,
    _entry_fill,
    _is_funding_time,
    _stop_fill,
    _take_profit_fill,
    run_backtest,
)
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts" / "research" / "opencode_r77_advisory" / "parity" / "fixtures"

EQUITY0 = 100.0
TOL = 1e-9

# --------------------------------------------------------------------------
# Candle / signal builders
# --------------------------------------------------------------------------

def make_candles(start_iso, rows, symbol="BTCUSDT"):
    """rows: list of (open, high, low, close[, volume]). 5-minute bars."""
    start = pd.Timestamp(start_iso, tz="UTC")
    records = []
    for i, row in enumerate(rows):
        o, h, lo, c = row[0], row[1], row[2], row[3]
        v = row[4] if len(row) > 4 else 10.0
        ot = start + pd.Timedelta(minutes=5 * i)
        records.append({
            "open_time": ot,
            "close_time": ot + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
            "open": float(o), "high": float(h), "low": float(lo),
            "close": float(c), "volume": float(v),
            "symbol": symbol, "is_closed": True,
        })
    return pd.DataFrame(records).reset_index(drop=True)


def make_signals(specs):
    """specs: list of dicts with bar_index, direction, entry_limit, stop_loss,
    take_profit_1, take_profit_2, holding_bars."""
    return pd.DataFrame(specs).reset_index(drop=True)


def std_execution():
    return ExecutionConfig(entry_expiry_bars=3, max_holding_bars=12,
                           tp1_fraction=0.5, leverage=1.0, max_leverage=1.0)


def normal_costs():
    return CostModel()


def fee_stress_costs():
    return CostModel(fee_rate_per_fill=0.00055)


def exec_stress():
    return FillStress(entry_penetration_bps=5, target_penetration_bps=5,
                      market_exit_slippage_bps=5, market_exit_fee_rate=0.00055,
                      allow_limit_price_improvement=False)


# --------------------------------------------------------------------------
# Fixture builders: each returns (candles, signals, meta)
# --------------------------------------------------------------------------

BASE_START = "2026-01-05T01:00:00Z"  # Monday, far from any 8h funding boundary


def build_F1():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),      # 0 signal bar
        (100, 100.5, 99.5, 100),      # 1 entry @100 (at open)
        (100, 102, 99.8, 101),        # 2 TP1 @101 (stop 98.5 untouched)
        (101, 103.5, 100.5, 103),     # 3 TP2 @103
        (103, 103.2, 102.8, 103),
        (103, 103.1, 102.9, 103),
        (103, 103.1, 102.9, 103),
        (103, 103.1, 102.9, 103),
        (103, 103.1, 102.9, 103),
    ])
    signals = make_signals([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                             "stop_loss": 98.5, "take_profit_1": 101.0,
                             "take_profit_2": 103.0, "holding_bars": 6}])
    return candles, signals, {"id": "F1_long_tp1_tp2"}


def build_F2():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),
        (100, 100.5, 99.5, 100),      # 1 entry @100
        (100, 102, 99.8, 101),        # 2 TP1 @101
        (101, 101.5, 98.0, 99),       # 3 stop @98.5 on remainder
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
    ])
    signals = make_signals([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                             "stop_loss": 98.5, "take_profit_1": 101.0,
                             "take_profit_2": 103.0, "holding_bars": 6}])
    return candles, signals, {"id": "F2_long_tp1_stop"}


def build_F3():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),
        (100, 100.5, 99.5, 100),      # 1 short entry @100 (at open)
        (100, 100.2, 98.0, 99),       # 2 TP1 @99 (stop 101.5 untouched)
        (99, 99.2, 96.5, 97),         # 3 TP2 @97
        (97, 97.2, 96.8, 97),
        (97, 97.2, 96.8, 97),
        (97, 97.2, 96.8, 97),
        (97, 97.2, 96.8, 97),
        (97, 97.2, 96.8, 97),
    ])
    signals = make_signals([{"bar_index": 0, "direction": -1, "entry_limit": 100.0,
                             "stop_loss": 101.5, "take_profit_1": 99.0,
                             "take_profit_2": 97.0, "holding_bars": 6}])
    return candles, signals, {"id": "F3_short_tp1_tp2"}


def build_F4():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),
        (100, 100.5, 99.5, 100),      # 1 short entry @100
        (100, 100.2, 98.0, 99),       # 2 TP1 @99
        (99, 102.0, 98.5, 100),       # 3 stop @101.5 on remainder
        (100, 100.2, 99.8, 100),
        (100, 100.2, 99.8, 100),
        (100, 100.2, 99.8, 100),
        (100, 100.2, 99.8, 100),
        (100, 100.2, 99.8, 100),
    ])
    signals = make_signals([{"bar_index": 0, "direction": -1, "entry_limit": 100.0,
                             "stop_loss": 101.5, "take_profit_1": 99.0,
                             "take_profit_2": 97.0, "holding_bars": 6}])
    return candles, signals, {"id": "F4_short_tp1_stop"}


def build_F5():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),
        (100, 100.5, 99.5, 100),      # 1 entry @100
        (100, 104.0, 97.0, 99),       # 2 stop AND TP1/TP2 touched -> stop-first
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
        (99, 99.2, 98.8, 99),
    ])
    signals = make_signals([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                             "stop_loss": 98.5, "take_profit_1": 101.0,
                             "take_profit_2": 103.0, "holding_bars": 6}])
    return candles, signals, {"id": "F5_ambiguous_stop_first"}


def build_F6():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),
        # 1 entry @limit 100 (open 100.5 above limit -> NOT entry_at_open);
        # high 102 touches TP1=101 but targets are SUPPRESSED on this bar.
        (100.5, 102.0, 99.5, 100.2),
        (101.2, 101.8, 100.5, 101.5),  # 2 TP1 @max(101.2,101)=101.2
        (101.2, 103.5, 100.8, 103),    # 3 TP2 @103
        (103, 103.2, 102.8, 103),
        (103, 103.1, 102.9, 103),
        (103, 103.1, 102.9, 103),
        (103, 103.1, 102.9, 103),
        (103, 103.1, 102.9, 103),
    ])
    signals = make_signals([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                             "stop_loss": 98.5, "take_profit_1": 101.0,
                             "take_profit_2": 103.0, "holding_bars": 6}])
    return candles, signals, {"id": "F6_suppression"}


def build_F7():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),
        (100, 100.5, 99.5, 100),      # 1 entry @100
        (100, 100.6, 99.6, 100.2),
        (100.2, 100.7, 99.7, 100.3),
        (100.3, 100.8, 99.8, 100.4),
        (100.4, 100.9, 99.9, 100.5),
        (100.8, 101.0, 100.6, 100.9),  # 6 timeout exit @open 100.8
        (100.9, 101.1, 100.7, 101.0),
        (101.0, 101.2, 100.8, 101.1),
    ])
    signals = make_signals([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                             "stop_loss": 90.0, "take_profit_1": 105.0,
                             "take_profit_2": 110.0, "holding_bars": 5}])
    return candles, signals, {"id": "F7_timeout"}


FUNDING_START = "2026-01-05T07:30:00Z"  # bars: 07:30,07:35,...,08:00(idx6),...,08:20(idx9)


def build_F8():
    rows = [
        (100, 100.4, 99.6, 100),      # 0 07:30 signal
        (100, 100.5, 99.5, 100),      # 1 07:35 entry @100
        (100, 100.6, 99.6, 100.2),    # 2
        (100.2, 100.7, 99.7, 100.3),  # 3
        (100.3, 100.8, 99.8, 100.4),  # 4
        (100.4, 100.9, 99.9, 100.5),  # 5
        (100.5, 100.9, 100.1, 100.6),  # 6 08:00 FUNDING bar
        (100.6, 101.0, 100.2, 100.7),  # 7
        (100.7, 101.1, 100.3, 100.8),  # 8
        (101.0, 101.2, 100.8, 101.1),  # 9 08:20 timeout @open 101
        (101.1, 101.3, 100.9, 101.2),  # 10 filler
        (101.2, 101.4, 101.0, 101.3),  # 11 filler
    ]
    candles = make_candles(FUNDING_START, rows)
    signals = make_signals([{"bar_index": 0, "direction": 1, "entry_limit": 100.0,
                             "stop_loss": 90.0, "take_profit_1": 105.0,
                             "take_profit_2": 110.0, "holding_bars": 8}])
    return candles, signals, {"id": "F8_funding_long"}


def build_F8s():
    candles, _, _ = build_F8()
    signals = make_signals([{"bar_index": 0, "direction": -1, "entry_limit": 100.0,
                             "stop_loss": 105.0, "take_profit_1": 95.0,
                             "take_profit_2": 90.0, "holding_bars": 8}])
    return candles, signals, {"id": "F8s_funding_short"}


def build_F9():
    candles = make_candles(BASE_START, [
        (100, 100.4, 99.6, 100),
        (100, 100.5, 99.5, 100),      # limit 90 never touched
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ])
    signals = make_signals([{"bar_index": 0, "direction": 1, "entry_limit": 90.0,
                             "stop_loss": 85.0, "take_profit_1": 95.0,
                             "take_profit_2": 110.0, "holding_bars": 6}])
    return candles, signals, {"id": "F9_expiry"}


BUILDERS = {
    "F1_long_tp1_tp2": build_F1,
    "F2_long_tp1_stop": build_F2,
    "F3_short_tp1_tp2": build_F3,
    "F4_short_tp1_stop": build_F4,
    "F5_ambiguous_stop_first": build_F5,
    "F6_suppression": build_F6,
    "F7_timeout": build_F7,
    "F8_funding_long": build_F8,
    "F8s_funding_short": build_F8s,
    "F9_expiry": build_F9,
}

# Hand-derived normal-scenario expectations (fee 0.0002, equity0 100).
# Derived from engine rules BEFORE running; certify() asserts engine matches.
HAND_EXPECTED = {
    "F1_long_tp1_tp2": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                        "exit_index": 3, "exit_reason": "tp2", "gross_pnl": 2.0,
                        "fees": 0.0404, "funding": 0.0, "net_pnl": 1.9596,
                        "equity_after": 101.9596},
    "F2_long_tp1_stop": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                         "exit_index": 3, "exit_reason": "stop", "gross_pnl": -0.25,
                         "fees": 0.03995, "funding": 0.0, "net_pnl": -0.28995,
                         "equity_after": 99.71005},
    "F3_short_tp1_tp2": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                         "exit_index": 3, "exit_reason": "tp2", "gross_pnl": 2.0,
                         "fees": 0.0396, "funding": 0.0, "net_pnl": 1.9604,
                         "equity_after": 101.9604},
    "F4_short_tp1_stop": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                          "exit_index": 3, "exit_reason": "stop", "gross_pnl": -0.25,
                          "fees": 0.04005, "funding": 0.0, "net_pnl": -0.29005,
                          "equity_after": 99.70995},
    "F5_ambiguous_stop_first": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                                "exit_index": 2, "exit_reason": "stop", "gross_pnl": -1.5,
                                "fees": 0.0397, "funding": 0.0, "net_pnl": -1.5397,
                                "equity_after": 98.4603},
    "F6_suppression": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                       "exit_index": 3, "exit_reason": "tp2", "gross_pnl": 2.1,
                       "fees": 0.04042, "funding": 0.0, "net_pnl": 2.05958,
                       "equity_after": 102.05958,
                       "naive_no_suppression_gross": 2.0},
    "F7_timeout": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                   "exit_index": 6, "exit_reason": "time", "gross_pnl": 0.8,
                   "fees": 0.04016, "funding": 0.0, "net_pnl": 0.75984,
                   "equity_after": 100.75984},
    "F8_funding_long": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                        "exit_index": 9, "exit_reason": "time", "gross_pnl": 1.0,
                        "fees": 0.0402, "funding": 0.01005, "net_pnl": 0.94975,
                        "equity_after": 100.94975},
    "F8s_funding_short": {"trades": 1, "entry_index": 1, "entry_price": 100.0,
                          "exit_index": 9, "exit_reason": "time", "gross_pnl": -1.0,
                          "fees": 0.0402, "funding": 0.0, "net_pnl": -1.0402,
                          "equity_after": 98.9598},
    "F9_expiry": {"trades": 0, "rejected": 1, "equity_after": 100.0},
}

# --------------------------------------------------------------------------
# Feed-contract validator (contract tests only; W1 owns the runner feed)
# --------------------------------------------------------------------------

def _as_utc(value):
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def ingest_feed(records, expected_market="BTCUSDT", manifest_kind="FRESH",
                watermark_close=None, seen_open_times=None):
    """Validate an arrival-ordered batch of candle records.

    Returns (accepted_df, rejections). Each rejection is a dict with a
    distinct code. FRESH manifests require observed_at on every record;
    REPLAY manifests must not be mistaken for fresh observations.
    """
    if manifest_kind not in ("FRESH", "REPLAY"):
        raise ValueError("manifest_kind must be FRESH or REPLAY")
    seen = set(seen_open_times or set())
    max_open = None
    accepted, rejections = [], []
    for rec in records:
        ot = _as_utc(rec.get("open_time"))
        ct = _as_utc(rec.get("close_time"))
        if rec.get("symbol") != expected_market:
            rejections.append({"code": "MARKET_MISMATCH", "open_time": str(ot)})
            continue
        if (not rec.get("is_closed")) or ot is None or ct is None or not (ct > ot):
            rejections.append({"code": "INCOMPLETE", "open_time": str(ot)})
            continue
        if manifest_kind == "FRESH" and rec.get("observed_at") is None:
            rejections.append({"code": "INCOMPLETE", "open_time": str(ot),
                               "detail": "fresh record without observed_at"})
            continue
        if ot in seen:
            rejections.append({"code": "DUPLICATE", "open_time": str(ot)})
            continue
        if watermark_close is not None and ct <= _as_utc(watermark_close):
            rejections.append({"code": "STALE", "open_time": str(ot)})
            continue
        if max_open is not None and ot < max_open:
            rejections.append({"code": "OUT_OF_ORDER", "open_time": str(ot)})
            continue
        accepted.append(rec)
        seen.add(ot)
        max_open = ot if max_open is None else max(max_open, ot)
    frame = pd.DataFrame(accepted).reset_index(drop=True) if accepted else pd.DataFrame()
    return frame, rejections


def make_manifest(kind, candles, source="synthetic-fixture", observed_at=None):
    """Manifest distinguishing REPLAY (historical, diagnostic) from FRESH
    (observed now, actionable) consumption of the same bytes."""
    if kind not in ("FRESH", "REPLAY"):
        raise ValueError("kind must be FRESH or REPLAY")
    body = {
        "kind": kind,
        "is_replay": kind == "REPLAY",
        "source": source,
        "market": "BTCUSDT",
        "n_candles": int(len(candles)),
        "range": [pd.Timestamp(candles["open_time"].iloc[0]).isoformat(),
                  pd.Timestamp(candles["open_time"].iloc[-1]).isoformat()] if len(candles) else [],
    }
    if kind == "FRESH":
        if observed_at is None:
            raise ValueError("FRESH manifest requires observed_at")
        body["observed_at"] = observed_at
    return body

# --------------------------------------------------------------------------
# Restart stubs: PendingIntent + PartialPosition
# --------------------------------------------------------------------------

@dataclass
class PendingIntent:
    signal_index: int
    direction: int
    entry_limit: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    holding_bars: int
    expiry_deadline_bar: int
    policy_id: str = "frozen-reference"
    stream_hash: str = "fixture"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def is_live(self, current_bar):
        return int(current_bar) <= int(self.expiry_deadline_bar)


def fill_pending_entry(candles, intent):
    """Streaming-side entry search over bars signal+1..deadline (engine fill rule)."""
    if not intent.is_live(intent.signal_index + 1):
        return None, "EXPIRED"
    for index in range(intent.signal_index + 1, intent.expiry_deadline_bar + 1):
        if index >= len(candles):
            break
        fill = _entry_fill(candles.iloc[index], intent.direction, intent.entry_limit)
        if fill is not None:
            return (index, float(fill)), "FILLED"
    return None, "EXPIRED"


@dataclass
class PartialPosition:
    entry_index: int
    entry_time_iso: str
    entry_price: float
    direction: int
    notional: float
    remaining: float
    tp1_done: bool
    holding_bars: int
    equity_at_checkpoint: float
    gross_so_far: float
    fees_so_far: float
    funding_so_far: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    exec_identity: str = "ohlc-v2,tp1f=0.5,fee=0.0002"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def continue_partial_position(candles, partial, costs, execution, start_bar):
    """Continue a post-checkpoint partial position with verbatim engine rules.

    Mirrors run_backtest lines for stop-first, TP1 skip when done, TP2,
    funding, and timeout-at-open. Returns a dict comparable to Trade fields.
    """
    direction = partial.direction
    entry_price = partial.entry_price
    notional = partial.notional
    remaining = partial.remaining
    tp1_done = partial.tp1_done
    equity = partial.equity_at_checkpoint
    gross = partial.gross_so_far
    fees = partial.fees_so_far
    funding = partial.funding_so_far
    exit_index = partial.entry_index + partial.holding_bars
    exit_reason = "time"

    for index in range(start_bar, exit_index):
        bar = candles.iloc[index]
        bar_time = pd.Timestamp(bar["open_time"])
        if index > partial.entry_index and _is_funding_time(bar_time, costs.funding_interval_hours):
            rate = costs.funding_long_rate if direction == 1 else costs.funding_short_rate
            charge = notional / entry_price * float(bar["open"]) * remaining * rate
            funding += charge
            equity -= charge
        stop_fill = _stop_fill(bar, direction, partial.stop_loss)
        if stop_fill is not None:
            pnl = direction * (stop_fill - entry_price) / entry_price * notional * remaining
            exit_fee = notional * remaining * (stop_fill / entry_price) * costs.fee_rate_per_fill
            gross += pnl
            fees += exit_fee
            equity += pnl - exit_fee
            remaining = 0.0
            exit_reason = "stop"
            exit_index = index
            break
        # entry_at_open is only meaningful on the entry bar, which precedes
        # any post-checkpoint bar; targets are therefore always allowed here.
        allow_targets = True
        if not tp1_done and allow_targets:
            tp1_fill = _take_profit_fill(bar, direction, partial.take_profit_1)
            if tp1_fill is not None:
                pnl = direction * (tp1_fill - entry_price) / entry_price * notional * execution.tp1_fraction
                exit_fee = notional * execution.tp1_fraction * (tp1_fill / entry_price) * costs.fee_rate_per_fill
                gross += pnl
                fees += exit_fee
                equity += pnl - exit_fee
                remaining -= execution.tp1_fraction
                tp1_done = True
        tp2_fill = _take_profit_fill(bar, direction, partial.take_profit_2)
        if remaining > 0 and tp2_fill is not None:
            pnl = direction * (tp2_fill - entry_price) / entry_price * notional * remaining
            exit_fee = notional * remaining * (tp2_fill / entry_price) * costs.fee_rate_per_fill
            gross += pnl
            fees += exit_fee
            equity += pnl - exit_fee
            remaining = 0.0
            exit_reason = "tp2"
            exit_index = index
            break
    if remaining > 0:
        bar = candles.iloc[exit_index]
        bar_time = pd.Timestamp(bar["open_time"])
        if _is_funding_time(bar_time, costs.funding_interval_hours):
            rate = costs.funding_long_rate if direction == 1 else costs.funding_short_rate
            charge = notional / entry_price * float(bar["open"]) * remaining * rate
            funding += charge
            equity -= charge
        final_exit_price = float(bar["open"])
        pnl = direction * (final_exit_price - entry_price) / entry_price * notional * remaining
        exit_fee = notional * remaining * (final_exit_price / entry_price) * costs.fee_rate_per_fill
        gross += pnl
        fees += exit_fee
        equity += pnl - exit_fee
        exit_reason = "time_after_tp1" if tp1_done else "time"
        remaining = 0.0
    return {"exit_index": exit_index, "exit_reason": exit_reason, "gross_pnl": gross,
            "fees": fees, "funding": funding, "equity_after": equity,
            "remaining": remaining, "tp1_done": tp1_done}


# --------------------------------------------------------------------------
# Verifier stub interface (W3 uses the real verifier; this proves the concept)
# --------------------------------------------------------------------------

@dataclass
class Verdict:
    pass_: bool
    reasons: list
    compared: dict


VERIFY_FIELDS = ("entry_index", "entry_price", "exit_index", "exit_reason",
                 "remaining", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_after", "entry_time", "exit_time", "account")


def trade_record(trade, remaining=0.0, account="operating"):
    return {"entry_index": trade.entry_index, "entry_price": trade.entry_price,
            "exit_index": trade.exit_index, "exit_reason": trade.exit_reason,
            "remaining": remaining, "gross_pnl": trade.gross_pnl, "fees": trade.fees,
            "funding": trade.funding, "net_pnl": trade.net_pnl,
            "equity_after": trade.equity_after, "entry_time": trade.entry_time,
            "exit_time": trade.exit_time, "account": account}


def verify_parity(expected, actual, tol=TOL):
    """Field-by-field parity check. Any mismatch -> FAIL with named reasons."""
    reasons, compared = [], {}
    for field in VERIFY_FIELDS:
        exp, act = expected.get(field), actual.get(field)
        if isinstance(exp, float) or isinstance(act, float):
            ok = exp is not None and act is not None and abs(float(exp) - float(act)) <= tol
        else:
            ok = exp == act
        compared[field] = {"expected": exp, "actual": act, "match": bool(ok)}
        if not ok:
            reasons.append(f"MISMATCH:{field} expected={exp} actual={act}")
    return Verdict(pass_=not reasons, reasons=reasons, compared=compared)


# --------------------------------------------------------------------------
# Scenario runners + certification
# --------------------------------------------------------------------------

def run_scenarios(candles, signals, execution=None):
    execution = execution or std_execution()
    out = {}
    res, trades = run_backtest(candles, signals, EQUITY0, normal_costs(), execution)
    out["normal"] = {"result": asdict(res),
                     "trades": [asdict(t) for t in trades]}
    res_f, trades_f = run_backtest(candles, signals, EQUITY0, fee_stress_costs(), execution)
    out["fee_stress"] = {"result": asdict(res_f),
                         "trades": [asdict(t) for t in trades_f]}
    res_s, trades_s, diag = run_stress(candles, signals, EQUITY0, normal_costs(),
                                       execution, exec_stress())
    out["execution_stress"] = {"result": asdict(res_s),
                               "trades": [asdict(t) for t in trades_s],
                               "diagnostics": diag}
    return out


def certify_fixture(fid):
    """Run the audited engine on fixture fid; compare vs hand derivation."""
    candles, signals, meta = BUILDERS[fid]()
    execution = std_execution()
    result, trades = run_backtest(candles, signals, EQUITY0, normal_costs(), execution)
    hand = HAND_EXPECTED[fid]
    mismatches = []
    if hand.get("trades", 1) == 0:
        for key in ("rejected",):
            pass
        actual = {"trades": result.trades,
                  "rejected": result.rejected_or_unfilled_signals,
                  "equity_after": result.final_equity}
        for key in ("trades", "rejected", "equity_after"):
            exp, act = hand[{"trades": "trades", "rejected": "rejected",
                             "equity_after": "equity_after"}[key]], actual[key]
            if isinstance(exp, float):
                ok = abs(exp - act) <= TOL
            else:
                ok = exp == act
            if not ok:
                mismatches.append(f"{key}: hand={exp} engine={act}")
    else:
        trade = trades[0]
        actual = {"trades": result.trades, "entry_index": trade.entry_index,
                  "entry_price": trade.entry_price, "exit_index": trade.exit_index,
                  "exit_reason": trade.exit_reason, "gross_pnl": trade.gross_pnl,
                  "fees": trade.fees, "funding": trade.funding,
                  "net_pnl": trade.net_pnl, "equity_after": trade.equity_after,
                  "entry_time": trade.entry_time, "exit_time": trade.exit_time}
        for key, exp in hand.items():
            if key.startswith("naive_"):
                continue
            act = actual[key]
            ok = abs(float(exp) - float(act)) <= TOL if isinstance(exp, float) else exp == act
            if not ok:
                mismatches.append(f"{key}: hand={exp} engine={act}")
    scenarios = run_scenarios(candles, signals, execution)
    return {"fixture": fid, "hand": hand,
            "engine": actual,
            "mismatches": mismatches,
            "certified": not mismatches,
            "scenarios": {k: v["result"] for k, v in scenarios.items()}}


def certify_all(write=True):
    records = [certify_fixture(fid) for fid in BUILDERS]
    # F10/F11 share the F1 frame; certified via dedicated restart checks.
    f10 = check_pending_restart()
    f11 = check_partial_restart()
    records.extend([f10, f11])
    payload = {"engine": "ohlc-v2", "equity0": EQUITY0, "tol": TOL,
               "fixtures": records,
               "unsupported": ["liquidation path (1x fixtures; no liq model in stress)",
                               "true intrabar/mark-price drawdown (close-sampled only)",
                               "maker queue-position claims from OHLC"],
               "global_pass": False,
               "global_pass_reason": "WITHHELD: unsupported scenarios above unimplemented."}
    if write:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / "certified_expectations.json").write_text(json.dumps(payload, indent=2, default=str))
    return payload


def check_pending_restart():
    candles, signals, _ = build_F1()
    row = signals.iloc[0]
    intent = PendingIntent(signal_index=int(row["bar_index"]), direction=int(row["direction"]),
                           entry_limit=float(row["entry_limit"]), stop_loss=float(row["stop_loss"]),
                           take_profit_1=float(row["take_profit_1"]),
                           take_profit_2=float(row["take_profit_2"]),
                           holding_bars=int(row["holding_bars"]),
                           expiry_deadline_bar=int(row["bar_index"]) + 3)
    restored = PendingIntent.from_dict(json.loads(json.dumps(intent.to_dict())))
    assert restored == intent, "pending intent JSON round-trip must be lossless"
    (found, status) = fill_pending_entry(candles, restored)
    result, trades = run_backtest(candles, signals, EQUITY0, normal_costs(), std_execution())
    engine_entry = (trades[0].entry_index, trades[0].entry_price)
    match = found is not None and found[0] == engine_entry[0] and abs(found[1] - engine_entry[1]) <= TOL
    stale = PendingIntent(**{**intent.to_dict(), "expiry_deadline_bar": 0})
    _, stale_status = fill_pending_entry(candles, stale)
    return {"fixture": "F10_pending_restart", "status": status,
            "resumed_entry": list(found) if found else None,
            "engine_entry": list(engine_entry),
            "match": bool(match), "stale_status": stale_status,
            "certified": bool(match) and stale_status == "EXPIRED", "mismatches": []}


def check_partial_restart():
    candles, signals, _ = build_F1()
    result, trades = run_backtest(candles, signals, EQUITY0, normal_costs(), std_execution())
    engine_trade = trades[0]
    # Hand checkpoint just after the TP1 bar (index 2): half exited @101.
    partial = PartialPosition(
        entry_index=1, entry_time_iso=pd.Timestamp(candles["open_time"].iloc[1]).isoformat(),
        entry_price=100.0, direction=1, notional=100.0, remaining=0.5, tp1_done=True,
        holding_bars=6, equity_at_checkpoint=100.0 - 0.02 + 0.5 - 0.0101,
        gross_so_far=0.5, fees_so_far=0.0301, funding_so_far=0.0,
        stop_loss=98.5, take_profit_1=101.0, take_profit_2=103.0)
    restored = PartialPosition.from_dict(json.loads(json.dumps(partial.to_dict())))
    assert restored == partial, "partial position JSON round-trip must be lossless"
    resumed = continue_partial_position(candles, restored, normal_costs(), std_execution(), start_bar=3)
    mismatches = []
    for key, exp in (("exit_index", engine_trade.exit_index), ("exit_reason", engine_trade.exit_reason),
                     ("gross_pnl", engine_trade.gross_pnl), ("fees", engine_trade.fees),
                     ("funding", engine_trade.funding),
                     ("equity_after", engine_trade.equity_after)):
        act = resumed[key]
        ok = abs(float(exp) - float(act)) <= TOL if isinstance(exp, float) else exp == act
        if not ok:
            mismatches.append(f"{key}: resumed={act} engine={exp}")
    net = resumed["equity_after"] - EQUITY0
    if abs(net - engine_trade.net_pnl) > TOL:
        mismatches.append(f"net_pnl: resumed={net} engine={engine_trade.net_pnl}")
    return {"fixture": "F11_partial_restart", "resumed": resumed,
            "engine": {"exit_index": engine_trade.exit_index, "exit_reason": engine_trade.exit_reason,
                       "gross_pnl": engine_trade.gross_pnl, "fees": engine_trade.fees,
                       "funding": engine_trade.funding, "net_pnl": engine_trade.net_pnl,
                       "equity_after": engine_trade.equity_after},
            "mismatches": mismatches, "certified": not mismatches}


def main():
    parser = argparse.ArgumentParser(description="Certify R77 execution fixtures via the audited engine")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    payload = certify_all(write=not args.no_write)
    n_ok = sum(1 for r in payload["fixtures"] if r.get("certified"))
    print(f"certified {n_ok}/{len(payload['fixtures'])} fixtures")
    for r in payload["fixtures"]:
        if not r.get("certified"):
            print("MISMATCH", r["fixture"], r.get("mismatches"))
    if args.no_write:
        print(json.dumps({r["fixture"]: r.get("certified") for r in payload["fixtures"]}, indent=2))


if __name__ == "__main__":
    main()
