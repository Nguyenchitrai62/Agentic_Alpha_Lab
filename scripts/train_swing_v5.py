"""Versioned v5 driver reusing audited DDP mechanics without editing the v2 file."""
import torch
import argparse
from functools import partial
import json
import os
from pathlib import Path
import train_swing as engine
from agentic_alpha_lab.models.swing_v5 import SwingKronosV5, swing_v5_loss
from agentic_alpha_lab.data.training import sha256


def train(a):
    cfg = json.loads((a.dataset / "config.json").read_text())
    if cfg["schema"] != "kronos-base-swing-v5":
        raise ValueError("v5 driver requires an explicitly versioned v5 dataset")
    if set(cfg["loss"]) != {"return_scale_percent", "ranking_weight"}:
        raise ValueError("Unexpected loss parameters")
    # Scoped to this dedicated driver process; original trainer file stays immutable.
    engine.SwingKronos = SwingKronosV5
    engine.swing_loss = partial(swing_v5_loss, **cfg["loss"])
    engine.train(a)
    if int(os.getenv("RANK", 0)) == 0:
        path = a.output / "metadata.json"
        meta = json.loads(path.read_text())
        root = Path(__file__).resolve().parents[1]
        meta["source_hashes"][Path(__file__).relative_to(root).as_posix()] = sha256(Path(__file__))
        meta["training_driver"] = "scripts/train_swing_v5.py"
        meta["loss_name"] = "swing_v5_loss"
        meta["loss_parameters"] = cfg["loss"]
        meta["inference_class"] = "agentic_alpha_lab.models.swing_v5.SwingKronosV5"
        meta["warning"] = "Use the v5 model class for replay; v2 inference class is incompatible. Development only."
        path.write_text(json.dumps(meta, indent=2))
        print("V5_DRIVER_METADATA_COMPLETE", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device")
    p.add_argument("--require-two-t4", action="store_true")
    p.add_argument("--smoke", action="store_true")
    train(p.parse_args())
