import torch
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from safetensors.torch import save_file,load_file
from agentic_alpha_lab.models import temporal_value
from agentic_alpha_lab.models.macro_micro_value import objective
from agentic_alpha_lab.data.training import sha256
from walkforward_action_model import run


def main(a):
    torch.set_num_threads(2)
    plan=json.loads(a.plan.read_text())
    family=plan.get("model_family","gru")
    if family=="transformer":
        from agentic_alpha_lab.models import transformer_value as architecture
    elif family=="gru":
        architecture=temporal_value
    else:
        raise ValueError("Unknown temporal model family")
    parent=json.loads(Path(plan["parent_plan"]).read_text())
    dataset,cache=Path(plan["dataset"]),Path(plan["cache"])
    meta=json.loads((cache/"manifest.json").read_text())
    if meta["state"]!="complete" or meta["dataset_manifest_sha256"]!=sha256(dataset/"manifest.json"):
        raise ValueError("Sequence cache/data identity mismatch")
    for name,digest in meta["files"].items():
        if sha256(cache/name)!=digest:
            raise ValueError("Sequence cache hash mismatch")
    clock=pd.read_parquet(cache/"decisions.parquet")
    decisions=pd.read_parquet(dataset/"decisions.parquet")
    if not pd.DatetimeIndex(clock.signal_time).equals(pd.DatetimeIndex(decisions.signal_time)):
        raise ValueError("Sequence cache row misalignment")
    sequence=np.load(cache/"sequences.npy",allow_pickle=False)
    if sequence.shape!=(len(decisions),5,128,6) or not np.isfinite(sequence).all():
        raise ValueError("Invalid sequences")
    if a.output.exists():
        raise FileExistsError("Choose new immutable experiment")
    a.output.mkdir(parents=True)
    (a.output/"plan.json").write_text(json.dumps(plan,indent=2))
    (a.output/"driver_source.py").write_text(Path(__file__).read_text())
    (a.output/"model_source.py").write_text(Path(architecture.__file__).read_text())
    device="cuda" if torch.cuda.is_available() else "cpu"
    settings=plan["training"]
    reports={}
    for seed in plan["seeds"]:
        def provider(features,labels,train,test,candidates,output,fold):
            torch.manual_seed(seed)
            model=architecture.TemporalValue(candidates,**plan["network"])
            model.feature_mean.copy_(torch.tensor(features[train].mean(0),dtype=torch.float32))
            model.feature_scale.copy_(torch.tensor(np.maximum(features[train].std(0),1e-6),dtype=torch.float32))
            model.to(device)
            xs=torch.tensor(sequence[train],device=device)
            xf=torch.tensor(features[train],device=device)
            ys=torch.tensor(labels[train],device=device)
            optimizer=torch.optim.AdamW(model.parameters(),lr=settings["learning_rate"],weight_decay=settings["weight_decay"])
            history=[]
            for epoch in range(settings["epochs"]):
                model.train()
                order=torch.randperm(len(xs),device=device)
                total=0.
                for start in range(0,len(order),settings["batch_size"]):
                    idx=order[start:start+settings["batch_size"]]
                    optimizer.zero_grad(set_to_none=True)
                    score,aux=model(xs[idx],xf[idx])
                    loss=objective(score,aux,ys[idx])
                    if not torch.isfinite(loss):
                        raise ValueError("Nonfinite temporal loss")
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(),settings["gradient_clip"])
                    optimizer.step()
                    total+=float(loss.detach())*len(idx)
                history.append(total/len(xs))
                if (epoch+1)%4==0:
                    print(json.dumps({"seed":seed,"fold":fold,"epoch":epoch+1,"train_loss":history[-1]}),flush=True)
            forecast=temporal_value.predict(model,sequence[test],features[test])
            target=output/"checkpoints"/f"fold_{fold}"
            target.mkdir(parents=True)
            save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(target/"model.safetensors"))
            # Exact same architecture/normalization loaded from saved weights; replay on CPU.
            restored=architecture.TemporalValue(candidates,**plan["network"])
            restored.load_state_dict(load_file(str(target/"model.safetensors")))
            replay=temporal_value.predict(restored,sequence[test][:8],features[test][:8])
            np.testing.assert_allclose(replay,forecast[:8],rtol=1e-3,atol=1e-3)
            np.savez_compressed(target/"replay.npz",sequences=sequence[test][:8],features=features[test][:8],predictions=forecast[:8])
            details={"seed":seed,"fold":fold,"train_decisions":int(train.sum()),"parameters":sum(p.numel() for p in model.parameters()),
                     "network":plan["network"],"training":settings,"training_loss":history,"device":device,
                     "torch":torch.__version__,"cache_manifest_sha256":sha256(cache/"manifest.json"),
                     "model_family":family,"model_source_sha256":sha256(Path(architecture.__file__)),"weights_sha256":sha256(target/"model.safetensors"),
                     "cpu_replay_max_error":float(np.max(np.abs(replay-forecast[:8]))),"live_approved":False}
            (target/"metadata.json").write_text(json.dumps(details,indent=2))
            return forecast
        child=dict(parent,experiment=plan["experiment"],branches=["temporal_neural","train_candidate_mean"],temporal_spec=plan)
        child_path=a.output/f"seed{seed}_plan.json"
        child_path.write_text(json.dumps(child,indent=2))
        target=a.output/f"seed{seed}"
        run(SimpleNamespace(plan=child_path,output=target),model_branch="temporal_neural",implementation_path=Path(architecture.__file__),fold_provider=provider)
        reports[str(seed)]=json.loads((target/"summary.json").read_text())
    result={"plan":plan,"reports":reports,"all_seeds_pass":all(r["advance_to_further_research"] for r in reports.values()),"live_approved":False}
    (a.output/"summary.json").write_text(json.dumps(result,indent=2))
    print(json.dumps({"all_seeds_pass":result["all_seeds_pass"]}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,default=Path("configs/swing_v13_temporal.json"))
    p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())
