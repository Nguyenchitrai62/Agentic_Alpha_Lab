from __future__ import annotations

import argparse
import copy
import json
import random
import subprocess
from pathlib import Path

import torch
import numpy as np
from safetensors.torch import save_file
from sklearn.linear_model import LogisticRegression

from agentic_alpha_lab.data.training import verified_split, sha256
from agentic_alpha_lab.models.supervised import MultiHorizonMLP, objective, probabilities, classification_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train MLP + logistic reference without loading test")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--epochs", type=int, help="Explicit smoke override recorded in checkpoint")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a new checkpoint directory")
    manifest = json.loads((args.dataset / "manifest.json").read_text(encoding="utf-8"))
    config = copy.deepcopy(manifest["config"])
    if args.epochs is not None:
        config["model"]["epochs"] = args.epochs
    seed = config["seed"]
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    horizons, features = config["horizons"], manifest["features"]
    frames = {name: verified_split(args.dataset, name, manifest) for name in ("train", "validation", "calibration")}
    mean = frames["train"][features].to_numpy(float).mean(axis=0)
    scale = frames["train"][features].to_numpy(float).std(axis=0)
    scale = np.maximum(scale, 1e-8)
    arrays = {}
    for name, frame in frames.items():
        arrays[name] = (np.clip((frame[features].to_numpy(float) - mean) / scale, -10, 10).astype("float32"),
                        frame[[f"y_direction_{h}" for h in horizons]].to_numpy("int64"),
                        frame[[f"y_return_{h}" for h in horizons]].to_numpy("float32") * 100)
    device = torch.device(args.device)
    tensors = {name: tuple(torch.as_tensor(value, device=device) for value in values) for name, values in arrays.items()}
    model = MultiHorizonMLP(len(features), config["model"]["hidden"], len(horizons)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["model"]["learning_rate"], weight_decay=0.01)
    loader = torch.utils.data.DataLoader(torch.utils.data.TensorDataset(*tensors["train"]),
                                        batch_size=config["model"]["batch_size"], shuffle=True)
    best_loss, best_state, bad_epochs, history = float("inf"), None, 0, []
    # FP32 is deliberately the reference. This tiny head does not need mixed precision.
    for epoch in range(config["model"]["epochs"]):
        model.train()
        for x, y, r in loader:
            optimizer.zero_grad(set_to_none=True)
            logits, quantiles = model(x)
            loss = objective(logits, quantiles, y, r)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        model.eval()
        with torch.no_grad():
            x, y, r = tensors["validation"]
            logits, quantiles = model(x)
            validation_loss = float(objective(logits, quantiles, y, r))
        history.append({"epoch": epoch + 1, "validation_loss": validation_loss})
        print(json.dumps(history[-1]), flush=True)
        if validation_loss < best_loss - 1e-6:
            best_loss, best_state, bad_epochs = validation_loss, copy.deepcopy(model.state_dict()), 0
        else:
            bad_epochs += 1
        if bad_epochs >= config["model"]["patience"]:
            break
    if best_state is None:
        raise RuntimeError("Training did not produce a finite checkpoint")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        calibration_logits = model(tensors["calibration"][0])[0].cpu().numpy()
        validation_logits = model(tensors["validation"][0])[0].cpu().numpy()
    temperature = min(np.linspace(0.5, 5.0, 91), key=lambda t: classification_metrics(
        probabilities(calibration_logits, t), arrays["calibration"][1])["nll"])
    references = {}
    x_train, y_train, _ = arrays["train"]
    x_val, y_val, _ = arrays["validation"]
    for i, horizon in enumerate(horizons):
        if len(np.unique(y_train[:, i])) < 2:
            references[str(horizon)] = {"status": "insufficient_classes"}
            continue
        classifier = LogisticRegression(max_iter=1000, random_state=seed).fit(x_train, y_train[:, i])
        probs = np.zeros((len(x_val), 3))
        probs[:, classifier.classes_] = classifier.predict_proba(x_val)
        references[str(horizon)] = {"validation": classification_metrics(probs, y_val[:, i]),
                                   "classes": classifier.classes_.tolist(), "coef": classifier.coef_.tolist(),
                                   "intercept": classifier.intercept_.tolist()}
    args.output.mkdir(parents=True)
    save_file({key: value.detach().cpu().contiguous() for key, value in model.state_dict().items()},
              str(args.output / "model.safetensors"))
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    metadata = {"model_type": "engineered_multiframe_mlp_v1_not_kronos", "config": config,
                "features": features, "mean": mean.tolist(), "scale": scale.tolist(),
                "temperature": float(temperature), "seed": seed, "git_sha": revision.stdout.strip(),
                "device": str(device), "torch_version": torch.__version__, "precision": "float32",
                "source_code_sha256": {str(path.relative_to(Path.cwd())).replace("\\", "/"): sha256(path)
                                       for path in [Path.cwd() / "scripts/train_baseline.py", *sorted((Path.cwd() / "src").rglob("*.py"))]},
                "dataset_manifest_sha256": sha256(args.dataset / "manifest.json"),
                "dataset_files": manifest["files"], "source_range": manifest["source_range"],
                "model_sha256": sha256(args.output / "model.safetensors"),
                "history": history, "logistic_references": references,
                "validation_uncalibrated": classification_metrics(probabilities(validation_logits, 1), arrays["validation"][1]),
                "calibration_fit_metrics_not_test": classification_metrics(probabilities(calibration_logits, temperature), arrays["calibration"][1]),
                "test_opened": False, "policy_selection": "fixed config, not tuned on test",
                "evaluation_status": manifest["evaluation_status"]}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({key: metadata[key] for key in ("model_type", "temperature", "validation_uncalibrated")}, indent=2))


if __name__ == "__main__":
    # Required by deterministic CUDA matrix multiplication, before CUDA initialization.
    import os
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    main()
