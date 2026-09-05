"""Acquire an earlier BTC futures cycle, preserve original immutable snapshot."""
import torch
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import pandas as pd
from agentic_alpha_lab.data.binance_usdm import fetch_klines, validate_klines
from agentic_alpha_lab.data.training import sha256, validate_source


def run(a):
    if a.output.exists():
        raise FileExistsError("Choose a new immutable source folder")
    original = json.loads((a.source / "manifest.json").read_text())
    if sha256(a.source / "candles.parquet") != original["files"]["candles.parquet"]:
        raise ValueError("Original snapshot changed")
    old = pd.read_parquet(a.source / "candles.parquet")
    first = pd.Timestamp(old.open_time.iloc[0])
    print(f"Fetch earlier BTC futures from {a.start} to {first}", flush=True)
    earlier = fetch_klines("BTCUSDT", "5m", pd.Timestamp(a.start).to_pydatetime(), first.to_pydatetime())
    earlier = earlier.loc[earlier.open_time < first]
    combined = pd.concat([earlier, old], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    quality = validate_klines(combined, "5m")
    a.output.mkdir(parents=True)
    # Keep raw evidence even if continuity checks fail; downstream must not fill gaps silently.
    combined.to_parquet(a.output / "candles.parquet", index=False)
    validation_error = None
    try:
        validate_source(combined)
    except ValueError as exc:
        validation_error = str(exc)
    manifest = {"schema": "btc-extended-source-v1", "parent_manifest_sha256": sha256(a.source / "manifest.json"),
                "created_at": datetime.now(timezone.utc).isoformat(), "source": "Binance USD-M BTCUSDT 5m",
                "quality": quality.__dict__, "validation_error": validation_error,
                "files": {"candles.parquet": sha256(a.output / "candles.parquet")},
                "note": "Later candles preserved byte-value equivalent from prior snapshot, not fetched again. New earlier history only."}
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    if validation_error:
        raise ValueError(validation_error)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=Path("data/processed/btc_3y_20260905_v1"))
    p.add_argument("--start", default="2022-01-01T00:00:00Z")
    p.add_argument("--output", type=Path, required=True)
    run(p.parse_args())
