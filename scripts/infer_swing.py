"""Research-only swing suggestion. Portfolio cooldown/cap handled by policy layer."""
import torch
import argparse
import json
from pathlib import Path
import pandas as pd
from safetensors.torch import load_file
from agentic_alpha_lab.models.swing import SwingKronos
from agentic_alpha_lab.data.swing import SwingStore, choose
from agentic_alpha_lab.data.training import sha256, validate_source


def infer(a):
    meta = json.loads((a.checkpoint / "metadata.json").read_text())
    if sha256(a.checkpoint / "swing.safetensors") != meta["checkpoint_sha256"]:
        raise ValueError("Checkpoint changed")
    for name, digest in meta["upstream_hashes"].items():
        if sha256(a.upstream / name) != digest:
            raise ValueError(f"Upstream changed: {name}")
    for name, digest in meta["initial_weights"].items():
        if sha256(a.weights / name) != digest:
            raise ValueError(f"Initial weight/config changed: {name}")
    config = meta["config"]
    candles = validate_source(pd.read_parquet(a.candles))
    w, t, ages, features, atr5, atr4 = SwingStore(candles, config).sample(candles.close_time.iloc[-1])
    device = torch.device(a.device or ("cuda:0" if torch.cuda.is_available() else "cpu"))
    model = SwingKronos(a.upstream, a.weights, config).to(device).eval()
    model.load_state_dict(load_file(str(a.checkpoint / "swing.safetensors")))
    with torch.no_grad(), torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
        p, medium = model(*(torch.from_numpy(x[None]).to(device) for x in (w, t, ages, features)))
    return {"as_of": str(candles.close_time.iloc[-1]), "research_only": True,
            "checkpoint_sha256": meta["checkpoint_sha256"], "smoke_checkpoint": meta["runtime"]["smoke"],
            "medium_return_3d_7d_percent": medium[0].float().cpu().tolist(),
            "requires_portfolio_cooldown_and_monthly_cap": True,
            **choose(p[0].float().cpu().numpy(), float(candles.close.iloc[-1]), atr5, atr4, config)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--candles", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    p.add_argument("--device")
    print(json.dumps(infer(p.parse_args()), indent=2))
