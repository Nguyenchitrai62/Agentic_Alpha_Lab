"""v5 model-class adapter for the existing hash/prediction/backtest audit."""
import torch
import argparse
import json
from pathlib import Path
import audit_swing as engine
from agentic_alpha_lab.models.swing_v5 import SwingKronosV5


def audit(a):
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    if meta["config"]["schema"] != "kronos-base-swing-v5":
        raise ValueError("Expected v5 checkpoint")
    engine.SwingKronos = SwingKronosV5
    engine.audit(a)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device")
    audit(p.parse_args())
