from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import torch  # Windows DLL load order
import pandas as pd
import yaml

from agentic_alpha_lab.data.training import validate_source, make_examples, chronological_splits, sha256


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an immutable research dataset (never overwrite)")
    parser.add_argument("--data", type=Path, default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/training.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Choose a new dataset version; output already exists")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    candles = validate_source(pd.read_parquet(args.data))
    examples = make_examples(candles, config)
    splits = chronological_splits(examples, config)
    args.output.mkdir(parents=True)
    candles.to_parquet(args.output / "candles.parquet", index=False)
    shutil.copyfile(args.config, args.output / "training.yaml")
    for name, frame in splits.items():
        frame.to_parquet(args.output / f"{name}.parquet", index=False)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    manifest = {
        "schema_version": 1, "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "git_sha": revision.stdout.strip(), "source_sha256": sha256(args.data),
        "source_range": [candles.open_time.iloc[0].isoformat(), candles.close_time.iloc[-1].isoformat()],
        "features": [column for column in examples if column.startswith("x_")],
        "config": config, "evaluation_status": "exploratory_research_not_pristine_forward_test",
        "warning": "Historical interval may already have been inspected. Short history is pipeline smoke only.",
        "splits": {name: {"rows": len(frame), "start": frame.signal_time.iloc[0].isoformat(),
                           "end": frame.signal_time.iloc[-1].isoformat(),
                           "label_end": frame.label_end.iloc[-1].isoformat()} for name, frame in splits.items()},
        "files": {path.name: sha256(path) for path in sorted(args.output.iterdir()) if path.is_file()},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["splits"], indent=2))


if __name__ == "__main__":
    main()
