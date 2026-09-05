"""Build immutable raw-window training data; never export the locked test."""
from __future__ import annotations
import torch  # Windows DLL load order
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.training import sha256, verified_split, validate_source
from agentic_alpha_lab.data.kronos_trading import WindowStore, atr_series, candidate_labels


def build(source: Path, output: Path, config_path: Path, max_rows: int | None = None):
    if output.exists():
        raise FileExistsError("Use a new dataset version")
    config = json.loads(config_path.read_text())
    manifest = json.loads((source / "manifest.json").read_text())
    if sha256(source / "candles.parquet") != manifest["files"]["candles.parquet"]:
        raise ValueError("Source candle hash mismatch")
    candles = validate_source(pd.read_parquet(source / "candles.parquet"))
    # No test or calibration candles on the training service, including in raw context.
    cutoff = pd.Timestamp(manifest["splits"]["validation"]["label_end"])
    candles = candles.loc[candles.open_time <= cutoff].reset_index(drop=True)
    store, atr = WindowStore(candles, config), atr_series(candles)
    output.mkdir(parents=True)
    counts = {}
    for name in ("train", "validation"):
        split = verified_split(source, name, manifest).iloc[::config["stride"]]
        packed, records = [], []
        for row in split.itertuples():
            index = int(row.bar_index)
            if index + config["holding_bars"] + 1 >= len(candles):
                continue
            label_end = candles.open_time.iloc[index + config["holding_bars"] + 1]
            if label_end > pd.Timestamp(manifest["splits"][name]["label_end"]):
                raise ValueError("Label crossed split boundary")
            try:
                x, stamps, ages = store.at(row.signal_time)
            except ValueError as exc:
                if "Insufficient" in str(exc):
                    continue
                raise
            y = candidate_labels(candles, index, float(atr.iloc[index]), config)
            packed.append((x, stamps, ages, y))
            records.append({"bar_index": index, "signal_time": row.signal_time, "close": float(candles.close.iloc[index]),
                            "atr": float(atr.iloc[index]), "label_end": label_end})
            if len(packed) % 250 == 0:
                print(f"{name}: {len(packed)} windows", flush=True)
            if max_rows and len(packed) >= max_rows:
                break
        if not packed:
            raise ValueError(f"No {name} windows")
        np.savez_compressed(output / f"{name}.npz", **{key: np.stack([r[i] for r in packed])
                           for i, key in enumerate(("windows", "stamps", "ages", "labels"))})
        pd.DataFrame(records).to_parquet(output / f"{name}_decisions.parquet", index=False)
        counts[name] = len(packed)
    candles.to_parquet(output / "development_candles.parquet", index=False)
    (output / "config.json").write_text(json.dumps(config, indent=2))
    meta = {"schema": config["schema"], "source_manifest_sha256": sha256(source / "manifest.json"),
            "source_candles_sha256": sha256(source / "candles.parquet"), "rows": counts,
            "smoke_only": max_rows is not None, "test_included": False, "calibration_included": False,
            "cutoff": str(cutoff), "source_splits": manifest["splits"],
            "engine": "ohlc-v2", "label_units": "net percent at fixed 1x including unfilled=0",
            "files": {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()}}
    (output / "manifest.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/processed/btc_3y_20260905_v1"))
    parser.add_argument("--config", type=Path, default=Path("configs/kronos_trading.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-rows", type=int)
    args = parser.parse_args()
    build(args.source, args.output, args.config, args.max_rows)
