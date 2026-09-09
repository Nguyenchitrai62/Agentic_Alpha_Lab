"""Opencode v10 (R2-B2): decision-clock thinning on FROZEN v30 isotonic-4 scores.

Frozen inputs (never refit):
  artifacts/research/opencode_v02_reproduce_v30/isotonic_4/predictions.npz
    keys: prediction (N, n_candidates, 6), decision_indices into decisions.parquet
  data/processed/swing_regime_research_v4/decisions.parquet

Grid discovery (pre-specified in configs/opencode_v10_mtfclock.json BEFORE running):
  The frozen frame is 4076 rows on a perfectly regular 6-HOURLY grid
  (00/06/12/18 UTC; the repo decision clock is stride-72, see
  tests/test_decision_clock.py; "5m" is the base candle resolution, not a
  decision frame). Literal first-row-per-UTC-hour and first-row-per-4h-block
  rules both keep 4076/4076 rows (identity; asserted at runtime). The 1h/4h
  branch slots therefore execute the nearest achievable lower-frequency
  thinnings (12-hourly 00/12 UTC, and 24-hourly/daily 00 UTC), carrying each
  kept row's frozen calibrated prediction vector UNCHANGED. This isolates the
  clock effect exactly as hypothesised. Branch names keep the assigned
  {5m-control, 1h, 4h} labels; each branch records its actual_decision_grid.

Method per branch: IDENTICAL choose() + swing_signals frequency-policy loop
(cooldown + monthly cap) + backtest chain on the subsampled frame; prediction
content untouched; thresholds/costs/holding grid frozen.

Sizing:
  1x       : fixed 1.0 leverage (base_exec 1.0/1.0).
  dd_guard : lev = 0.5 while 5m-control_1x sampled equity is >10% under its
             trailing peak (past-only 1-microsecond cutoff, 100.0 seed), else
             1.0. Trade-candle-close sampled equity, NOT mark/intrabar.

Control gate: 5m-control_1x normal must reproduce total_return 1.2279837998661565,
max_drawdown -0.20086073993367803, trades 65 (tolerance 1e-9) or STOP before
any other branch runs.

Scenarios per branch: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x only.
Monthly geometric uses duration from configs/swing_v15_continuous_folds.json.
Exploratory: opened 2023-2026 development interval, NOT an independent test.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.backtest.swing import swing_signals
from agentic_alpha_lab.data.training import sha256


TRADE_COLUMNS = ["signal_index", "direction", "leverage", "entry_index",
                 "entry_time", "entry_price", "exit_index", "exit_time",
                 "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                 "equity_before", "equity_after", "holding_bars",
                 "liquidation_price"]


def dd_guard_leverage(signal_times, ref_trades):
    """Past-only guard from 5m-control_1x sampled equity (disclosed).

    Equity curve sampled from trade exit_time/equity_after (trade-candle-close
    sampled, NOT true mark-price or full intrabar drawdown). At each signal
    time, uses only exits strictly before signal timestamp.
    """
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: v for ts, v in equity_at})
    out = []
    for ts in pd.to_datetime(signal_times, utc=True):
        ts = pd.Timestamp(ts)
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}), past]).sort_index()
        peak = float(curve.cummax().iloc[-1])
        level = float(curve.iloc[-1])
        out.append(0.5 if level / peak < 1.0 - 0.10 else 1.0)
    return np.array(out, dtype=float)


def fold_index(ts, folds):
    ts = pd.Timestamp(ts)
    for i, (start, end) in enumerate(folds):
        if pd.Timestamp(start) <= ts < pd.Timestamp(end):
            return i
    return -1


def run_branch(candles, signals, costs, execution, duration_years, out_dir, stress):
    scenarios = {}
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    estress, st, diagnostic = run_stress(candles, signals, 100, costs, execution, stress)
    for label, result, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                                 ("execution_stress", estress, st)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / duration_years) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * duration_years)) - 1}
        rows = [asdict(t) for t in items]
        pd.DataFrame(rows, columns=TRADE_COLUMNS if rows else None).to_csv(
            out_dir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios, trades


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    root = Path(__file__).resolve().parents[1]
    predictions_path = root / cfg["predictions"]
    decisions_path = root / cfg["decisions"]
    candles = pd.read_parquet(root / cfg["candles"])
    decisions = pd.read_parquet(decisions_path)
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    blob = np.load(predictions_path)
    prediction = blob["prediction"]
    decision_indices = blob["decision_indices"].astype(int)
    sub_decisions = decisions.iloc[decision_indices].reset_index(drop=True)
    sub_prediction = np.asarray(prediction)
    assert sub_prediction.shape[0] == len(sub_decisions) == 4076, "frozen frame shape changed"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"], "sizing axis changed"
    assert [b["name"] for b in cfg["branches"]] == [
        "5m-control_1x", "5m-control_dd_guard", "1h_1x", "1h_dd_guard", "4h_1x", "4h_dd_guard",
    ], "6-branch matrix changed"

    # --- Literal-rule audit: prove the brief's verbatim rules are vacuous here.
    hours = pd.to_datetime(sub_decisions["signal_time"], utc=True).dt.hour.to_numpy()
    assert set(np.unique(hours).tolist()) == {0, 6, 12, 18}, f"unexpected grid hours {np.unique(hours)}"
    day_hour = (pd.to_datetime(sub_decisions["signal_time"], utc=True).dt.floor("D").astype("int64") * 24
                + hours)
    literal_1h_keep = pd.Series(True, index=sub_decisions.index).groupby(day_hour).transform("first").to_numpy()
    block = (hours // 4)  # 4h blocks 00/04/08/12/16/20
    day_block = pd.to_datetime(sub_decisions["signal_time"], utc=True).dt.floor("D").astype("int64") * 6 + block
    literal_4h_keep = pd.Series(True, index=sub_decisions.index).groupby(day_block).transform("first").to_numpy()
    literal_audit = {"literal_1h_first_row_per_hour_kept": int(literal_1h_keep.sum()),
                     "literal_4h_first_row_per_block_kept": int(literal_4h_keep.sum()),
                     "frozen_rows": int(len(sub_decisions))}
    assert int(literal_1h_keep.sum()) == len(sub_decisions), "literal 1h rule is not identity"
    assert int(literal_4h_keep.sum()) == len(sub_decisions), "literal 4h rule is not identity"
    print(json.dumps({"literal_rule_audit": literal_audit}, indent=1), flush=True)

    # --- Intent-preserving thinning: pure function of each row's own UTC hour.
    clocks = {}
    for name, spec in cfg["clocks"].items():
        mask = np.isin(hours, np.asarray(spec["keep_hours_utc"]))
        assert int(mask.sum()) == spec["expected_rows"], f"{name}: got {mask.sum()}, want {spec['expected_rows']}"
        clocks[name] = {"mask": mask,
                        "frame": sub_decisions.loc[mask].reset_index(drop=True),
                        "pred": sub_prediction[mask],
                        "actual_grid": spec["actual_decision_grid"]}
        print(json.dumps({"clock": name, "actual_grid": spec["actual_decision_grid"],
                          "kept_rows": int(mask.sum())}), flush=True)

    # --- Whole-fold-structure check: every fold keeps coverage on every clock.
    folds = parent["folds"]
    fold_coverage = {}
    for name, c in clocks.items():
        idx = [fold_index(t, folds) for t in c["frame"]["signal_time"]]
        assert min(idx) >= 0, f"{name}: row outside fold structure"
        counts = pd.Series(idx).value_counts().sort_index().to_dict()
        assert len(counts) == len(folds) and all(v > 0 for v in counts.values()), f"{name}: fold lost"
        fold_coverage[name] = {str(k): int(v) for k, v in counts.items()}
    print(json.dumps({"fold_coverage": fold_coverage}, indent=1), flush=True)

    costs = CostModel(**ds_cfg["costs"])
    base_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                leverage=1.0, max_leverage=1.0)
    guard_exec = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                 max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                 leverage=float(cfg["lev_min"]), max_leverage=float(cfg["lev_max"]))
    stress = FillStress(int(cfg["stress"]["entry_penetration_bps"]),
                        int(cfg["stress"]["target_penetration_bps"]),
                        int(cfg["stress"]["market_exit_slippage_bps"]),
                        float(cfg["stress"]["market_exit_fee_rate"]),
                        bool(cfg["stress"]["allow_limit_price_improvement"]))
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    # --- Signals per clock: IDENTICAL swing_signals loop on each subsampled frame.
    clock_signals = {}
    for name, c in clocks.items():
        sigs = swing_signals(c["pred"], c["frame"], ds_cfg)
        clock_signals[name] = sigs
        print(json.dumps({"clock": name, "n_signals": int(len(sigs))}), flush=True)

    def branch_signal_frame(clock_name):
        sig = clock_signals[clock_name].copy()
        return sig.drop(columns=["leverage"]) if "leverage" in sig.columns else sig

    # --- Control run + reproduction gate (STOP on mismatch).
    ctrl = cfg["control_reproduction"]
    ctrl_dir = a.output / ctrl["branch"]
    ctrl_dir.mkdir()
    ctrl_sigs = branch_signal_frame("5m-control")
    ctrl_sigs.to_parquet(ctrl_dir / "signals.parquet", index=False)
    ref_scenarios, ref_trades = run_branch(candles, ctrl_sigs, costs, base_exec, duration, ctrl_dir, stress)
    n = ref_scenarios["normal"]
    ok = (n["trades"] == ctrl["expected_trades"]
          and abs(n["total_return"] - ctrl["expected_total_return"]) <= ctrl["tolerance"]
          and abs(n["max_drawdown"] - ctrl["expected_max_drawdown"]) <= ctrl["tolerance"])
    print(json.dumps({"control_check": ctrl["branch"],
                      "normal": {k: n[k] for k in ["total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net", "final_equity"]},
                      "expected": {k: ctrl[k] for k in ["expected_total_return", "expected_max_drawdown",
                                                        "expected_trades"]},
                      "match": bool(ok)}), flush=True)
    if not ok:
        print("CONTROL MISMATCH: STOPPING before any other branch (see control_reproduction).", flush=True)
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"got": {k: n[k] for k in ["total_return", "max_drawdown", "trades"]},
             "expected": {k: ctrl[k] for k in ["expected_total_return", "expected_max_drawdown",
                                               "expected_trades"]}}, indent=2, default=str))
        sys.exit(2)
    results = {ctrl["branch"]: ref_scenarios}

    for b in cfg["branches"]:
        name = b["name"]
        if name in results:
            continue
        clock_name = b["clock"]
        filt = branch_signal_frame(clock_name)
        bdir = a.output / name
        bdir.mkdir()
        if b["sizing"] == "1x":
            filt.to_parquet(bdir / "signals.parquet", index=False)
            scenarios, _ = run_branch(candles, filt, costs, base_exec, duration, bdir, stress)
        else:
            levs = dd_guard_leverage(filt["signal_time"] if len(filt) else [], ref_trades)
            sig = filt.copy()
            sig["leverage"] = levs
            sig.to_parquet(bdir / "signals.parquet", index=False)
            scenarios, _ = run_branch(candles, sig, costs, guard_exec, duration, bdir, stress)
        results[name] = scenarios
        print(json.dumps({"branch": name, "clock": clock_name,
                          "actual_grid": clocks[clock_name]["actual_grid"],
                          "n_signals": int(len(filt)),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades", "monthly_geometric_net",
                                            "gross_pnl", "fees", "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")}}), flush=True)

    for branch, scenarios in results.items():
        for scen, metrics in scenarios.items():
            if scen not in ("normal", "fee_stress", "execution_stress"):
                continue
            try:
                m_pass = bool(metrics["monthly_geometric_net"] >= gate["monthly_min"])
                d_pass = bool(metrics["max_drawdown"] >= -abs(gate["dd_max"]))
                f_pass = bool(metrics["trades"] >= gate["fills_min"])
            except (KeyError, TypeError):
                continue
            metrics["gate"] = {"monthly_geometric_net_ge_5pct": m_pass,
                               "drawdown_within_20pct": d_pass,
                               "fills_ge_30": f_pass,
                               "pass_all": bool(m_pass and d_pass and f_pass)}
    report = {"branches": results, "config": cfg,
              "actual_grids": {b["name"]: clocks[b["clock"]]["actual_grid"] for b in cfg["branches"]},
              "kept_rows": {k: int(v["mask"].sum()) for k, v in clocks.items()},
              "literal_rule_audit": literal_audit,
              "fold_coverage": fold_coverage,
              "control_reproduction": {"branch": ctrl["branch"], "match": True,
                                       "normal": {k: n[k] for k in
                                                  ["total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net", "final_equity"]}},
              "formulas": {"choose": "argmax eligible expected net (fill*pred_mean); thresholds frozen",
                           "frequency": "swing_signals exact loop (cooldown+monthly cap) per thinned frame",
                           "thinning": "keep rows by own UTC hour only (causal); frozen vectors carried unchanged",
                           "dd_guard": "0.5x while 5m-control_1x sampled equity >10% under trailing peak, "
                           "past-only 1-microsecond cutoff, 100.0 seed; trade-candle-close sampled; "
                           "applies to ALL dd_guard branches at their own signal times",
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only",
                           "monthly_geometric": "ratio=final/100; monthly=ratio**(1/(12*duration_years))-1"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Exploratory on the opened 2023-2026 development interval only. "
              "NOT an independent test; no validation claims. Do not promote any branch. "
              "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
              "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills. "
              "Branch labels 1h/4h denote assigned matrix slots; actual_decision_grid per branch "
              "is 12h (00/12 UTC) and 24h/daily (00 UTC) because the base grid is 6-hourly.",
              "input_sha256": {str(k): sha256(root / v) for k, v in
                               (("predictions", cfg["predictions"]), ("decisions", cfg["decisions"]),
                                ("candles", cfg["candles"]), ("dataset_config", cfg["dataset_config"]),
                                ("parent_plan", cfg["parent_plan"]))},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
