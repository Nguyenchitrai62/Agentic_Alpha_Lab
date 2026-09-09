"""Thin adapter: replay the frozen L3-combo dd_guard_tp075 signals through paper-trader v2.1.

EXPLORATORY / SIMULATED-PAPER ONLY. No live orders, no exchange code/keys/network.
Does NOT modify scripts/opencode_paper_trader_v21.py (or v2/v1) nor the frozen combo
artifacts. New code, disclosed here:

WHY AN ADAPTER IS NEEDED (interface mismatch, found at load):
  v2.1's ReplayPredictor keys signals by ``bar_index`` in a dict
  (``{int(bar): row}``), i.e. it assumes AT MOST ONE signal per 5m bar. The L3
  combo book (L1-pool union of v38-identity / v33-identity / majority legs) has
  210 signal rows on only 202 unique bars: 8 bars carry TWO opposite-direction
  signals each (bars 239328, 249408, 280512, 306720, 319968, 324576, 334080,
  381024). Fed straight into v2.1, the dict collapses 210 -> 202 rows (last row
  per bar silently wins), the same-book fingerprint check FAILS CLOSED
  (fingerprint_match=False, n_missing_trades=0) and the run refuses. That refusal
  is correct behaviour - this adapter resolves it WITHOUT touching v2.1.

WHAT THE ADAPTER DOES:
  ComboReplayPredictor implements the v1 Predictor protocol
  (``predict_proba(closed_candles_df)`` -> action/confidence) AND the v2.1
  introspection contract (``_by_bar`` mapping to per-row namedtuples) so
  ``replay_frame_from_predictor`` + ``check_signalset_identity`` see all 210
  rows and the same-book identity PASSES bit-identically against the frozen
  ``signals.parquet``. Keys are sequence ids (not bar_index), values are the
  untouched frozen rows.

  Same-bar collision rule (deterministic, disclosed): the paper loop emits at
  most ONE intent per closed bar (single-position engine). When N>1 frozen rows
  share a bar, the adapter picks exactly one: highest ``ohlc_fill_score`` wins;
  exact-score ties break by lowest ``candidate_id``, then file order. The loser
  is absorbed (counted in ``collision_absorbed`` / ``collision_picks`` for the
  report, never emitted). Confidence semantics are unchanged from v1: the
  winner's ``ohlc_fill_score`` (all 210 combo rows score >= 0.364, above the
  0.25 operating gate, so zero low-confidence skips are expected).

  Deliberately NOT carried over: the frozen per-row ``leverage`` column (the
  backtest-time dd_guard decision, incl. seven 0.5x rows). The live/paper guard
  must recompute leverage from LIVE paper equity (past-only), never trust a
  frozen leverage - v2.1 does exactly this via DdGuard.multiplier(). Any paper
  vs backtest drift from this (plus the documented full-at-TP2 simplification
  vs the combo's TP1-0.75 split, plus single-intent-per-bar on the 8 collided
  bars) is what the one-sided Y=5% UNDER-trip watches for.

DRIVER: ``main()`` mirrors ``opencode_paper_trader_v21.main()`` bar-for-bar
(same window/state/output/verify logic, same no-overwrite guards, same live-flag
refusals) but constructs ComboReplayPredictor. All strategy/guard/halt/trip
code paths are v2.1's own, unmodified.
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import opencode_paper_trader as v1  # noqa: E402  (UNMODIFIED)
import opencode_paper_trader_v2 as v2  # noqa: E402  (UNMODIFIED)
import opencode_paper_trader_v21 as v21  # noqa: E402  (UNMODIFIED)

ADAPTER_VERSION = "r27L3_combo_replay/1"


class ComboReplayPredictor:
    """Replay ALL frozen combo rows (incl. same-bar pairs) for paper ops rehearsal.

    DEMO/REPLAY ONLY - not a live model. Past-only lookup of frozen rows.
    """

    kind = "COMBO_REPLAY_ADAPTER_R27L3_DEMO_ONLY"

    def __init__(self, signals_df: pd.DataFrame):
        frame = signals_df.copy()
        for col in ("bar_index", "direction", "ohlc_fill_score"):
            if col not in frame.columns:
                raise ValueError(f"ComboReplayPredictor needs frozen signals with {col}.")
        rows = list(frame.itertuples(index=False))
        if not rows:
            raise ValueError("v2.1 paper replay requires a non-empty frozen signal frame.")
        # Sequence keys (NOT bar_index): preserves every row for the v2.1
        # identity fingerprint, including same-bar pairs v1's dict would collapse.
        self._by_bar = {i: r for i, r in enumerate(rows)}
        self._cols = list(rows[0]._fields)
        by_bar: dict[int, list] = {}
        for r in rows:
            by_bar.setdefault(int(r.bar_index), []).append(r)
        self._rows_by_bar = by_bar
        self.n_rows = len(rows)
        self.n_bars = len(by_bar)
        self.n_collided_bars = sum(1 for v in by_bar.values() if len(v) > 1)
        self.collision_picks: list[dict] = []
        self.collision_absorbed = 0

    @staticmethod
    def _pick(rows: list) -> object:
        """Deterministic same-bar pick: top ohlc_fill_score, then lowest
        candidate_id, then file order. Disclosed; recorded by the caller."""
        best = None
        best_key = None
        for seq, r in enumerate(rows):
            key = (-float(getattr(r, "ohlc_fill_score", 0.0) or 0.0),
                   int(getattr(r, "candidate_id", 0) or 0), seq)
            if best_key is None or key < best_key:
                best_key = key
                best = r
        return best

    def predict_proba(self, closed_candles_df: pd.DataFrame) -> dict:
        current_bar = int(closed_candles_df.index[-1])
        rows = self._rows_by_bar.get(current_bar)
        if not rows:
            return {"action": "FLAT", "confidence": 0.0}
        row = rows[0] if len(rows) == 1 else self._pick(rows)
        if len(rows) > 1:
            self.collision_absorbed += len(rows) - 1
            self.collision_picks.append(
                {"bar_index": current_bar,
                 "picked_candidate_id": int(row.candidate_id),
                 "picked_direction": int(row.direction),
                 "picked_score": float(row.ohlc_fill_score),
                 "absorbed": [{"candidate_id": int(r.candidate_id),
                               "direction": int(r.direction),
                               "score": float(r.ohlc_fill_score)} for r in rows
                              if r is not row]})
        direction = int(row.direction)
        action = "LONG" if direction == 1 else ("SHORT" if direction == -1 else "FLAT")
        confidence = float(getattr(row, "ohlc_fill_score", 0.0) or 0.0)
        return {"action": action, "confidence": confidence, "_replay_row": row}


def main() -> None:
    for token in sys.argv[1:]:  # same refusals as v2.1 (paper only)
        if any(token == b or token.startswith(b + "=")
               for b in (*v1.LIVE_ARGV_BLOCKLIST, *v2.EXTRA_LIVE_ARGV_BLOCKLIST,
                         *v21.EXTRA_V21_ARGV_BLOCKLIST)):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token} (paper only).")
    ap = argparse.ArgumentParser(description="Paper rehearsal of the L3 combo book (SIMULATED/PAPER ONLY).")
    ap.add_argument("--demo", action="store_true", help="walk closed candles bar-by-bar and log intents")
    ap.add_argument("--config", type=Path, default=Path("configs/opencode_v82_papercombo.json"))
    ap.add_argument("--output", type=Path,
                    default=Path("artifacts/research/opencode_paper_combo/paper_combo_intents.csv"))
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
    v21.assert_no_live_path_v21(config)
    print(f"[{v1.MODE_LABEL}] L3-combo paper rehearsal via UNMODIFIED v2.1 + thin adapter "
          f"{ADAPTER_VERSION}. No orders, no exchange calls, no credentials.", flush=True)
    candles = pd.read_parquet(root / config["data"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals = pd.read_parquet(root / config["data"]["signals_replay_only"])
    predictor = ComboReplayPredictor(signals)
    print(f"[{v1.MODE_LABEL}] adapter: {predictor.n_rows} frozen rows on {predictor.n_bars} bars "
          f"({predictor.n_collided_bars} collided bars, deterministic top-score pick).", flush=True)
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
    strategy = v21.PaperStrategyV21(predictor, config, n_bars=len(candles), root=root)
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
            print(f"[{v1.MODE_LABEL}] resumed: state ends at bar {snap_bar}; "
                  f"continuing walk at bar {max(start, snap_bar + 1)}.", flush=True)
            start = max(start, snap_bar + 1)
    df = v2.run_replay(candles, strategy, start, end + 1,
                       state_path=state_path,
                       persist_every=int(a.persist_every
                                         if a.persist_every is not None
                                         else config["state"].get("persist_every_n_bars", 1)),
                       alert_path=alert_path)
    report = v21.verify_intents_v21(df, strategy)
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
                   "guard_states_used": sorted(set(guard_states)),
                   "adapter": {"version": ADAPTER_VERSION,
                               "frozen_rows": predictor.n_rows,
                               "frozen_bars": predictor.n_bars,
                               "collided_bars": predictor.n_collided_bars,
                               "collision_absorbed": predictor.collision_absorbed,
                               "collision_picks": predictor.collision_picks}})
    print(f"[{v1.MODE_LABEL}] " + json.dumps(report, default=str), flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    summary = {"mode": v1.MODE_LABEL, "exploratory": True, "live_orders": False,
               "bot_version": "paper_trader_v21",
               "adapter": {"version": ADAPTER_VERSION, "file": "scripts/opencode_r27L3_papercombo.py",
                           "reason": "v1-ReplayPredictor assumes <=1 signal/bar; combo has 8 same-bar pairs",
                           "collision_rule": "top ohlc_fill_score wins, ties by lowest candidate_id then file order",
                           "collision_picks": predictor.collision_picks,
                           "frozen_leverage_ignored": "paper guard recomputes live from paper equity by design"},
               "label": "OPENED-INTERVAL REHEARSAL (not forward validation)",
               "config_snapshot": config,
               "data_range": {"start_open": pd.Timestamp(candles['open_time'].iloc[start]).isoformat(),
                              "end_close": pd.Timestamp(candles['close_time'].iloc[end]).isoformat()},
               "predictor": "ComboReplayPredictor (FROZEN combo signals, demo plumbing only)",
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
    print(f"[{v1.MODE_LABEL}] wrote {out} ({len(df)} intents) + {summary_path.name} "
          f"+ {Path(alert_path).name} + {Path(state_path).name}", flush=True)


if __name__ == "__main__":
    main()
