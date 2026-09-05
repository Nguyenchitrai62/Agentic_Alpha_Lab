"""Evaluate a frozen portable tree pipeline on a predeclared historical holdout."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.models.tree_pipeline import PortableForest
from agentic_alpha_lab.models.regime_gate import apply_gate
from agentic_alpha_lab.data.swing import SwingStore
from agentic_alpha_lab.data.training import sha256, validate_source
from agentic_alpha_lab.backtest.swing import evaluate
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest


def trade_bootstrap(trades, seed=1729):
    if len(trades) < 6:
        return {"trade_count": len(trades), "replicates": 0,
                "warning": "Insufficient trades for even two size-3 blocks; no resampling quantiles reported. This is not a confidence interval."}
    returns = np.asarray([t.equity_after / t.equity_before - 1 for t in trades])
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(2000):
        start = rng.integers(0, len(returns), size=(len(returns)+2)//3)
        indices = ((start[:, None] + np.arange(3)) % len(returns)).ravel()[:len(returns)]
        samples.append(np.prod(1 + returns[indices]) - 1)
    return {"circular_trade_block_size": 3, "replicates": 2000,
            "net_return_percent_p025_p50_p975": (np.quantile(samples, [.025, .5, .975]) * 100).tolist(),
            "warning": "Descriptive resampling only; few dependent trades/regime shifts can invalidate confidence interpretation."}


def run(a):
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    portable = PortableForest(a.checkpoint)
    if sha256(a.checkpoint / "forests.npz") != meta["checkpoint_sha256"]:
        raise ValueError("Changed checkpoint")
    root = Path(__file__).resolve().parents[1]
    for name, digest in meta["source_hashes"].items():
        if sha256(root / name) != digest:
            raise ValueError(f"Source changed since freeze: {name}")
    config, plan = meta["config"], meta["research_plan"]
    start, end = map(pd.Timestamp, plan[a.interval])
    source = json.loads((a.source / "manifest.json").read_text())
    if sha256(a.source / "candles.parquet") != source["files"]["candles.parquet"]:
        raise ValueError("Source hash mismatch")
    if a.output.exists():
        raise FileExistsError("Do not overwrite an opened holdout")
    a.output.mkdir(parents=True)
    provenance = {"state": "opening_holdout", "interval": a.interval, "start": str(start), "end": str(end),
                  "checkpoint_sha256": meta["checkpoint_sha256"], "checkpoint_metadata_sha256": sha256(a.checkpoint / "metadata.json"),
                  "source_sha256": source["files"]["candles.parquet"], "evaluator_sha256": sha256(Path(__file__)),
                  "warning": "Once read this interval is research; never tune and reuse as an independent test."}
    (a.output / "evaluation_manifest.json").write_text(json.dumps(provenance, indent=2))
    candles = validate_source(pd.read_parquet(a.source / "candles.parquet"))
    candles = candles.loc[candles.close_time < end].reset_index(drop=True)
    store = SwingStore(candles, config)
    features, decisions = [], []
    span = max(config["holding_days"]) * 288 + config["entry_expiry_bars"]
    for i in range(0, len(candles) - span, config["stride"]):
        timestamp = candles.close_time.iloc[i]
        if timestamp < start:
            continue
        _, _, _, f, atr5, atr4 = store.sample(timestamp)
        features.append(f)
        decisions.append({"bar_index": i, "signal_time": timestamp, "close": float(candles.close.iloc[i]), "atr5": atr5, "atr4": atr4})
    if not features:
        raise ValueError("No valid windows")
    prediction, uncertainty = portable.swing_prediction(np.stack(features))
    prediction = apply_gate(prediction, np.stack(features), config, meta.get("regime_gate", "none"))
    decisions = pd.DataFrame(decisions)
    report, signals, trades_frame = evaluate(prediction, decisions, candles, config, "historical_holdout_no_tuning")
    signals = signals.drop(columns=["conditional_net_quantiles_percent", "conditional_win_score"], errors="ignore")
    execution = ExecutionConfig(entry_expiry_bars=config["entry_expiry_bars"], max_holding_bars=max(config["holding_days"]) * 288)
    _, trades = run_backtest(candles, signals, 100, CostModel(**config["costs"]), execution)
    report["bootstrap"] = trade_bootstrap(trades)
    report["quantiles_estimated"] = False
    report["model"] = meta["model"]
    dynamic = signals.copy()
    if len(dynamic):
        lookup = dict(zip(decisions.bar_index, range(len(decisions))))
        uncertainty_selected = np.asarray([uncertainty[lookup[int(r.bar_index)], int(r.candidate_id)] for r in dynamic.itertuples()])
        dynamic["ensemble_disagreement"] = uncertainty_selected
        dynamic["leverage"] = np.clip(meta["uncertainty_train_median"] / np.maximum(uncertainty_selected, 1e-6), .5, 1.)
    risk_execution = ExecutionConfig(entry_expiry_bars=config["entry_expiry_bars"], max_holding_bars=max(config["holding_days"]) * 288,
                                     leverage=.5, max_leverage=1.)
    risk_result, risk_trades = run_backtest(candles, dynamic, 100, CostModel(**config["costs"]), risk_execution)
    risk_stress, _ = run_backtest(candles, dynamic, 100, CostModel(**dict(config["costs"], fee_rate_per_fill=.00055)), risk_execution)
    risk_report = {**report, "result": asdict(risk_result), "fee_stress": asdict(risk_stress), "bootstrap": trade_bootstrap(risk_trades),
                   "policy": "predeclared_train_disagreement_exposure_reduction_0.5_to_1x",
                   "warning": "Disagreement is not calibrated win probability. This is a secondary comparison; default remains fixed1x."}
    for name, value in (("report", report), ("risk_overlay_report", risk_report)):
        (a.output / f"{name}.json").write_text(json.dumps(value, indent=2))
    signals.to_parquet(a.output / "signals.parquet", index=False)
    dynamic.to_parquet(a.output / "risk_overlay_signals.parquet", index=False)
    trades_frame.to_csv(a.output / "trades.csv", index=False)
    pd.DataFrame([asdict(t) for t in risk_trades]).to_csv(a.output / "risk_overlay_trades.csv", index=False)
    decisions.to_parquet(a.output / "decisions.parquet", index=False)
    np.save(a.output / "predictions.npy", prediction)
    provenance["state"] = "opened_complete_do_not_tune"
    (a.output / "evaluation_manifest.json").write_text(json.dumps(provenance, indent=2))
    print(json.dumps({"fixed_1x": report, "reduced_exposure": risk_report}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--interval", choices=["first_holdout", "reserve_holdout"], default="first_holdout")
    p.add_argument("--source", type=Path, default=Path("data/processed/btc_3y_20260905_v1"))
    run(p.parse_args())
