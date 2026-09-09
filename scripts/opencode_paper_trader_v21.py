"""Paper-trading v2.1: same-book baseline + one-sided divergence trip. SIMULATED/PAPER ONLY.

EXPLORATORY (research plumbing, not a production bot). No live orders, no exchange
credentials, no network calls to exchanges. Order "intents" are logged to CSV for
plumbing tests only; nothing is executed.

v2.1 subclasses scripts/opencode_paper_trader_v2.py WITHOUT modifying v1/v2 and
fixes the v2 gaps documented in round15 (paper-trader v2 demo):

  GAP-1 (v2: silent book mismatch): the v2 demo replayed v02/isotonic_4 signals
      while the divergence baseline was the majority_1x book, so the trip fired
      on book mismatch + the documented paper-vs-backtest simplification.
      FIX: the divergence baseline MUST be the frozen backtest equity of THE SAME
      signal set being replayed (parameterized ``divergence.baseline`` +
      ``divergence.baseline_signals`` in config). At load, v2.1 asserts
      signal-set identity between the replay frame and the baseline: matching
      content fingerprints AND every baseline trade's ``signal_index`` present in
      the replay ``bar_index`` set. Silent mismatch is REFUSED fail-closed; only
      an explicitly declared ``divergence.crossbook_drill`` (with reason) may run
      cross-book, loudly logged + summary-labelled as DRILL.
  GAP-2 (v2: two-sided trip): the v2 trip latched on OVERperformance (+7.5% paper
      above expected blocked 75 later signals). FIX: one-sided trip - latch ONLY
      on underperformance (paper below expected by Y; Y=5% pre-specified in
      config). Over-excursions are logged once as DIVERGENCE_OVER_INFO (with
      direction="OVER") and NEVER latch or block. Trip events carry
      direction="UNDER".
  GAP-3 (v2: no real halt-blocks-signal proof): the v2 demo recorded halt DAYS
      but skipped_daily_halt stayed 0 (no signal landed post-latch), and the trip
      caught overperformance. FIX (demo harness, same code): same-book operating
      runs per halt alternate X in {3%, 2%} (both reported) PLUS an explicit
      stale-baseline cross-book DRILL on 100% real artifacts (real v02 signals vs
      real majority baseline) where a genuine UNDER trip blocks later REAL
      signals. No synthetic candles anywhere in the demo.
  GAP-4 (v2: resume only proven on a tiny synthetic window): v2.1 snapshot adds
      the signal-set fingerprint + identity report; restore refuses fingerprint
      or horizon/threshold mismatch. tests/test_paper_trader_v21.py kills +
      resumes mid-run on the LONG Track-C replay (265311 bars) and asserts
      identical continuation.
  GAP-5 (v2 interlock): kept and EXTENDED to the new v2.1 code paths (new config
      keys baseline_signals/crossbook_drill, new CLI surface refusals).

Causality contract: unchanged from v2 (past-only, entry >= signal_bar+1).
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:  # allow `import opencode_paper_trader_v2`
    sys.path.insert(0, str(_SCRIPTS_DIR))

import opencode_paper_trader as v1  # noqa: E402  (v1 stays UNMODIFIED)
import opencode_paper_trader_v2 as v2  # noqa: E402  (v2 stays UNMODIFIED)

MODE_LABEL = v1.MODE_LABEL
STATE_VERSION = "paper_v21_state/1"

# Pre-specified divergence tolerance for the demo configs (kept from v2: Y=5%).
PRESPECIFIED_TOLERANCE_PCT = 0.05
# Pre-specified halt-threshold alternates for the demo (no other X allowed there).
PRESPECIFIED_HALT_ALTERNATES = (0.03, 0.02)

# Extra CLI flags refused by v2.1 (on top of v1 + v2 blocklists): nothing may
# bypass the identity check or enable a live path from the command line.
EXTRA_V21_ARGV_BLOCKLIST = ("--crossbook", "--force-crossbook", "--override-identity",
                            "--skip-identity-check", "--allow-live", "--force")

# Columns defining the signal-set fingerprint (bar geometry of each signal).
FINGERPRINT_COLUMNS = ["bar_index", "direction", "entry_limit",
                       "stop_loss", "take_profit_2", "holding_bars"]


def assert_no_live_path_v21(config: dict) -> None:
    """Hard interlock: v2 checks PLUS the v2.1-only paths. Paper only, always."""
    v2.assert_no_live_path_v2(config)
    dv = config.get("divergence", {})
    if isinstance(dv, dict):
        for key in ("baseline_signals", "crossbook_drill"):
            if key in dv:
                _scan_v21_value(dv[key], f"$.divergence.{key}")
        drill = dv.get("crossbook_drill")
        if drill is not None:
            if not isinstance(drill, dict) or drill.get("declared") is not True:
                raise ValueError("divergence.crossbook_drill must be a dict with "
                                 "declared=true plus a non-empty reason (or be absent).")
            if not isinstance(drill.get("reason"), str) or not drill["reason"].strip():
                raise ValueError("divergence.crossbook_drill needs a non-empty reason.")
    for token in sys.argv[1:]:
        if any(token == b or token.startswith(b + "=") for b in EXTRA_V21_ARGV_BLOCKLIST):
            raise SystemExit(f"REFUSED: flag is not supported: {token} (paper only).")


def _scan_v21_value(node: object, path: str) -> None:
    """Refuse live-trading-looking or secret-looking values under v2.1 new keys."""
    if isinstance(node, str):
        low = node.lower()
        if low.startswith(("http://", "https://", "ws://", "wss://", "ftp://")):
            raise SystemExit(f"REFUSED: network-looking value at {path} (paper only).")
        return
    if isinstance(node, dict):
        for k, val in node.items():
            kl = str(k).lower()
            if any(s in kl for s in ("secret", "api_key", "apikey", "token",
                                     "password", "private_key")):
                raise SystemExit(f"REFUSED: config looks like it holds a secret at {path}.{k}.")
            if any(h in kl for h in v2.LIVE_CONFIG_KEY_HINTS) and val:
                raise SystemExit(f"REFUSED: live-trading-looking config at {path}.{k} (paper only).")
            _scan_v21_value(val, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _scan_v21_value(item, f"{path}[{i}]")


def fingerprint_signals(df: pd.DataFrame) -> str:
    """Canonical content fingerprint of a replay signal set (deterministic)."""
    missing = [c for c in FINGERPRINT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"signal-set fingerprint needs columns {FINGERPRINT_COLUMNS}; "
                         f"missing {missing}.")
    frame = df[FINGERPRINT_COLUMNS].copy()
    frame["bar_index"] = frame["bar_index"].astype(int)
    frame["direction"] = frame["direction"].astype(int)
    frame["holding_bars"] = frame["holding_bars"].astype(int)
    frame = frame.sort_values("bar_index").reset_index(drop=True)
    rows = [f"{int(r.bar_index)}|{int(r.direction)}|{float(r.entry_limit):.6f}|"
            f"{float(r.stop_loss):.6f}|{float(r.take_profit_2):.6f}|{int(r.holding_bars)}"
            for r in frame.itertuples(index=False)]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def fingerprint_signals_file(path: Path | str) -> str:
    return fingerprint_signals(pd.read_parquet(Path(path)))


def replay_frame_from_predictor(predictor: object) -> pd.DataFrame:
    """Recover the frozen replay frame behind a ReplayPredictor (fail-closed)."""
    by_bar = getattr(predictor, "_by_bar", None)
    if not by_bar:
        raise ValueError("v2.1 paper replay requires a ReplayPredictor over FROZEN "
                         "signals (needed for the signal-set identity check).")
    rows = list(by_bar.values())
    cols = list(rows[0]._fields)
    return pd.DataFrame(rows, columns=cols)


def check_signalset_identity(replay_df: pd.DataFrame, baseline_signals_path: Path | str,
                             baseline_trades_csv: Path | str) -> dict:
    """Compare the replayed signal set against the divergence baseline's own set.

    Returns a report dict; raises only on unreadable inputs (the caller decides
    refuse-vs-drill). Identity holds iff fingerprints match AND every baseline
    trade's signal_index exists in the replay bar_index set.
    """
    baseline_signals_path = Path(baseline_signals_path)
    fp_replay = fingerprint_signals(replay_df)
    fp_baseline_file = fingerprint_signals_file(baseline_signals_path)
    trades = pd.read_csv(baseline_trades_csv)
    if "signal_index" not in trades.columns:
        raise ValueError(f"baseline trades need a signal_index column: {baseline_trades_csv}")
    replay_bars = {int(b) for b in replay_df["bar_index"].tolist()}
    trade_bars = [int(b) for b in trades["signal_index"].tolist()]
    missing = sorted(set(trade_bars) - replay_bars)
    match = (fp_replay == fp_baseline_file) and not missing
    return {"fingerprint_replay": fp_replay, "fingerprint_baseline_signals": fp_baseline_file,
            "fingerprint_match": fp_replay == fp_baseline_file,
            "baseline_signals_path": str(baseline_signals_path),
            "baseline_trades": str(baseline_trades_csv),
            "n_replay_signals": int(len(replay_df)), "n_baseline_trades": int(len(trades)),
            "baseline_trades_missing_from_replay": missing,
            "n_missing": len(missing), "identity": bool(match)}


class OneSidedDivergenceMonitor(v2.DivergenceMonitor):
    """Divergence-trip, ONE-SIDED: latch ONLY on underperformance.

    Trip rule (pre-specified, Y from config, 5% in every demo config):
        (paper_equity - expected_equity) / expected_equity < -tolerance_pct
    i.e. paper is BELOW the frozen same-book backtest path by more than Y.
    Over-excursions (>= +Y) are recorded ONCE as DIVERGENCE_OVER_INFO with
    direction="OVER" for the alert log and NEVER latch or block. Every trip
    event carries direction="UNDER". Interface-compatible with v2 (check()
    returns None / TRIPPED_NOW / BLOCKED_LATCHED) so the v2 replay driver,
    precedence order and verifier keep working unchanged.
    """

    def __init__(self, exit_indices: list[int], equities: list[float],
                 tolerance_pct: float, initial_equity: float):
        super().__init__(exit_indices, equities, tolerance_pct, initial_equity)
        self.max_over_divergence = 0.0
        self.max_under_divergence = 0.0  # most negative, as a negative number
        self.over_events: list[dict] = []
        self._pending_over: list[dict] = []

    def check(self, bar_idx: int, paper_equity: float, bar_time_iso: str) -> dict | None:
        expected = self.expected_at(bar_idx)
        div = (float(paper_equity) - expected) / expected if expected > 0 else 0.0
        self.checks += 1
        self.last_expected = expected
        self.last_divergence = div
        if abs(div) > self.max_abs_divergence:
            self.max_abs_divergence = abs(div)
        if div > self.max_over_divergence:
            self.max_over_divergence = div
        if div < self.max_under_divergence:
            self.max_under_divergence = div
        if self.tripped:
            return {"status": "BLOCKED_LATCHED", "bar_idx": int(bar_idx),
                    "bar_time": bar_time_iso, "paper_equity": float(paper_equity),
                    "expected_equity": expected, "divergence": div, "direction": "UNDER"}
        if expected > 0 and div < -self.tolerance_pct:
            self.tripped = True
            self.trip_event = {"kind": "DIVERGENCE_TRIP", "status": "TRIPPED_NOW",
                               "direction": "UNDER",
                               "bar_idx": int(bar_idx), "bar_time": bar_time_iso,
                               "paper_equity": float(paper_equity), "expected_equity": expected,
                               "divergence": div, "tolerance_pct": self.tolerance_pct}
            return dict(self.trip_event)
        if expected > 0 and div > self.tolerance_pct and not self.over_events:
            # Info only: logged once, never latches, never blocks (check keeps
            # returning None so the caller emits intents normally).
            ev = {"kind": "DIVERGENCE_OVER_INFO", "status": "INFO_ONLY",
                  "direction": "OVER",
                  "bar_idx": int(bar_idx), "bar_time": bar_time_iso,
                  "paper_equity": float(paper_equity), "expected_equity": expected,
                  "divergence": div, "tolerance_pct": self.tolerance_pct,
                  "note": "overperformance is logged, never trips (one-sided UNDER-only)."}
            self.over_events.append(ev)
            self._pending_over.append(ev)
        return None

    def drain_over_alerts(self) -> list[dict]:
        pending, self._pending_over = list(self._pending_over), []
        return pending

    def snapshot(self) -> dict:
        snap = super().snapshot()
        snap.update({"one_sided": True, "side": "UNDER_ONLY",
                     "max_over_divergence": self.max_over_divergence,
                     "max_under_divergence": self.max_under_divergence,
                     "over_events": self.over_events})
        return snap

    def restore(self, snap: dict) -> None:
        if not snap.get("one_sided", False):
            raise ValueError("OneSidedDivergenceMonitor refuses a two-sided snapshot (refusing).")
        super().restore(snap)
        self.max_over_divergence = float(snap.get("max_over_divergence", 0.0))
        self.max_under_divergence = float(snap.get("max_under_divergence", 0.0))
        self.over_events = list(snap.get("over_events", []))
        self._pending_over = []


class PaperStrategyV21(v2.PaperStrategyV2):
    """v2 strategy with same-book identity assert + one-sided trip.

    Constructor asserts signal-set identity at LOAD (fail-closed) before any bar
    is walked. New snapshot fields: signal-set fingerprint + identity report +
    drill declaration, all re-checked on restore.
    """

    INTENT_COLUMNS = v2.PaperStrategyV2.INTENT_COLUMNS

    def __init__(self, predictor: v1.Predictor, config: dict,
                 expected_curve: tuple[list[int], list[float]] | None = None,
                 alert_sink: list | None = None, n_bars: int | None = None,
                 root: Path | str | None = None):
        assert_no_live_path_v21(config)
        repo_root = Path(root) if root is not None else _SCRIPTS_DIR.parent
        dv = config["divergence"]
        if "baseline_signals" not in dv:
            raise ValueError("v2.1 requires divergence.baseline_signals (signals file "
                             "the baseline was built from).")
        baseline_trades = Path(dv["baseline"])
        if not baseline_trades.is_absolute():
            baseline_trades = repo_root / baseline_trades
        baseline_signals = Path(dv["baseline_signals"])
        if not baseline_signals.is_absolute():
            baseline_signals = repo_root / baseline_signals
        replay_df = replay_frame_from_predictor(predictor)
        identity = check_signalset_identity(replay_df, baseline_signals, baseline_trades)
        self.identity_report = identity
        drill = dv.get("crossbook_drill")
        self.is_drill = bool(drill is not None)
        if not identity["identity"] and not self.is_drill:
            raise ValueError(
                "REFUSED: signal-set mismatch between replay and divergence baseline "
                f"(fingerprint_match={identity['fingerprint_match']}, "
                f"n_missing_trades={identity['n_missing']}). Same-book baseline required; "
                "declare divergence.crossbook_drill with a reason for an explicit drill.")
        if expected_curve is None:
            expected_curve = v2.load_expected_curve(
                baseline_trades, config["account"]["initial_equity_indexed"])
        super().__init__(predictor, config, expected_curve=expected_curve,
                         alert_sink=alert_sink, n_bars=n_bars)
        # Swap the two-sided monitor for the one-sided one (fresh: no checks yet).
        self.divergence = OneSidedDivergenceMonitor(
            list(self.divergence._idx), list(self.divergence._eq),  # noqa: SLF001
            self.divergence.tolerance_pct, self.divergence.initial_equity)
        if self.is_drill:
            msg = (f"[{MODE_LABEL}] CROSSBOOK_DRILL: {drill['reason']} "
                   f"(replay_fp={identity['fingerprint_replay'][:12]}.. vs "
                   f"baseline_fp={identity['fingerprint_baseline_signals'][:12]}.., "
                   f"missing_trades={identity['n_missing']}). Exploratory drill only.")
            print(msg, flush=True)
            self.alerts.append({"kind": "CROSSBOOK_DRILL", "status": "DECLARED",
                                "reason": drill["reason"],
                                "expected_effect": drill.get("expected_effect", ""),
                                "identity": identity})

    # -- Strategy interface (v2 logic + over-info drain) ----------------------
    def on_bar(self, closed_bars_df: pd.DataFrame) -> dict | None:
        intent = super().on_bar(closed_bars_df)
        for ev in self.divergence.drain_over_alerts():
            if ev not in self.alerts:
                self.alerts.append(ev)
        return intent

    # -- State persistence (v2 fields + fingerprint/identity/over state) ------
    def snapshot_state(self) -> dict:
        snap = super().snapshot_state()
        snap["version"] = STATE_VERSION
        snap["bot_version"] = "paper_trader_v21"
        snap["signal_set_fingerprint"] = self.identity_report["fingerprint_replay"]
        snap["identity_report"] = self.identity_report
        snap["is_drill"] = self.is_drill
        return snap

    def restore_state(self, snap: dict) -> None:
        if snap.get("version") != STATE_VERSION:
            raise ValueError(f"state version mismatch: {snap.get('version')} (refusing).")
        if snap.get("mode") != MODE_LABEL:
            raise ValueError("state mode mismatch (refusing).")
        if snap.get("n_bars") != self.n_bars:
            raise ValueError("state horizon (n_bars) mismatch (refusing).")
        if snap.get("signal_set_fingerprint") != self.identity_report["fingerprint_replay"]:
            raise ValueError("signal-set fingerprint mismatch on restore (refusing).")
        if bool(snap.get("is_drill", False)) != self.is_drill:
            raise ValueError("drill/operating mismatch on restore (refusing).")
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


def verify_intents_v21(df: pd.DataFrame, strategy: PaperStrategyV21) -> dict:
    """v2 halt/trip checks PLUS v2.1 one-sided + identity checks."""
    report = v2.verify_intents_v2(df, strategy)
    if strategy.divergence.tripped:
        trip = strategy.divergence.trip_event
        assert trip is not None and trip.get("direction") == "UNDER", \
            "v2.1 trips must carry direction=UNDER (one-sided)."
        assert float(trip["divergence"]) < 0, "v2.1 trip must be underperformance."
    for ev in strategy.divergence.over_events:
        assert ev.get("direction") == "OVER" and ev.get("status") == "INFO_ONLY", \
            "over-excursions must be info-only (never latch)."
    assert strategy.identity_report["identity"] or strategy.is_drill, \
        "operating runs must carry a passing signal-set identity."
    report.update({"v21_identity": strategy.identity_report["identity"],
                   "v21_is_drill": strategy.is_drill,
                   "v21_one_sided_checks": "pass",
                   "trip_direction": (strategy.divergence.trip_event or {}).get("direction"),
                   "over_info_events": len(strategy.divergence.over_events),
                   "max_over_divergence": strategy.divergence.max_over_divergence,
                   "max_under_divergence": strategy.divergence.max_under_divergence})
    return report


def main() -> None:
    for token in sys.argv[1:]:  # explicit refusal before argparse (mirrors v1/v2)
        if any(token == b or token.startswith(b + "=")
               for b in (*v1.LIVE_ARGV_BLOCKLIST, *v2.EXTRA_LIVE_ARGV_BLOCKLIST,
                         *EXTRA_V21_ARGV_BLOCKLIST)):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token} (paper only).")
    ap = argparse.ArgumentParser(description="Paper-trading loop v2.1 (SIMULATED/PAPER ONLY).")
    ap.add_argument("--demo", action="store_true", help="walk closed candles bar-by-bar and log intents")
    ap.add_argument("--config", type=Path, default=Path("configs/opencode_paper_trader_v21.json"))
    ap.add_argument("--output", type=Path,
                    default=Path("artifacts/research/opencode_paper_v21/paper_v21_intents.csv"))
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
    assert_no_live_path_v21(config)
    print(f"[{MODE_LABEL}] PaperTrader v2.1 demo. No orders, no exchange calls, no credentials.",
          flush=True)
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
    strategy = PaperStrategyV21(v1.ReplayPredictor(signals), config, n_bars=len(candles), root=root)
    state_path = root / config["state"]["persist_path"]
    alert_path = root / config["state"]["alert_log"]
    out = root / a.output
    summary_path = out.with_name(out.stem + "_summary.json")
    for p in (out, summary_path, alert_path):
        if p.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {p}")
    if state_path.exists() and not a.resume:
        raise FileExistsError(f"Refusing to overwrite existing state (use --resume): {state_path}")
    if a.resume:
        if not state_path.exists():
            raise SystemExit(f"REFUSED: --resume asked but no state file at {state_path}.")
        strategy.restore_state(v2.load_state_file(state_path))
        snap_bar = strategy.snapshot_state()["last_bar"]
        if snap_bar is not None and start <= snap_bar:
            print(f"[{MODE_LABEL}] resumed: state ends at bar {snap_bar}; "
                  f"continuing walk at bar {max(start, snap_bar + 1)}.", flush=True)
            start = max(start, snap_bar + 1)
    df = v2.run_replay(candles, strategy, start, end + 1,
                       state_path=state_path,
                       persist_every=int(a.persist_every
                                         if a.persist_every is not None
                                         else config["state"].get("persist_every_n_bars", 1)),
                       alert_path=alert_path)
    report = verify_intents_v21(df, strategy)
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
               "bot_version": "paper_trader_v21",
               "config_snapshot": config,
               "data_range": {"start_open": pd.Timestamp(candles['open_time'].iloc[start]).isoformat(),
                              "end_close": pd.Timestamp(candles['close_time'].iloc[end]).isoformat()},
               "predictor": "ReplayPredictor (FROZEN signals, demo plumbing only)",
               "execution_assumptions": config["policy_geometry"].get("paper_exit_note", ""),
               "halt_trip_params": {"daily_loss_halt_X_pct": config["kill_switch"]["daily_loss_halt_pct"],
                                    "max_positions": config["kill_switch"]["max_positions"],
                                    "divergence_tolerance_Y_pct": config["divergence"]["tolerance_pct"],
                                    "divergence_baseline": config["divergence"]["baseline"],
                                    "divergence_baseline_signals": config["divergence"]["baseline_signals"],
                                    "one_sided": "UNDER_ONLY",
                                    "crossbook_drill": config["divergence"].get("crossbook_drill")},
               "signal_set_identity": strategy.identity_report,
               "is_drill": strategy.is_drill,
               "stats": report,
               "guard_history": strategy.guard.history,
               "day_closes": strategy.day_closes,
               "alerts": strategy.alerts}
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[{MODE_LABEL}] wrote {out} ({len(df)} intents) + {summary_path.name} "
          f"+ {Path(alert_path).name} + {Path(state_path).name}", flush=True)


if __name__ == "__main__":
    main()
