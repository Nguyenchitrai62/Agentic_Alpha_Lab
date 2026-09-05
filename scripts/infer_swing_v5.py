"""Read-only v5 candidate inference; portfolio management is not an order service."""
import torch
import argparse
import json
from pathlib import Path
import infer_swing as engine
from agentic_alpha_lab.models.swing_v5 import SwingKronosV5
from agentic_alpha_lab.data.training import sha256


def infer(a):
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    if meta["config"]["schema"] != "kronos-base-swing-v5":
        raise ValueError("Expected v5 checkpoint")
    root = Path(__file__).resolve().parents[1]
    for name, digest in meta["source_hashes"].items():
        if sha256(root / name) != digest:
            raise ValueError(f"Frozen source mismatch: {name}")
    engine.SwingKronos = SwingKronosV5
    value = engine.infer(a)
    return {**value, "candidate_only": True, "probabilities_calibrated": False,
            "note": "Offline candidate only. Apply the frozen decision clock, freshness, pending-order/position state, cooldown and monthly cap before paper use. No orders sent."}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--candles", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device")
    print(json.dumps(infer(p.parse_args()), indent=2))
