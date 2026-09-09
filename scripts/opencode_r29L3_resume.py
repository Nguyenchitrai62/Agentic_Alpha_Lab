"""Resume-from-state on the L3-combo book (gap #2 from the papercombo report).

EXPLORATORY / SIMULATED-PAPER ONLY. No live orders, no exchange code/keys/network,
no registry writes, no commit/push. New driver only; v2.1/v2/v1 + adapter
scripts/opencode_r27L3_papercombo.py are reused UNMODIFIED.

WHAT THIS DOES (pre-specified in configs/opencode_v89_resume.json BEFORE running):
  window [148600, 443000] (294401 bars, identical to configs/opencode_v82_papercombo.json)
  kill_bar = 295800 = (148600 + 443000) // 2 (halfway, pre-specified).
  Phase REF : uninterrupted [start, end] -> reference/...
  Phase KILL: [start, kill_bar] -> kill_part/... (simulated KILL: object dropped after final save_state)
  Phase RESU: FRESH strategy + FRESH predictor, restore kill snapshot file into the NEW
              resumed state dir, continue [kill_bar+1, end] -> resumed/...
  Then assert bit-identical continuation: resumed-full vs reference on
  intents / equity / exits / counters / halts / alerts (+ guard/day_closes/divergence).

WHY A DRIVER (not the adapter CLI): the adapter CLI walks one window per process.
This driver reuses its ComboReplayPredictor + v2.1 strategy/verify/run_replay
bar-for-bar, with the kill boundary enforced by the window split + snapshot file.

STATE NOTES (disclosed):
  - v21 snapshot covers equity/pending/open/guard/halt/divergence/counters/intents/
    alerts/day_closes (past-only). Predictor collision log counters (absorbed/picks)
    are NOT in the snapshot by design; the pick rule itself is stateless +
    deterministic (top ohlc_fill_score, then lowest candidate_id, then file order),
    so intents are unaffected. Final adapter totals compare as kill+resumed vs ref.
  - persist_every=1000 is IO stride only (final save_state covers the remainder, so
    the kill snapshot ends EXACTLY at kill_bar regardless of stride).
  - "Fresh process-equivalent" = new strategy + new predictor objects, no shared
    mutable state except the kill snapshot file (same pattern as
    tests/test_paper_trader_v21.py::test_resume_long_trackc_replay_identical).
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import hashlib
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
from opencode_r27L3_papercombo import ComboReplayPredictor, ADAPTER_VERSION  # noqa: E402  (UNMODIFIED)

DRIVER_VERSION = "r29L3_resume/1"


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _refuse_live_tokens() -> None:
    for token in sys.argv[1:]:
        if any(token == b or token.startswith(b + "=")
               for b in (*v1.LIVE_ARGV_BLOCKLIST, *v2.EXTRA_LIVE_ARGV_BLOCKLIST,
                         *v21.EXTRA_V21_ARGV_BLOCKLIST)):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token} (paper only).")


def _run_window(candles: pd.DataFrame, signals_df: pd.DataFrame, config: dict,
                start: int, end_incl: int, state_path: Path, alert_path: Path,
                out_csv: Path, persist_every: int, resume_from: Path | None,
                expect_resume_bar: int | None, label: str):
    """Walk [start, end_incl] through a FRESH combo strategy. Returns (strategy, df, report, predictor)."""
    for p in (out_csv, out_csv.with_name(out_csv.stem + "_summary.json"), alert_path):
        if p.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {p}")
    if state_path.exists() and resume_from is None:
        raise FileExistsError(f"Refusing to overwrite existing state (use resume): {state_path}")
    if resume_from is not None and not resume_from.exists():
        raise SystemExit(f"REFUSED: resume source missing: {resume_from}")
    predictor = ComboReplayPredictor(signals_df)
    strategy = v21.PaperStrategyV21(predictor, config, n_bars=len(candles),
                                    root=Path(__file__).resolve().parents[1])
    walk_start = start
    if resume_from is not None:
        snap = v2.load_state_file(resume_from)
        strategy.restore_state(snap)
        snap_bar = strategy.snapshot_state()["last_bar"]
        if expect_resume_bar is not None and int(snap_bar) != int(expect_resume_bar):
            raise AssertionError(f"kill snapshot ends at {snap_bar}, expected {expect_resume_bar}.")
        if snap_bar is not None and walk_start <= int(snap_bar):
            walk_start = int(snap_bar) + 1
        print(f"[{v1.MODE_LABEL}] {label}: resumed from {resume_from} (ends {snap_bar}); "
              f"continuing at {walk_start}.", flush=True)
    else:
        print(f"[{v1.MODE_LABEL}] {label}: fresh walk [{walk_start}, {end_incl}].", flush=True)
    if walk_start != start:
        # Only the resume phase may shift the walk start (to kill_bar+1).
        if resume_from is None or walk_start != int(expect_resume_bar) + 1:
            raise AssertionError(f"unexpected walk start {walk_start} (asked {start}).")
    df = v2.run_replay(candles, strategy, walk_start, end_incl + 1,
                       state_path=state_path, persist_every=persist_every,
                       alert_path=alert_path)
    report = v21.verify_intents_v21(df, strategy)
    guard_states = [h["state"] for h in strategy.guard.history]
    report.update({"bars_walked": end_incl + 1 - walk_start, "window": [walk_start, end_incl],
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
                   "paper_equity_full": float(strategy.account.equity),
                   "guard_state_changes": strategy.guard.state_changes,
                   "guard_states_used": sorted(set(guard_states)),
                   "adapter": {"version": ADAPTER_VERSION,
                               "frozen_rows": predictor.n_rows,
                               "frozen_bars": predictor.n_bars,
                               "collided_bars": predictor.n_collided_bars,
                               "collision_absorbed": predictor.collision_absorbed,
                               "collision_picks": predictor.collision_picks}})
    print(f"[{v1.MODE_LABEL}] {label}: " + json.dumps(
        {k: report[k] for k in ("bars_walked", "window", "signals_seen", "skipped_busy",
                                "paper_exits", "paper_equity", "alerts",
                                "divergence_trip", "divergence_blocks")}, default=str), flush=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    summary = {"mode": v1.MODE_LABEL, "exploratory": True, "live_orders": False,
               "bot_version": "paper_trader_v21", "driver": DRIVER_VERSION,
               "driver_file": "scripts/opencode_r29L3_resume.py",
               "adapter": {"version": ADAPTER_VERSION, "file": "scripts/opencode_r27L3_papercombo.py",
                           "reason": "v1-ReplayPredictor assumes <=1 signal/bar; combo has 8 same-bar pairs",
                           "collision_rule": "top ohlc_fill_score wins, ties by lowest candidate_id then file order",
                           "collision_picks": predictor.collision_picks,
                           "frozen_leverage_ignored": "paper guard recomputes live from paper equity by design"},
               "label": "OPENED-INTERVAL REHEARSAL (not forward validation)",
               "phase": label,
               "config_snapshot": config,
               "data_range": {"start_open": pd.Timestamp(candles["open_time"].iloc[walk_start]).isoformat(),
                              "end_close": pd.Timestamp(candles["close_time"].iloc[end_incl]).isoformat()},
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
    (out_csv.with_name(out_csv.stem + "_summary.json")).write_text(json.dumps(summary, indent=2, default=str))
    print(f"[{v1.MODE_LABEL}] {label}: wrote {out_csv} ({len(df)} intents).", flush=True)
    return strategy, df, report, predictor


def main() -> None:
    _refuse_live_tokens()
    ap = argparse.ArgumentParser(description="Resume-from-state rehearsal on the L3-combo book (PAPER ONLY).")
    ap.add_argument("--demo", action="store_true", help="run the pre-specified resume rehearsal")
    ap.add_argument("--config", type=Path, default=Path("configs/opencode_v89_resume.json"))
    ap.add_argument("--persist-every", type=int, default=None)
    a = ap.parse_args()
    if not a.demo:
        ap.error("--demo is the only supported mode (paper skeleton has no live path).")
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / a.config).read_text())
    v21.assert_no_live_path_v21(config)
    print(f"[{v1.MODE_LABEL}] L3-combo resume rehearsal via UNMODIFIED v2.1 + adapter "
          f"{ADAPTER_VERSION} + driver {DRIVER_VERSION}. No orders, no exchange calls.", flush=True)

    demo = config.get("demo", {})
    rt = config.get("resume_test", {})
    start, end = int(demo["start_bar"]), int(demo["end_bar"])
    kill_bar = int(rt["kill_bar"])
    assert kill_bar == (start + end) // 2, \
        f"kill_bar {kill_bar} must equal halfway (start+end)//2 = {(start + end) // 2}."
    assert start < kill_bar < end, f"kill_bar must split the window: [{start}, {end}]."
    persist_every = int(a.persist_every if a.persist_every is not None
                        else rt.get("persist_every", config["state"].get("persist_every_n_bars", 1000)))

    ref_csv = root / rt["reference_intents"]
    kill_csv = root / rt["kill_intents"]
    res_csv = root / rt["resumed_intents"]
    ref_state = root / rt["reference_dir"] / "guard_halt_state.json"
    kill_state = root / rt["kill_dir"] / "guard_halt_state.json"
    res_state = root / rt["resumed_dir"] / "guard_halt_state.json"
    ref_alerts = root / rt["reference_dir"] / "alerts.jsonl"
    kill_alerts = root / rt["kill_dir"] / "alerts.jsonl"
    res_alerts = root / rt["resumed_dir"] / "alerts.jsonl"
    comp_path = root / rt["comparison"]
    summ_path = root / rt["summary"]
    for p in (ref_csv, kill_csv, res_csv, ref_state, kill_state, res_state,
              ref_alerts, kill_alerts, res_alerts, comp_path, summ_path,
              ref_csv.with_name(ref_csv.stem + "_summary.json"),
              kill_csv.with_name(kill_csv.stem + "_summary.json"),
              res_csv.with_name(res_csv.stem + "_summary.json")):
        if p.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {p}")

    candles = pd.read_parquet(root / config["data"]["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals_df = pd.read_parquet(root / config["data"]["signals_replay_only"])
    assert 0 <= start < kill_bar < end < len(candles), "window out of candle range."

    # Phase REF: uninterrupted reference.
    ref_strategy, ref_df, ref_report, ref_pred = _run_window(
        candles, signals_df, config, start, end, ref_state, ref_alerts,
        ref_csv, persist_every, None, None, "REFERENCE_FULL")
    # Phase KILL-A: first half, then simulated KILL (drop objects after final save).
    kill_strategy, kill_df, kill_report, kill_pred = _run_window(
        candles, signals_df, config, start, kill_bar, kill_state, kill_alerts,
        kill_csv, persist_every, None, None, "KILL_PART")
    kill_snap_bar = int(kill_strategy.snapshot_state()["last_bar"])
    assert kill_snap_bar == kill_bar, f"kill snapshot {kill_snap_bar} != {kill_bar}."
    kill_equity = float(kill_strategy.account.equity)
    kill_absorbed, kill_picks = int(kill_pred.collision_absorbed), list(kill_pred.collision_picks)
    del kill_strategy, kill_pred  # KILL: no shared mutable state survives except the snapshot file.
    # Phase RESUME-B: fresh objects, restore kill snapshot into the NEW resumed dir.
    res_strategy, res_df, res_report, res_pred = _run_window(
        candles, signals_df, config, kill_bar + 1, end, res_state, res_alerts,
        res_csv, persist_every, kill_state, kill_bar, "RESUMED_FULL")

    # ---- bit-identical continuation assertions (resumed-full vs reference) ----
    checks: dict = {}

    def _check(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = {"verdict": "PASS" if ok else "FAIL", "detail": detail}

    try:
        pd.testing.assert_frame_equal(res_df.reset_index(drop=True),
                                      ref_df.reset_index(drop=True), check_dtype=True)
        _check("intents", True, f"{len(ref_df)} rows bit-identical (columns+dtypes+values).")
    except AssertionError as e:
        _check("intents", False, f"DataFrame mismatch: {str(e)[:500]}")
    _check("equity", float(res_strategy.account.equity) == float(ref_strategy.account.equity),
           f"resumed={float(res_strategy.account.equity):.6f} ref={float(ref_strategy.account.equity):.6f}")
    _check("exits", int(res_strategy.account.exits) == int(ref_strategy.account.exits),
           f"resumed={int(res_strategy.account.exits)} ref={int(ref_strategy.account.exits)}")
    for key in ("signals_seen", "skipped_low_conf", "skipped_busy",
                "skipped_daily_halt", "skipped_divergence"):
        _check(f"counter:{key}", int(getattr(res_strategy, key)) == int(getattr(ref_strategy, key)),
               f"resumed={int(getattr(res_strategy, key))} ref={int(getattr(ref_strategy, key))}")
    _check("halts", res_strategy.daily_halt.halt_events == ref_strategy.daily_halt.halt_events
           and int(res_strategy.daily_halt.bars_halted) == int(ref_strategy.daily_halt.bars_halted),
           f"halt_days resumed={len(res_strategy.daily_halt.halt_events)} "
           f"ref={len(ref_strategy.daily_halt.halt_events)}; "
           f"halted_bars {int(res_strategy.daily_halt.bars_halted)} vs {int(ref_strategy.daily_halt.bars_halted)}")
    _check("alerts", list(res_strategy.alerts) == list(ref_strategy.alerts)
           and _sha256_file(res_alerts) == _sha256_file(ref_alerts),
           f"alert records resumed={len(res_strategy.alerts)} ref={len(ref_strategy.alerts)}; "
           f"jsonl sha256 equal={_sha256_file(res_alerts) == _sha256_file(ref_alerts)}")
    _check("guard_history", list(res_strategy.guard.history) == list(ref_strategy.guard.history)
           and int(res_strategy.guard.state_changes) == int(ref_strategy.guard.state_changes),
           f"history_len {len(res_strategy.guard.history)} vs {len(ref_strategy.guard.history)}; "
           f"changes {int(res_strategy.guard.state_changes)} vs {int(ref_strategy.guard.state_changes)}")
    _check("day_closes", list(res_strategy.day_closes) == list(ref_strategy.day_closes),
           f"day_closes {len(res_strategy.day_closes)} vs {len(ref_strategy.day_closes)}")
    _check("divergence", (res_strategy.divergence.tripped == ref_strategy.divergence.tripped)
           and int(res_strategy.divergence.blocks) == int(ref_strategy.divergence.blocks)
           and int(res_strategy.divergence.checks) == int(ref_strategy.divergence.checks)
           and list(getattr(res_strategy.divergence, "over_events", []))
           == list(getattr(ref_strategy.divergence, "over_events", [])),
           f"tripped={res_strategy.divergence.tripped}/{ref_strategy.divergence.tripped}; "
           f"blocks {int(res_strategy.divergence.blocks)}/{int(ref_strategy.divergence.blocks)}; "
           f"checks {int(res_strategy.divergence.checks)}/{int(ref_strategy.divergence.checks)}")
    _check("intents_csv_sha256", _sha256_file(res_csv) == _sha256_file(ref_csv),
           f"resumed={_sha256_file(res_csv)[:16]}.. ref={_sha256_file(ref_csv)[:16]}..")
    combined_absorbed = int(kill_absorbed) + int(res_pred.collision_absorbed)
    combined_picks = list(kill_picks) + list(res_pred.collision_picks)
    _check("adapter_collisions_combined", combined_absorbed == int(ref_pred.collision_absorbed)
           and combined_picks == list(ref_pred.collision_picks),
           f"kill({kill_absorbed})+resumed({int(res_pred.collision_absorbed)})={combined_absorbed} "
           f"vs ref({int(ref_pred.collision_absorbed)}); picks {len(combined_picks)} vs {len(list(ref_pred.collision_picks))} "
           f"(predictor log not in snapshot by design; stateless pick => summed comparison).")

    divergences = {k: v for k, v in checks.items() if v["verdict"] == "FAIL"}
    overall = "PASS" if not divergences else "FAIL"
    comparison = {"mode": v1.MODE_LABEL, "exploratory": True, "live_orders": False,
                  "label": "OPENED-INTERVAL REHEARSAL (not forward validation)",
                  "driver": DRIVER_VERSION, "adapter": ADAPTER_VERSION,
                  "window": [start, end], "kill_bar": kill_bar,
                  "kill_rule": rt.get("kill_bar_rule", ""),
                  "kill_snapshot_equity": kill_equity,
                  "kill_snapshot_bar": kill_snap_bar,
                  "persist_every": persist_every,
                  "reference": {"intents": len(ref_df), "equity": float(ref_strategy.account.equity),
                                "exits": int(ref_strategy.account.exits),
                                "csv_sha256": _sha256_file(ref_csv)},
                  "resumed": {"intents": len(res_df), "equity": float(res_strategy.account.equity),
                              "exits": int(res_strategy.account.exits),
                              "csv_sha256": _sha256_file(res_csv)},
                  "checks": checks, "overall": overall,
                  "divergence_cause": ("" if overall == "PASS"
                                       else f"{len(divergences)} FAIL: " + "; ".join(
                                           f"{k} {v['detail']}" for k, v in divergences.items())[:2000]),
                  "ops_verdict": ("RESTART-SAFE (this book): kill at halfway + restore continues "
                                  "bit-identically; state file is a sufficient restart record."
                                  if overall == "PASS" else
                                  "NOT restart-safe: divergence found, see divergence_cause.")}
    comp_path.parent.mkdir(parents=True, exist_ok=True)
    comp_path.write_text(json.dumps(comparison, indent=2, default=str))
    summary = {"mode": v1.MODE_LABEL, "exploratory": True, "live_orders": False,
               "label": "OPENED-INTERVAL REHEARSAL (not forward validation)",
               "mission": "Resume-from-state on the L3-combo book (gap #2 from the papercombo report)",
               "book": {"signals": str(config["data"]["signals_replay_only"]),
                        "baseline": str(config["divergence"]["baseline"]),
                        "window_bars": [start, end], "bars_walked": end + 1 - start,
                        "kill_bar": kill_bar},
               "run": {"bot": "paper_trader_v21 (UNMODIFIED) + adapter r27L3 (UNMODIFIED) + driver r29L3",
                       "config": str(a.config), "persist_every": persist_every,
                       "reference_dir": str(rt["reference_dir"]),
                       "kill_dir": str(rt["kill_dir"]), "resumed_dir": str(rt["resumed_dir"])},
               "results": {"reference_intents": len(ref_df),
                           "resumed_intents": len(res_df),
                           "reference_equity": float(ref_strategy.account.equity),
                           "resumed_equity": float(res_strategy.account.equity),
                           "reference_exits": int(ref_strategy.account.exits),
                           "resumed_exits": int(res_strategy.account.exits),
                           "overall": overall, "checks": {k: v["verdict"] for k, v in checks.items()}},
               "files": {"driver": "scripts/opencode_r29L3_resume.py",
                         "config": str(a.config),
                         "reference_intents": str(rt["reference_intents"]),
                         "kill_intents": str(rt["kill_intents"]),
                         "resumed_intents": str(rt["resumed_intents"]),
                         "comparison": str(rt["comparison"]),
                         "summary": str(rt["summary"])},
               "paper_only": True}
    summ_path.write_text(json.dumps(summary, indent=2, default=str))
    print(f"[{v1.MODE_LABEL}] resume rehearsal overall={overall} kill_bar={kill_bar} "
          f"ref_intents={len(ref_df)} res_intents={len(res_df)} "
          f"ref_eq={float(ref_strategy.account.equity):.4f} res_eq={float(res_strategy.account.equity):.4f}.",
          flush=True)
    print(f"[{v1.MODE_LABEL}] wrote {comp_path} + {summ_path}", flush=True)
    if overall != "PASS":
        raise SystemExit(f"RESUME DIVERGENCE: {comparison['divergence_cause']}")


if __name__ == "__main__":
    main()
