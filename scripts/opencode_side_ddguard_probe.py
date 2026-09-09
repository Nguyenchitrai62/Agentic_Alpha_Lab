"""Opencode v04: side decomposition x dd_guard overlay on FROZEN v30 isotonic-4 signals.

Frozen inputs (never refit): artifacts/research/opencode_v02_reproduce_v30/isotonic_4/signals.parquet
Pre-specified matrix (fixed before running; signals/scores untouched):
  sides  {all, long_only (direction==1), short_only (direction==-1)}
  sizing {1x, dd_guard}
  = 6 branches: all_1x, all_dd_guard, long_only_1x, long_only_dd_guard,
                short_only_1x, short_only_dd_guard
  dd_guard lev = 0.5 while base-1x-ALL sampled equity is >10% under its
                 trailing peak (past-only), else 1.0.
Guard state for EVERY dd_guard branch is derived from the base-1x-ALL run's
sampled equity (same disclosed method as scripts/opencode_risk_overlay_probe.py),
applied at the side-filtered signal times. All quantities used at signal time
come from strictly earlier data (signal timestamps get a 1-microsecond cutoff).
Each branch x 3 scenarios (normal / fee_stress / execution_stress).
Exploratory: the 2023-2026 interval is opened development data, NOT an independent test.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256


DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0


def dd_guard_leverage(signals, trades):
    """Same disclosed method as scripts/opencode_risk_overlay_probe.py.

    Equity curve is sampled from trade exit_time/equity_after (trade-candle-close
    sampled, NOT true mark-price or full intrabar drawdown). Guard at signal time
    uses only exits strictly before the signal timestamp (past-only).
    """
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in trades]
    equity_at.sort()
    eq = pd.Series({ts: eq for ts, eq in equity_at})
    out = []
    for ts in signals["signal_time"]:
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}), past]).sort_index()
        peak = float(curve.cummax().iloc[-1])
        level = float(curve.iloc[-1])
        out.append(DD_GUARD_LEV if level / peak < 1.0 - DD_TRIGGER else 1.0)
    return np.array(out)


def run_branch(candles, signals, costs, execution, duration_years, out_dir):
    scenarios = {}
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": 0.00055})
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    stress, st, diagnostic = run_stress(candles, signals, 100, costs, execution,
                                        FillStress(5, 5, 5, 0.00055, False))
    for label, result, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                                 ("execution_stress", stress, st)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / duration_years) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * duration_years)) - 1}
        rows = [asdict(t) for t in items]
        pd.DataFrame(rows, columns=["signal_index", "direction", "leverage", "entry_index",
                                    "entry_time", "entry_price", "exit_index", "exit_time",
                                    "exit_reason", "gross_pnl", "fees", "funding", "net_pnl",
                                    "equity_before", "equity_after", "holding_bars",
                                    "liquidation_price"] if rows else None).to_csv(
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
    candles = pd.read_parquet(root / cfg["candles"])
    base_signals = pd.read_parquet(root / cfg["signals"])
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    costs = CostModel(**ds_cfg["costs"])
    execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                leverage=LEV_MIN, max_leverage=LEV_MAX)
    base_exec = ExecutionConfig(entry_expiry_bars=execution.entry_expiry_bars,
                                max_holding_bars=execution.max_holding_bars,
                                leverage=1.0, max_leverage=1.0)
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    gate = cfg.get("gate", {"monthly_min": 0.05, "dd_max": 0.2, "fills_min": 30})
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    # Reference run: base-1x-ALL. Guard state for all dd_guard branches derives from this.
    ref_signals = base_signals.copy()
    if "leverage" in ref_signals.columns:
        ref_signals = ref_signals.drop(columns=["leverage"])
    ref_dir = a.output / "all_1x"
    ref_dir.mkdir()
    ref_scenarios, ref_trades = run_branch(candles, ref_signals, costs, base_exec, duration, ref_dir)
    ref_signals.to_parquet(ref_dir / "signals.parquet", index=False)
    results = {"all_1x": ref_scenarios}

    guard_all = dd_guard_leverage(base_signals, ref_trades)
    guard_by_index = dict(zip(base_signals.index.to_numpy(), guard_all))

    side_filters = {"all": None, "long_only": 1, "short_only": -1}
    for side_name, direction in side_filters.items():
        for sizing in ("1x", "dd_guard"):
            branch = f"{side_name}_{sizing}" if side_name != "all" else ("all_1x" if sizing == "1x" else "all_dd_guard")
            if branch in results:
                continue
            filt = base_signals if direction is None else base_signals[base_signals["direction"] == direction]
            filt = filt.copy()
            bdir = a.output / branch
            bdir.mkdir()
            if sizing == "1x":
                sig = filt.drop(columns=["leverage"]) if "leverage" in filt.columns else filt
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, base_exec, duration, bdir)
            else:
                levs = np.array([guard_by_index[i] for i in filt.index.to_numpy()])
                sig = filt.copy()
                sig["leverage"] = levs
                sig.to_parquet(bdir / "signals.parquet", index=False)
                scenarios, _ = run_branch(candles, sig, costs, execution, duration, bdir)
            results[branch] = scenarios
            print(json.dumps({"branch": branch,
                              "metrics": {s: {k: scenarios[s][k] for k in
                                               ["total_return", "max_drawdown", "trades", "monthly_geometric_net",
                                                "gross_pnl", "fees", "funding", "profit_factor", "win_rate",
                                                "long_trades", "short_trades"]}
                                          for s in ("normal", "fee_stress", "execution_stress")}}), flush=True)

    for branch, scenarios in results.items():
        for scen, metrics in scenarios.items():
            if scen == "execution_stress" and not isinstance(metrics.get("total_return"), (int, float)):
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
              "formulas": {"dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "guard_reference": "base-1x-ALL sampled equity (trade exit_time/equity_after), "
                           "past-only 1-microsecond cutoff, 100.0 seed level; side-filtered signals reuse "
                           "the ALL-run guard state at their own signal times",
                           "fee_stress": "fee_rate_per_fill=0.00055",
                           "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x only"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Exploratory on the opened 2023-2026 development interval only. "
              "NOT an independent test; no validation claims. Do not promote any branch. "
              "Drawdown is trade-candle-close sampled, not true mark-price/intrabar drawdown. "
              "Stop/timeout exits are market-like at the scenario fee, not guaranteed maker fills.",
              "input_sha256": {str(k): sha256(root / v) for k, v in
                               (("candles", cfg["candles"]), ("signals", cfg["signals"]),
                                ("dataset_config", cfg["dataset_config"]), ("parent_plan", cfg["parent_plan"]))},
              "gate": gate}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))
