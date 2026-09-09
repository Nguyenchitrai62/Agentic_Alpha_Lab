"""Resume helper for v27: compute ONLY missing outputs, never overwrite existing files.

Existing: all 8 signals.parquet + 7/8 branches' trades CSVs.
Missing: stop150_dd_guard {normal,fee_stress,execution_stress}_trades.csv + summary.json.
This script re-runs branches IN MEMORY (deterministic) for summary.json metrics,
writes ONLY files that do not already exist, then writes summary.json.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import json
from dataclasses import asdict
from pathlib import Path
import importlib.util
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256

root = Path(__file__).resolve().parents[1]
out = root / "artifacts/research/opencode_v27_stopfix"
cfg = json.loads((out / "config.json").read_text())

spec = importlib.util.spec_from_file_location(
    "probe", root / "scripts/opencode_r5n_stopfix_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

candles = pd.read_parquet(root / cfg["candles"])
base_signals = pd.read_parquet(root / cfg["signals"])
ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
parent = json.loads((root / cfg["parent_plan"]).read_text())
costs = CostModel(**ds_cfg["costs"])
fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": cfg["fee_stress_rate"]})
stress = FillStress(cfg["stress"]["entry_penetration_bps"],
                    cfg["stress"]["target_penetration_bps"],
                    cfg["stress"]["market_exit_slippage_bps"],
                    cfg["stress"]["market_exit_fee_rate"],
                    cfg["stress"]["allow_limit_price_improvement"])

DURATION = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
            .total_seconds() / (365.2425 * 86400))

# Guard reference: deterministic re-run of frozen control signals (in-memory, no writes).
ref_signals = pd.read_parquet(out / "stop100_1x/signals.parquet")
_, control_trades = run_backtest(
    candles, ref_signals, 100, costs,
    ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                    max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                    tp1_fraction=0.5, leverage=1.0, max_leverage=1.0))


def exec_for(sizing):
    if sizing == "1x":
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                               tp1_fraction=0.5, leverage=1.0, max_leverage=1.0)
    return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                           max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                           tp1_fraction=0.5, leverage=0.25, max_leverage=1.0)


def run_branch_mem(signals, execution):
    scenarios = {}
    normal, _ = run_backtest(candles, signals, 100, costs, execution)
    fee, _ = run_backtest(candles, signals, 100, fee_costs, execution)
    estress, _, diagnostic = run_stress(candles, signals, 100, costs, execution, stress)
    for label, result in (("normal", normal), ("fee_stress", fee),
                          ("execution_stress", estress)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / DURATION) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * DURATION)) - 1}
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios


results = {}
order = ["stop050_1x", "stop050_dd_guard", "stop075_1x", "stop075_dd_guard",
         "stop100_1x", "stop100_dd_guard", "stop150_1x", "stop150_dd_guard"]
mult_of = {"stop050": 0.5, "stop075": 0.75, "stop100": 1.0, "stop150": 1.5}
for branch in order:
    bdir = out / branch
    sig = pd.read_parquet(bdir / "signals.parquet")
    sizing = "dd_guard" if branch.endswith("dd_guard") else "1x"
    ex = exec_for(sizing)
    scenarios = run_branch_mem(sig, ex)
    # Write ONLY missing trades CSVs (stop150_dd_guard); never overwrite.
    if branch == "stop150_dd_guard":
        _, t_n = run_backtest(candles, sig, 100, costs, ex)
        _, t_f = run_backtest(candles, sig, 100, fee_costs, ex)
        _, t_s, _ = run_stress(candles, sig, 100, costs, ex, stress)
        for label, items in (("normal", t_n), ("fee_stress", t_f),
                             ("execution_stress", t_s)):
            target = bdir / f"{label}_trades.csv"
            assert not target.exists(), f"refusing to overwrite {target}"
            pd.DataFrame([asdict(t) for t in items]).to_csv(target, index=False)
    n = scenarios["normal"]
    print(json.dumps({"branch": branch, "normal": {k: n[k] for k in (
        "total_return", "max_drawdown", "trades", "monthly_geometric_net")},
        "gate": probe.gate_flags(scenarios, cfg["gate"])["overall_pass"]}), flush=True)
    mkey = branch.split("_")[0]
    results[branch] = {"scenarios": scenarios, "n_signals": len(sig),
                       "stop_mult": mult_of[mkey], "sizing": sizing}

flagged = {b: {"gate": probe.gate_flags(v["scenarios"], cfg["gate"]),
               "n_signals": v["n_signals"], "stop_mult": v["stop_mult"],
               "sizing": v["sizing"], "scenarios": v["scenarios"]} for b, v in results.items()}
report = {"branches": flagged, "config": cfg,
          "formulas": {"stop_formula": cfg["stop_formula"],
                       "stop_mults": cfg["stop_mults"],
                       "dd_trigger": 0.10, "dd_guard_lev": 0.5,
                       "dd_guard_reference": cfg["dd_guard_reference"],
                       "lev_min": 0.25, "lev_max": 1.0, "tp1_fraction": 0.5,
                       "stop_path": "honored: engine run_backtest + run_stress both "
                                    "_stop_fill(bar,side,float(signal.stop_loss)), "
                                    "stop_first intrabar policy"},
          "duration_years": DURATION, "independent_test": False, "live_approved": False,
          "exploratory": True,
          "warning": ("Exploratory labels: opened development interval only ("
                      + parent["complete_evaluation_until"] + "). Stop multiples are frozen "
                      "constants per branch (no fitting). Do not promote any branch or "
                      "claim validation."),
          "input_sha256": {str(q): sha256(root / q) for q in
                           (cfg["candles"], cfg["signals"], cfg["dataset_config"],
                            cfg["parent_plan"], "configs/opencode_v27_stopfix.json")},
          "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                   "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
target = out / "summary.json"
assert not target.exists(), "refusing to overwrite summary.json"
target.write_text(json.dumps(report, indent=2))
print("WROTE", str(target))
