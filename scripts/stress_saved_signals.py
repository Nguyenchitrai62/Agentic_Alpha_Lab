"""Reprice already-recorded signals under declared friction scenarios; no tuning."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, align_signal_indices
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256, validate_source


def run(a):
    if a.output.exists():
        raise FileExistsError("Choose a new sensitivity output; do not overwrite historical evidence")
    original = json.loads(a.report.read_text())
    cfg_file = json.loads(a.config.read_text())
    config = cfg_file.get("config", cfg_file)
    candles = validate_source(pd.read_parquet(a.candles))
    signals = align_signal_indices(candles, pd.read_parquet(a.signals))
    costs = CostModel(**config["costs"])
    execution = ExecutionConfig(entry_expiry_bars=config["entry_expiry_bars"],
                                max_holding_bars=max(config["holding_days"]) * 288)
    scenarios = {"zero_stress_parity": FillStress()}
    for bps in (2., 5., 10.):
        scenarios[f"penetration_and_market_slippage_{int(bps)}bps"] = FillStress(
            entry_penetration_bps=bps, target_penetration_bps=bps,
            market_exit_slippage_bps=bps, market_exit_fee_rate=.00055,
            allow_limit_price_improvement=False)
    results, trade_frames = {}, {}
    for name, stress in scenarios.items():
        result, trades, diagnostics = run_stress(candles, signals, original["result"]["initial_equity"], costs, execution, stress)
        if name == "zero_stress_parity":
            for field, value in original["result"].items():
                found = asdict(result)[field]
                if (value is None and found is not None) or (value is not None and not np.isclose(found, value, rtol=1e-8, atol=1e-8)):
                    raise ValueError(f"Baseline differs from original: {field}: {found} vs {value}")
        results[name] = {"result": asdict(result), **diagnostics}
        trade_frames[name] = pd.DataFrame([asdict(t) for t in trades])
    root = Path(__file__).resolve().parents[1]
    paths = [a.report, a.signals, a.candles, a.config, Path(__file__), root / "src/agentic_alpha_lab/backtest/execution_stress.py",
             root / "src/agentic_alpha_lab/backtest/engine.py", root / "src/agentic_alpha_lab/data/training.py"]
    report = {"original_split": original["split"], "new_independent_test": False,
              "signals_regenerated_or_tuned": False, "original_report_modified": False,
              "input_sha256": {str(p): sha256(p) for p in paths}, "scenarios": results,
              "warning": "Sensitivity on already-opened signals only. Do not select the most favorable friction or claim a fresh test. Missing fills can change which subsequent trades occur; effects need not be monotonic."}
    a.output.mkdir(parents=True)
    (a.output / "report.json").write_text(json.dumps(report, indent=2))
    for name, frame in trade_frames.items():
        frame.to_csv(a.output / f"{name}_trades.csv", index=False)
    print(json.dumps({name: {"return": r["result"]["total_return"], "close_dd": r["result"]["max_drawdown"],
                            "adverse_sample_dd": r["adverse_price_sampled_drawdown"], "fills": r["result"]["trades"]}
                      for name, r in results.items()}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("report", "signals", "candles", "config", "output"):
        p.add_argument(f"--{name}", type=Path, required=True)
    run(p.parse_args())
