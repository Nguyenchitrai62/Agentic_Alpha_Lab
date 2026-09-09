"""Opencode v03: causal risk overlays on FROZEN v30 isotonic-4 signals.

Frozen inputs (never refit): artifacts/research/opencode_v02_reproduce_v30/isotonic_4/signals.parquet
Pre-specified branches (formulas fixed before running; signals/scores untouched):
  - base_1x            : leverage 1.0 for every signal (reproduction reference)
  - vol_target_15      : lev = clip(0.15 / trailing-30d realized vol (ann.), 0.25, 1.0)
  - dd_guard           : lev = 0.5 while base-1x sampled equity is >10% under its
                         trailing peak (past-only), else 1.0
  - vol_target_dd_guard: lev = clip(vol_target_15 * dd_guard, 0.25, 1.0)
All vol/equity quantities use only candles/trades strictly before signal time.
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


VOL_TARGET = 0.15
VOL_LOOKBACK_DAYS = 30
LEV_MIN, LEV_MAX = 0.25, 1.0
DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5


def trailing_vol_leverage(candles, signal_times):
    closes = candles.set_index("open_time")["close"].sort_index()
    logret = np.log(closes / closes.shift(1))
    out = []
    for ts in signal_times:
        cutoff = ts - pd.Timedelta(microseconds=1)
        mask = (logret.index <= cutoff) & (logret.index > cutoff - pd.Timedelta(days=VOL_LOOKBACK_DAYS))
        window = logret.loc[mask].dropna()
        if len(window) < 100:
            out.append(1.0)
            continue
        vol_ann = float(window.std() * np.sqrt(365.2425 * 288))
        out.append(float(np.clip(VOL_TARGET / vol_ann if vol_ann > 0 else 1.0, LEV_MIN, LEV_MAX)))
    return np.array(out)


def dd_guard_leverage(signals, trades):
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


def run_branch(candles, signals, costs, execution, duration_years):
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
        pd.DataFrame([asdict(t) for t in items]).to_csv(
            execution_out / f"{label}_trades.csv", index=False)
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
    duration = ((pd.Timestamp(parent["complete_evaluation_until"]) - pd.Timestamp(parent["folds"][0][0]))
                .total_seconds() / (365.2425 * 86400))
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    base_exec = ExecutionConfig(entry_expiry_bars=execution.entry_expiry_bars,
                                max_holding_bars=execution.max_holding_bars,
                                leverage=1.0, max_leverage=1.0)
    ref_signals = base_signals.copy()
    if "leverage" in ref_signals.columns:
        ref_signals = ref_signals.drop(columns=["leverage"])
    ref_dir = a.output / "base_1x"
    ref_dir.mkdir()
    execution_out = ref_dir
    ref_scenarios, ref_trades = run_branch(candles, ref_signals, costs, base_exec, duration)

    vol_lev = trailing_vol_leverage(candles, pd.to_datetime(base_signals["signal_time"]))
    guard_lev = dd_guard_leverage(base_signals, ref_trades)
    branches = {"base_1x": np.ones(len(base_signals)),
                "vol_target_15": vol_lev,
                "dd_guard": guard_lev,
                "vol_target_dd_guard": np.clip(vol_lev * guard_lev, LEV_MIN, LEV_MAX)}
    results = {"base_1x": ref_scenarios}
    for name, levs in branches.items():
        if name == "base_1x":
            continue
        bdir = a.output / name
        bdir.mkdir()
        execution_out = bdir
        sig = base_signals.copy()
        sig["leverage"] = levs
        sig.to_parquet(bdir / "signals.parquet", index=False)
        scenarios, _ = run_branch(candles, sig, costs, execution, duration)
        results[name] = scenarios
        print(json.dumps({"branch": name,
                          "metrics": {s: {k: scenarios[s][k] for k in
                                           ["total_return", "max_drawdown", "trades", "monthly_geometric_net",
                                            "gross_pnl", "fees", "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")}}), flush=True)
    report = {"branches": results, "config": cfg, "formulas": {"vol_target": VOL_TARGET,
              "vol_lookback_days": VOL_LOOKBACK_DAYS, "lev_min": LEV_MIN, "lev_max": LEV_MAX,
              "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV},
              "duration_years": duration, "independent_test": False, "live_approved": False,
              "exploratory": True,
              "warning": "Opened development interval only. Do not promote any branch or claim validation.",
              "input_sha256": {str(p): sha256(root / p) for p in
                               (cfg["candles"], cfg["signals"], cfg["dataset_config"], cfg["parent_plan"])},
              "gate": {"monthly_min": 0.05, "dd_max": 0.20, "fills_min": 30}}
    (a.output / "summary.json").write_text(json.dumps(report, indent=2))
    print("WROTE", str(a.output / "summary.json"))
