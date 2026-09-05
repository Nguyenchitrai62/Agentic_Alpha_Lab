"""As-of features plus execution labels through development cutoff only."""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.training import sha256, validate_source
from agentic_alpha_lab.data.swing import SwingStore, swing_labels, funding_flags


def build(a):
    config = json.loads(Path("configs/kronos_swing.json").read_text())
    plan = json.loads(Path("configs/regime_research_plan.json").read_text())
    meta = json.loads((a.source / "manifest.json").read_text())
    if sha256(a.source / "candles.parquet") != meta["files"]["candles.parquet"]:
        raise ValueError("Source changed")
    candles = validate_source(pd.read_parquet(a.source / "candles.parquet"))
    candles = candles.loc[candles.close_time < pd.Timestamp(plan["development_cutoff"])].reset_index(drop=True)
    if a.output.exists():
        raise FileExistsError("Choose new research snapshot")
    a.output.mkdir(parents=True)
    store = SwingStore(candles, config)
    ohlc, funding = candles[["open", "high", "low", "close"]].to_numpy(float), funding_flags(candles)
    span = max(config["holding_days"]) * 288 + config["entry_expiry_bars"]
    features, labels, records = [], [], []
    for i in range(0, len(candles) - span, config["stride"]):
        timestamp = candles.close_time.iloc[i]
        try:
            _, _, _, f, atr5, atr4 = store.sample(timestamp)
        except ValueError as exc:
            if "Insufficient" in str(exc):
                continue
            raise
        y = swing_labels(candles, i, atr5, atr4, config, ohlc, funding)
        features.append(f)
        labels.append(y)
        records.append({"bar_index": i, "signal_time": timestamp, "label_end": candles.close_time.iloc[i+span],
                        "close": float(candles.close.iloc[i]), "atr5": atr5, "atr4": atr4})
        if len(features) % 500 == 0:
            print(f"built {len(features)} development examples", flush=True)
    np.savez_compressed(a.output / "examples.npz", features=np.stack(features), labels=np.stack(labels))
    pd.DataFrame(records).to_parquet(a.output / "decisions.parquet", index=False)
    candles.to_parquet(a.output / "candles.parquet", index=False)
    (a.output / "config.json").write_text(json.dumps(config, indent=2))
    (a.output / "plan.json").write_text(json.dumps(plan, indent=2))
    manifest = {"source_sha256": meta["files"]["candles.parquet"], "rows": len(records),
                "first": str(records[0]["signal_time"]), "last": str(records[-1]["signal_time"]),
                "cutoff": plan["development_cutoff"], "reserve_included": False,
                "files": {p.name: sha256(p) for p in sorted(a.output.iterdir())}}
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args())
