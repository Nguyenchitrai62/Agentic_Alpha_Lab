"""Select epochs on nested past-only validation, then refit outer training anew."""
import torch
import argparse
import copy
import json
from pathlib import Path
import numpy as np
from safetensors.torch import save_file
from agentic_alpha_lab.models.tcn_fusion_value import TemporalValue
from agentic_alpha_lab.models.macro_micro_value import objective
from agentic_alpha_lab.models.temporal_validation import nested_split, earliest_best_epoch
from train_tcn_kaggle import load_inputs, run_fold, stable_evaluation_backend, write_json, digest


def validation_loss(model, sequences, features, labels, batch_size=32):
    model.eval()
    total = 0.
    with torch.no_grad():
        for start in range(0, len(features), batch_size):
            score, aux = model(sequences[start:start+batch_size], features[start:start+batch_size])
            total += objective(score, aux, labels[start:start+batch_size]).item() * len(score)
    return total / len(features)


def select_epoch(plan, parent, inputs, output, seed, fold):
    sequence, features, labels, decisions, candidates = inputs
    specification = plan["epoch_selection"]
    split_keys = ("window_days", "validation_days", "embargo_days", "minimum_train", "minimum_validation")
    train, validation, clock = nested_split(decisions, parent["folds"][fold][0],
                                           **{k: specification[k] for k in split_keys})
    target = output / f"seed{seed}/selection/fold_{fold}"
    target.mkdir(parents=True, exist_ok=False)
    torch.manual_seed(seed); np.random.seed(seed)
    model = TemporalValue(candidates, **plan["network"])
    model.feature_mean.copy_(torch.tensor(features[train].mean(0), dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(features[train].std(0), 1e-6), dtype=torch.float32))
    model.cuda()
    xs, xf, ys = [torch.tensor(x[train], dtype=torch.float32, device="cuda") for x in (sequence, features, labels)]
    vs, vf, vy = [torch.tensor(x[validation], dtype=torch.float32, device="cuda") for x in (sequence, features, labels)]
    settings = plan["training"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings["learning_rate"], weight_decay=settings["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=settings["amp"])
    train_losses, validation_losses, scales = [], [], []
    selected, stale = None, 0
    batch = settings["batch_size"]
    effective = batch * settings["accumulation_steps"]
    for epoch in range(settings["epochs"]):
        model.train()
        order = torch.randperm(len(train), device="cuda")
        total = 0.
        for left in range(0, len(order), effective):
            group = order[left:left+effective]
            optimizer.zero_grad(set_to_none=True)
            for start in range(0, len(group), batch):
                ix = group[start:start+batch]
                with torch.autocast("cuda", dtype=torch.float16, enabled=settings["amp"]):
                    score, aux = model(xs[ix], xf[ix])
                loss = objective(score.float(), aux.float(), ys[ix])
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite selection training loss")
                scaler.scale(loss * (len(ix) / len(group))).backward()
                total += loss.detach().item() * len(ix)
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), settings["gradient_clip"])
            scaler.step(optimizer); scaler.update()
        train_losses.append(total / len(train))
        validation_losses.append(validation_loss(model, vs, vf, vy))
        scales.append(float(scaler.get_scale()))
        best = earliest_best_epoch(validation_losses, specification["minimum_improvement"])
        if best != selected:
            selected, stale = best, 0
            save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}, str(target / "selected.safetensors"))
        else:
            stale += 1
        print(json.dumps({"stage": "inner_selection", "seed": seed, "fold": fold, "epoch": epoch+1,
                          "train_loss": train_losses[-1], "validation_loss": validation_losses[-1], "selected_epoch": selected}), flush=True)
        if stale >= specification["patience"]:
            break
    means = ys.mean(0)
    constant = torch.stack((means[:, 0], torch.logit(means[:, 1].clamp(1e-6, 1-1e-6))), -1)[None].expand(len(validation), -1, -1)
    aux = (means[:8, 0].mean() - means[8:, 0].mean()).expand(len(validation))
    baseline = objective(constant, aux, vy).item()
    record = {"seed": seed, "fold": fold, "selected_epoch": selected, "selection_spec": specification,
              "training_losses": train_losses, "validation_losses": validation_losses, "amp_scales": scales,
              "constant_validation_objective": baseline, "selected_validation_objective": validation_losses[selected-1],
              "beats_constant_validation": validation_losses[selected-1] < baseline,
              "clock": clock, "selection_weights_sha256": digest(target / "selected.safetensors"),
              "rule": "Earliest validation-loss improvement; no outer labels or PnL. Final refit resets seed and trains all matured outer rows for selected epochs. Constant comparison diagnostic only, no posthoc gating.",
              "live_approved": False}
    np.savez_compressed(target / "indices.npz", train=train, validation=validation)
    write_json(target / "selection.json", record)
    return selected


def main(a):
    torch.set_num_threads(2); stable_evaluation_backend()
    if torch.cuda.device_count() != 1 or "T4" not in torch.cuda.get_device_name():
        raise RuntimeError("One visible T4 per worker required; no heavy local fallback")
    plan = json.loads(a.plan.read_text()); parent = json.loads(Path(plan["parent_plan"]).read_text())
    inputs = load_inputs(plan)
    jobs = [(seed, fold) for fold in range(len(parent["folds"])) for seed in plan["seeds"]]
    for i, (seed, fold) in enumerate(jobs):
        if i % a.shards != a.shard:
            continue
        epoch = select_epoch(plan, parent, inputs, a.output, seed, fold)
        refit = copy.deepcopy(plan); refit["training"]["epochs"] = epoch
        torch.cuda.empty_cache()
        run_fold(refit, parent, inputs, a.output, seed, fold)
        target = a.output / f"seed{seed}/checkpoints/fold_{fold}/metadata.json"
        meta = json.loads(target.read_text())
        meta["selection_record_sha256"] = digest(a.output / f"seed{seed}/selection/fold_{fold}/selection.json")
        meta["epoch_selection"] = plan["epoch_selection"]
        write_json(target, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, default=2)
    main(p.parse_args())
