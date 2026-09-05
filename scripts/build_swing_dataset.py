import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.training import validate_source, sha256
from agentic_alpha_lab.data.swing import SwingStore, swing_labels, funding_flags
from agentic_alpha_lab.data.decision_clock import decision_indices


def build(a):
    config = json.loads(a.config.read_text())
    source = json.loads((a.source / "manifest.json").read_text())
    if sha256(a.source / "candles.parquet") != source["files"]["candles.parquet"]:
        raise ValueError("Source hash mismatch")
    max_span = max(config["holding_days"]) * 288 + config["entry_expiry_bars"]
    boundaries = [(pd.Timestamp(x), pd.Timestamp(y)) for x, y in config["splits"].values()]
    if any(b[0] - l[1] < pd.Timedelta(minutes=5 * max_span) for l, b in zip(boundaries, boundaries[1:])):
        raise ValueError("Embargo shorter than maximum execution horizon")
    candles = validate_source(pd.read_parquet(a.source / "candles.parquet"))
    candles = candles.loc[candles.close_time < boundaries[-1][1]].reset_index(drop=True)
    store = SwingStore(candles, config)
    ohlc, funding = candles[["open", "high", "low", "close"]].to_numpy(float), funding_flags(candles)
    if a.output.exists():
        raise FileExistsError("Choose a new dataset")
    a.output.mkdir(parents=True)
    counts = {}
    for split, (start, end) in zip(config["splits"], boundaries):
        rows, records = [], []
        for i in decision_indices(candles.close_time, config["stride"], max_span, config.get("decision_anchor_utc")):
            as_of = candles.close_time.iloc[i]
            if not start <= as_of < end or candles.close_time.iloc[i + max_span] >= end:
                continue
            try:
                w, t, ages, features, atr5, atr4 = store.sample(as_of)
            except ValueError as exc:
                if "Insufficient" in str(exc):
                    continue
                raise
            labels = swing_labels(candles, i, atr5, atr4, config, ohlc, funding)
            auxiliary = np.asarray([(candles.close.iloc[i + d * 288] / candles.close.iloc[i] - 1) * 100
                                    for d in (3, 7)], np.float32)
            rows.append((w, t, ages, features, labels, auxiliary))
            records.append({"bar_index": i, "signal_time": as_of, "close": float(candles.close.iloc[i]),
                            "atr5": atr5, "atr4": atr4, "label_end": candles.close_time.iloc[i + max_span]})
            if len(rows) % 200 == 0:
                print(f"{split}: {len(rows)}", flush=True)
            if a.max_rows and len(rows) >= a.max_rows:
                break
        if not rows:
            raise ValueError(f"Empty {split}")
        np.savez_compressed(a.output / f"{split}.npz", **{k: np.stack([r[j] for r in rows])
                            for j, k in enumerate(("windows", "stamps", "ages", "features", "labels", "auxiliary"))})
        pd.DataFrame(records).to_parquet(a.output / f"{split}_decisions.parquet", index=False)
        counts[split] = len(rows)
    candles.to_parquet(a.output / "development_candles.parquet", index=False)
    (a.output / "config.json").write_text(json.dumps(config, indent=2))
    manifest = {"schema": config["schema"], "rows": counts, "smoke_only": bool(a.max_rows), "test_included": False,
                "calibration_included": False, "policy_split_included": True, "max_label_bars": max_span,
                "decision_clock": {"anchor_utc": config.get("decision_anchor_utc"),
                                   "mode": "utc_anchored" if config.get("decision_anchor_utc") else "legacy_source_offset"},
                "source_sha256": source["files"]["candles.parquet"], "source_manifest_sha256": sha256(a.source / "manifest.json"),
                "cutoff": str(boundaries[-1][1]), "files": {p.name: sha256(p) for p in sorted(a.output.iterdir())}}
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=Path("data/processed/btc_3y_20260905_v1"))
    p.add_argument("--config", type=Path, default=Path("configs/kronos_swing.json"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-rows", type=int)
    build(p.parse_args())
