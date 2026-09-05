"""Load trained Kronos-fusion pipeline and return a research-only bracket suggestion."""
import torch
import argparse
import json
from pathlib import Path
import pandas as pd
from safetensors.torch import load_file
from agentic_alpha_lab.models.kronos_trading import KronosWindowEncoder, BracketFusion
from agentic_alpha_lab.data.kronos_trading import WindowStore, atr_series, decode_suggestion
from agentic_alpha_lab.data.training import sha256, validate_source


def infer(args):
    metadata = json.loads((args.checkpoint / "metadata.json").read_text())
    if sha256(args.checkpoint / "fusion.safetensors") != metadata["checkpoint_sha256"]:
        raise ValueError("Checkpoint hash mismatch")
    for name, digest in metadata["pretrained_weights"].items():
        if sha256(args.weights / name) != digest:
            raise ValueError(f"Pretrained weight changed: {name}")
    for name, digest in metadata["upstream_hashes"].items():
        if sha256(args.upstream / name) != digest:
            raise ValueError(f"Upstream implementation changed: {name}")
    config = metadata["config"]
    candles = validate_source(pd.read_parquet(args.candles))
    as_of = candles.close_time.iloc[-1]
    x, stamps, ages = WindowStore(candles, config).at(as_of)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    encoder = KronosWindowEncoder(args.upstream, args.weights).to(device).eval()
    fusion = BracketFusion(metadata["encoder_width"], config).to(device).eval()
    fusion.load_state_dict(load_file(str(args.checkpoint / "fusion.safetensors")))
    with torch.no_grad():
        embedding = encoder(torch.from_numpy(x[None]).to(device), torch.from_numpy(stamps[None]).to(device))
        prediction = fusion(embedding, torch.from_numpy(ages[None]).to(device))[0].cpu().numpy()
    return {"as_of": str(as_of), "symbol": "BTCUSDT", "timeframes": config["timeframes"],
            "research_only": True, "checkpoint_sha256": metadata["checkpoint_sha256"],
            **decode_suggestion(prediction, float(candles.close.iloc[-1]), float(atr_series(candles).iloc[-1]), config)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--candles", type=Path, required=True)
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    print(json.dumps(infer(p.parse_args()), indent=2))
