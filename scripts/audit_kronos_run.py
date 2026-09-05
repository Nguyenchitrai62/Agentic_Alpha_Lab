"""Verify a downloaded run against local hashes and replay validation samples.

No threshold tuning, test reads or live actions. Adds a train-fitted constant
predictor as a diagnostic, not a new selected strategy.
"""
import torch
import argparse
import json
from pathlib import Path
import numpy as np
from safetensors.torch import load_file
from agentic_alpha_lab.models.kronos_trading import KronosWindowEncoder, BracketFusion, trading_loss
from agentic_alpha_lab.data.training import sha256


def audit(args):
    meta = json.loads((args.checkpoint / "metadata.json").read_text())
    manifest = json.loads((args.dataset / "manifest.json").read_text())
    assert sha256(args.checkpoint / "fusion.safetensors") == meta["checkpoint_sha256"]
    assert sha256(args.dataset / "manifest.json") == meta["dataset_manifest_sha256"]
    for name, digest in manifest["files"].items():
        assert sha256(args.dataset / name) == digest, name
    for name, digest in meta["pretrained_weights"].items():
        assert sha256(args.weights / name) == digest, name
    for name, digest in meta["upstream_hashes"].items():
        assert sha256(args.upstream / name) == digest, name
    root = Path(__file__).resolve().parents[1]
    for name, digest in meta["source_hashes"].items():
        assert sha256(root / name) == digest, name
    with np.load(args.dataset / "train.npz", allow_pickle=False) as data:
        train_labels = data["labels"]
    with np.load(args.dataset / "validation.npz", allow_pickle=False) as data:
        validation = {k: data[k] for k in data.files}
    predictions = np.load(args.checkpoint / "validation_predictions.npy", allow_pickle=False)
    indices = np.linspace(0, len(predictions) - 1, 16, dtype=int)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    encoder = KronosWindowEncoder(args.upstream, args.weights).to(device).eval()
    fusion = BracketFusion(meta["encoder_width"], meta["config"]).to(device).eval()
    fusion.load_state_dict(load_file(str(args.checkpoint / "fusion.safetensors")))
    with torch.no_grad():
        embedding = encoder(torch.from_numpy(validation["windows"][indices]).to(device),
                            torch.from_numpy(validation["stamps"][indices]).to(device))
        replay = fusion(embedding, torch.from_numpy(validation["ages"][indices]).to(device)).cpu().numpy()
    error = float(np.abs(replay - predictions[indices]).max())
    if error > 0.001:
        raise ValueError(f"Cross-runtime prediction mismatch: {error}")
    constant = np.zeros_like(predictions)
    constant[..., 0] = train_labels[..., 0].mean(0)
    constant[..., 1:4] = np.quantile(train_labels[..., 0], [0.1, 0.5, 0.9], axis=0).T
    rates = np.clip(train_labels[..., 1:3].mean(0), 1e-6, 1 - 1e-6)
    constant[..., 4:6] = np.log(rates / (1 - rates))
    win = 1 / (1 + np.exp(-predictions[..., 5]))
    minimum_net = meta["config"]["minimum_net_bps"] / 100
    minimum_win = meta["config"]["minimum_win_score"]
    report = {"hashes_verified": True, "replayed_validation_samples": len(indices),
              "max_absolute_prediction_difference": error, "test_read": False,
              "constant_train_fitted_validation_loss": float(trading_loss(torch.from_numpy(constant),
                                                        torch.from_numpy(validation["labels"]))),
              "fusion_validation_loss": float(trading_loss(torch.from_numpy(predictions),
                                              torch.from_numpy(validation["labels"]))),
              "predicted_net_bps_range": [float(predictions[..., 0].min() * 100), float(predictions[..., 0].max() * 100)],
              "positive_net_score_range": [float(win.min()), float(win.max())],
              "candidate_count_net_gate": int((predictions[..., 0] > minimum_net).sum()),
              "candidate_count_win_gate": int((win >= minimum_win).sum()),
              "candidate_count_both_gates": int(((predictions[..., 0] > minimum_net) & (win >= minimum_win)).sum()),
              "warning": "Positive-net score is unconditional, including non-fills; not calibrated win rate given fill.",
              "train_net_percent_by_candidate": train_labels[..., 0].mean(0).tolist(),
              "validation_net_percent_by_candidate": validation["labels"][..., 0].mean(0).tolist()}
    if args.output.exists():
        raise FileExistsError("Choose a new audit output")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--upstream", type=Path, default=Path("../Kronos"))
    p.add_argument("--weights", type=Path, default=Path("artifacts/models"))
    audit(p.parse_args())
