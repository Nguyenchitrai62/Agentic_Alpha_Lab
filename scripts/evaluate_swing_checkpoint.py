"""One-shot historical holdout evaluation of a frozen swing checkpoint/policy.

Require an explicit date interval and a fresh output directory. Opening a test
interval changes its research status; never subsequently tune on its result.
"""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from safetensors.torch import load_file
from agentic_alpha_lab.models.swing import SwingKronos
from agentic_alpha_lab.data.swing import SwingStore
from agentic_alpha_lab.data.training import validate_source, sha256
from agentic_alpha_lab.backtest.swing import evaluate


def run(a):
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    if meta["runtime"]["smoke"]:
        raise ValueError("Do not spend the holdout on a smoke model")
    if sha256(a.checkpoint / "swing.safetensors") != meta["checkpoint_sha256"]:
        raise ValueError("Checkpoint hash mismatch")
    for root, hashes in ((a.upstream, meta["upstream_hashes"]), (a.weights, meta["initial_weights"]),
                          (Path(__file__).resolve().parents[1], meta["source_hashes"])):
        for name, digest in hashes.items():
            if sha256(root / name) != digest:
                raise ValueError(f"Implementation changed: {name}")
    config = meta["config"]
    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Use explicit timezone-aware start < end")
    minimum_start = pd.Timestamp(config["splits"]["policy"][1]) + pd.Timedelta(days=8)
    if start < minimum_start:
        raise ValueError("Holdout overlaps development or its embargo")
    source_meta = json.loads((a.source / "manifest.json").read_text())
    if sha256(a.source / "candles.parquet") != source_meta["files"]["candles.parquet"]:
        raise ValueError("Candle snapshot changed")
    if a.output.exists():
        raise FileExistsError("Do not overwrite an opened evaluation")
    a.output.mkdir(parents=True)
    provenance = {"checkpoint_sha256": meta["checkpoint_sha256"], "config": config, "start": str(start), "end": str(end),
                  "source_sha256": source_meta["files"]["candles.parquet"], "evaluator_sha256": sha256(Path(__file__)),
                  "status": "holdout_opening", "warning": "Historical holdout, unknown pretraining overlap. No tuning on this result."}
    (a.output / "evaluation_manifest.json").write_text(json.dumps(provenance, indent=2))
    candles = validate_source(pd.read_parquet(a.source / "candles.parquet"))
    candles = candles.loc[candles.close_time < end].reset_index(drop=True)
    store = SwingStore(candles, config)
    device = torch.device(a.device or ("cuda:0" if torch.cuda.is_available() else "cpu"))
    model = SwingKronos(a.upstream, a.weights, config).to(device).eval()
    model.load_state_dict(load_file(str(a.checkpoint / "swing.safetensors")))
    span = max(config["holding_days"]) * 288 + config["entry_expiry_bars"]
    predictions, records = [], []
    with torch.no_grad():
        for i in range(0, len(candles) - span, config["stride"]):
            as_of = candles.close_time.iloc[i]
            if as_of < start:
                continue
            w, t, ages, features, atr5, atr4 = store.sample(as_of)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
                p, _ = model(*(torch.from_numpy(x[None]).to(device) for x in (w, t, ages, features)))
            predictions.append(p[0].float().cpu().numpy())
            records.append({"bar_index": i, "signal_time": as_of, "close": float(candles.close.iloc[i]), "atr5": atr5, "atr4": atr4})
            if len(predictions) % 100 == 0:
                print(f"holdout inference {len(predictions)}", flush=True)
    if not predictions:
        raise ValueError("No eligible full-horizon decisions")
    predictions, decisions = np.stack(predictions), pd.DataFrame(records)
    report, signals, trades = evaluate(predictions, decisions, candles, config, "historical_holdout_no_tuning")
    np.save(a.output / "predictions.npy", predictions)
    decisions.to_parquet(a.output / "decisions.parquet", index=False)
    signals.to_parquet(a.output / "signals.parquet", index=False)
    trades.to_csv(a.output / "trades.csv", index=False)
    (a.output / "report.json").write_text(json.dumps(report, indent=2))
    provenance["status"] = "opened_complete_do_not_tune"
    (a.output / "evaluation_manifest.json").write_text(json.dumps(provenance, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source", type=Path, default=Path("data/processed/btc_3y_20260905_v1"))
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device")
    run(p.parse_args())
