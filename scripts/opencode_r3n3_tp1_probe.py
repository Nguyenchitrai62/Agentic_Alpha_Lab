"""Opencode v16 (R3-N3): TP1 take-fraction exit matrix on FROZEN v30 isotonic-4 signals.

Frozen inputs (never refit): artifacts/research/opencode_v02_reproduce_v30/isotonic_4/signals.parquet (94)
Pre-specified branches (configs/opencode_v16_tp1.json, fractions frozen before running):
  tp1_fraction {0.25, 0.5, 0.75} x sizing {1x, dd_guard} = 6 branches.
  tp1_fraction is a frozen ExecutionConfig constant per branch (causal past-only).
dd_guard: lev = 0.5 while TP1=0.5-CONTROL 1x sampled equity is >10% under its
  trailing peak (past-only, 1-microsecond cutoff), else 1.0. Shared control-equity
  reference disclosed in config (deviation from v03 own-book reference).
Control gate: tp050_1x (tp1=0.5/1x) normal must reproduce +122.80% total_return /
  -20.09% max_drawdown / 65 trades or STOP (asserted in-script).
Stress path: run_stress honors ExecutionConfig.tp1_fraction
  (execution_stress.py close_fraction(fill, execution.tp1_fraction, ...));
  asserted at runtime via source check + validation 0<f<1.
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


def dd_guard_leverage_at(signal_times, ref_trades):
    """Guard state from reference (control) equity, evaluated at given signal times."""
    equity_at = [(pd.Timestamp(t.exit_time), t.equity_after) for t in ref_trades]
    equity_at.sort()
    eq = pd.Series({ts: eq for ts, eq in equity_at})
    out = []
    for ts in signal_times:
        past = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(past) == 0:
            out.append(1.0)
            continue
        curve = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}), past]).sort_index()
        peak = float(curve.cummax().iloc[-1])
        level = float(curve.iloc[-1])
        out.append(DD_GUARD_LEV if level / peak < 1.0 - DD_TRIGGER else 1.0)
    return np.array(out)


def run_branch(candles, signals, costs, fee_costs, execution, stress, duration_years, out_dir):
    scenarios = {}
    normal, trades = run_backtest(candles, signals, 100, costs, execution)
    fee, ft = run_backtest(candles, signals, 100, fee_costs, execution)
    estress, st, diagnostic = run_stress(candles, signals, 100, costs, execution, stress)
    for label, result, items in (("normal", normal, trades), ("fee_stress", fee, ft),
                                 ("execution_stress", estress, st)):
        ratio = result.final_equity / 100
        scenarios[label] = {**asdict(result),
                            "annual_geometric_net": ratio ** (1 / duration_years) - 1,
                            "monthly_geometric_net": ratio ** (1 / (12 * duration_years)) - 1}
        pd.DataFrame([asdict(t) for t in items]).to_csv(out_dir / f"{label}_trades.csv", index=False)
    scenarios["execution_stress"]["diagnostics"] = diagnostic
    return scenarios


def gate_flags(scenarios, gate):
    flags = {}
    for s in ("normal", "fee_stress", "execution_stress"):
        m = scenarios[s]
        flags[s] = {"monthly_pass": bool(m["monthly_geometric_net"] >= gate["monthly_min"]),
                    "dd_pass": bool(abs(m["max_drawdown"]) <= gate["dd_max"]),
                    "fills_pass": bool(m["trades"] >= gate["fills_min"])}
        flags[s]["scenario_pass"] = all(flags[s].values())
    flags["overall_pass"] = all(flags[s]["scenario_pass"] for s in
                                ("normal", "fee_stress", "execution_stress"))
    return flags


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    cfg = json.loads(a.config.read_text())
    root = Path(__file__).resolve().parents[1]

    # Runtime VERIFY: stress path honors tp1_fraction (source-level assertion).
    stress_src = (root / "src/agentic_alpha_lab/backtest/execution_stress.py").read_text()
    assert "execution.tp1_fraction" in stress_src, "stress path does not reference tp1_fraction"
    assert "0 < execution.tp1_fraction < 1" in stress_src, "stress path missing tp1 validation"

    candles = pd.read_parquet(root / cfg["candles"])
    base_signals = pd.read_parquet(root / cfg["signals"])
    assert len(base_signals) == 94, f"frozen signal count changed: {len(base_signals)}"
    ds_cfg = json.loads((root / cfg["dataset_config"]).read_text())
    parent = json.loads((root / cfg["parent_plan"]).read_text())
    costs = CostModel(**ds_cfg["costs"])
    fee_costs = CostModel(**{**asdict(costs), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    stress = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])

    def exec_for(tp1, sizing):
        assert 0 < tp1 < 1, f"tp1_fraction must satisfy 0<f<1, got {tp1}"
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                   tp1_fraction=tp1, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                               tp1_fraction=tp1, leverage=LEV_MIN, max_leverage=LEV_MAX)

    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def prepared(tp1, sizing, guard_vec=None):
        sig = base_signals.copy()
        # Provenance only: engine reads ExecutionConfig.tp1_fraction, not this column.
        sig["tp1_fraction"] = tp1
        if sizing == "1x":
            if "leverage" in sig.columns:
                sig = sig.drop(columns=["leverage"])
        else:
            assert guard_vec is not None
            sig["leverage"] = guard_vec
        return sig.reset_index(drop=True)

    results = {}
    # --- control tp050_1x first (reproduction gate) ---
    c_tp1 = cfg["tp1_fractions"]["tp050"]
    cdir = a.output / "tp050_1x"
    cdir.mkdir()
    ref_signals = prepared(c_tp1, "1x")
    ref_signals.to_parquet(cdir / "signals.parquet", index=False)
    ref_scenarios = run_branch(candles, ref_signals, costs, fee_costs,
                               exec_for(c_tp1, "1x"), stress, duration, cdir)
    n = ref_scenarios["normal"]
    ok = (abs(n["total_return"] - 1.2280) < 0.005 and abs(n["max_drawdown"] - (-0.2009)) < 0.005
          and n["trades"] == 65)
    print(json.dumps({"branch": "tp050_1x", "n_signals": len(ref_signals),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "control_check": "PASS" if ok else "FAIL"}), flush=True)
    if not ok:
        raise SystemExit(f"CONTROL REPRODUCTION FAILED: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    results["tp050_1x"] = {"scenarios": ref_scenarios, "n_signals": len(ref_signals),
                           "tp1_fraction": c_tp1, "sizing": "1x"}

    # Guard reference = tp050_1x control equity (past-only). Fresh deterministic
    # re-run of the same control (matches v11 precedent); identical to ref run.
    _, control_trades = run_backtest(candles, ref_signals, 100, costs, exec_for(c_tp1, "1x"))
    guard_cache = {}

    def guard_for(sig):
        key = tuple(pd.to_datetime(sig["signal_time"]).astype("int64"))
        if key not in guard_cache:
            guard_cache[key] = dd_guard_leverage_at(pd.to_datetime(sig["signal_time"]),
                                                    control_trades)
        return guard_cache[key]

    plan = [("tp025_1x", "tp025", "1x"), ("tp025_dd_guard", "tp025", "dd_guard"),
            ("tp050_dd_guard", "tp050", "dd_guard"),
            ("tp075_1x", "tp075", "1x"), ("tp075_dd_guard", "tp075", "dd_guard")]
    for branch, tp_key, sizing in plan:
        bdir = a.output / branch
        bdir.mkdir()
        tp1 = cfg["tp1_fractions"][tp_key]
        if sizing == "1x":
            sig = prepared(tp1, "1x")
            ex = exec_for(tp1, "1x")
        else:
            # Guard state evaluated at this branch's own signal times from the
            # frozen tp050 control reference (past-only 1-microsecond cutoff).
            probe = base_signals.copy()
            sig = prepared(tp1, "dd_guard", guard_for(probe))
            ex = exec_for(tp1, "dd_guard")
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios = run_branch(candles, sig, costs, fee_costs, ex, stress, duration, bdir)
        results[branch] = {"scenarios": scenarios, "n_signals": len(sig),
                           "tp1_fraction": tp1, "sizing": sizing}
        print(json.dumps({"branch": branch, "n_signals": len(sig),
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": gate_flags(scenarios, cfg["gate"])["overall_pass"]}),
               flush=True)

    flagged = {b: {"gate": gate_flags(v["scenarios"], cfg["gate"]),
                   "n_signals": v["n_signals"], "tp1_fraction": v["tp1_fraction"],
                   "sizing": v["sizing"], "scenarios": v["scenarios"]} for b, v in results.items()}
    report = {"branches": flagged, "config": cfg,
              "formulas": {"tp1_fractions": cfg["tp1_fractions"],
                           "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                           "dd_guard_reference": cfg["dd_guard_reference"],
                           "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                           "stress_path_tp1": "honored: run_stress close_fraction(fill, "
                                              "execution.tp1_fraction, ...) + 0<f<1 validation"},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": ("Exploratory labels: opened development interval only ("
                          + parent["complete_evaluation_until"] + "). TP1 fractions are frozen "
                          "constants per branch (no fitting). Do not promote any branch or "
                          "claim validation."),
              "input_sha256": {str(q): sha256(root / q) for q in
                               (cfg["candles"], cfg["signals"], cfg["dataset_config"],
                                cfg["parent_plan"], "configs/opencode_v16_tp1.json")},
              "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                       "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2))
    print("WROTE", str(a.output / "summary.json"))
