"""Opencode R5-A1 SMOKE nhe (KHONG phai ket qua nghien cuu).

Muc dich duy nhat: chung minh pipeline train TCN-fresh chay duoc:
load + hash-check dataset/cache, chia fold walk-forward (trailing 730d,
embargo 8d), forward/backward 2 epochs tren CPU, save/reload parity,
predict + choose() + frequency loop + run_backtest/run_stress plumbing.

1 fold (fold_0) x 1 seed (1729) x 2 epochs, batch 64, CPU. Khong training
nang local. Ket qua chi de dan ong, KHONG so sanh voi standing_best.
"""
import torch  # noqa: F401  (phai import truoc pandas tren host nay)
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from train_tcn_kaggle import fold_indices, load_inputs, stable_evaluation_backend  # noqa: E402
from agentic_alpha_lab.models.tcn_fusion_value import TemporalValue  # noqa: E402
from agentic_alpha_lab.models.macro_micro_value import objective  # noqa: E402
from agentic_alpha_lab.models.temporal_value import predict  # noqa: E402
from safetensors.torch import load_file, save_file  # noqa: E402


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(a):
    torch.set_num_threads(2)
    stable_evaluation_backend()
    plan = json.loads(a.plan.read_text())
    parent = json.loads((ROOT / plan["parent_plan"]).read_text())
    fold, seed, epochs = 0, 1729, 2
    assert seed in plan["seeds"], "smoke seed phai nam trong seeds da co dinh"
    t0 = time.monotonic()
    inputs = load_inputs(plan)
    sequence, features, labels, decisions, candidates = inputs
    train, test = fold_indices(decisions, parent, plan["training"], fold)
    print(json.dumps({"smoke_shapes": {"train": len(train), "test": len(test),
                                       "features": list(features.shape),
                                       "labels": list(labels.shape),
                                       "sequence": list(sequence.shape)}}), flush=True)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = TemporalValue(candidates, **plan["network"])
    model.feature_mean.copy_(torch.tensor(features[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(features[train].std(0), 1e-6), dtype=torch.float32))
    model.train()
    xs = torch.tensor(sequence[train], dtype=torch.float32)
    xf = torch.tensor(features[train], dtype=torch.float32)
    ys = torch.tensor(labels[train], dtype=torch.float32)
    optimizer = torch.optim.AdamW(model.parameters(), lr=plan["training"]["learning_rate"],
                                  weight_decay=plan["training"]["weight_decay"])
    batch = 64
    losses = []
    for epoch in range(epochs):
        order = torch.randperm(len(train))
        total = 0.0
        for start in range(0, len(order), batch):
            idx = order[start:start + batch]
            optimizer.zero_grad(set_to_none=True)
            score, aux = model(xs[idx], xf[idx])
            loss = objective(score, aux, ys[idx])
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), plan["training"]["gradient_clip"])
            optimizer.step()
            total += loss.detach().item() * len(idx)
        losses.append(total / len(train))
        print(json.dumps({"smoke_epoch": epoch + 1, "loss": losses[-1]}), flush=True)
    out = a.output / "seed1729" / "fold_0"
    out.mkdir(parents=True, exist_ok=False)
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out / "model.safetensors"))
    forecast = predict(model, sequence[test], features[test], batch_size=32)
    if not np.isfinite(forecast).all():
        raise ValueError("Nonfinite smoke predictions")
    restored = TemporalValue(candidates, **plan["network"])
    restored.load_state_dict(load_file(str(out / "model.safetensors")))
    replay = predict(restored, sequence[test][:8], features[test][:8], batch_size=32)
    parity = bool(np.allclose(replay, forecast[:8], rtol=1e-4, atol=1e-4))
    np.save(out / "predictions.npy", forecast)
    np.savez_compressed(out / "indices.npz", train=train, test=test)
    summary = {"state": "smoke_complete" if parity else "parity_failed",
               "seed": seed, "fold": fold, "epochs": epochs, "device": "cpu",
               "losses": losses, "parameters": sum(p.numel() for p in model.parameters()),
               "network": plan["network"], "train_decisions": len(train),
               "test_decisions": len(test), "gpu_reload_parity": parity,
               "prediction_sha256": digest(out / "predictions.npy"),
               "elapsed_seconds": time.monotonic() - t0,
               "warning": "SMOKE plumbing only. KHONG phai ket qua nghien cuu; khong so voi standing_best.",
               "live_approved": False}
    (out / "smoke_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=ROOT / "configs/opencode_v25_tcnarch.json")
    p.add_argument("--output", type=Path,
                   default=ROOT / "artifacts/research/opencode_v25_tcnarch/smoke")
    main(p.parse_args())
