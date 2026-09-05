"""Versioned neural experiment; saves every fold checkpoint and exact normalization."""
import torch
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from safetensors.torch import save_file
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.models import macro_micro_value as neural
from walkforward_action_model import run


def train_fold(x, labels, plan, seed, target):
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    k = labels.shape[1]
    features,candidates = x[::k,:-6],x[:k,-6:]
    if features.shape[1]!=40 or k!=16:
        raise ValueError("Require40 features and16 ordered actions")
    model = neural.MacroMicroValue(candidates,**plan["network"])
    model.feature_mean.copy_(torch.tensor(features.mean(0),dtype=torch.float32))
    model.feature_scale.copy_(torch.tensor(np.maximum(features.std(0),1e-6),dtype=torch.float32))
    inputs,outcomes = torch.as_tensor(features,dtype=torch.float32),torch.as_tensor(labels,dtype=torch.float32)
    settings = plan["training"]
    optimizer = torch.optim.AdamW(model.parameters(),lr=settings["learning_rate"],weight_decay=settings["weight_decay"])
    history=[]
    for epoch in range(settings["epochs"]):
        model.train()
        order = torch.randperm(len(inputs))
        total=0.
        for start in range(0,len(order),settings["batch_size"]):
            index = order[start:start+settings["batch_size"]]
            optimizer.zero_grad(set_to_none=True)
            score,auxiliary = model(inputs[index])
            loss=neural.objective(score,auxiliary,outcomes[index])
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite neural training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),settings["gradient_clip"])
            optimizer.step()
            total+=float(loss.detach())*len(index)
        history.append(total/len(inputs))
    target.mkdir(parents=True)
    save_file(model.state_dict(),str(target/"model.safetensors"))
    np.savez_compressed(target/"replay.npz",features=features[:8],predictions=neural.swing_prediction(model,features[:8],candidates))
    meta={"seed":seed,"train_decisions":len(features),"parameters":sum(p.numel() for p in model.parameters()),
          "network":plan["network"],"training":settings,"train_loss":history,"candidate_grid":candidates.tolist(),
          "input_feature_order":"40 context_features:5m,15m,1h,4h,1d;8features each",
          "model_source_sha256":sha256(Path(neural.__file__)),"weights_sha256":sha256(target/"model.safetensors"),
          "training_inputs_sha256":__import__("hashlib").sha256(features.tobytes()).hexdigest(),
          "normalization":"train-only mean/std buffers in safetensors; no test stats",
          "live_approved":False}
    (target/"metadata.json").write_text(json.dumps(meta,indent=2))
    print(json.dumps({"checkpoint":str(target),"parameters":meta["parameters"],"first_loss":history[0],"last_loss":history[-1]}),flush=True)
    return model


def main(a):
    plan=json.loads(a.plan.read_text())
    parent=json.loads(Path(plan["parent_plan"]).read_text())
    if a.output.exists():
        raise FileExistsError("Choose new immutable experiment")
    a.output.mkdir(parents=True)
    (a.output/"plan.json").write_text(json.dumps(plan,indent=2))
    (a.output/"driver_source.py").write_text(Path(__file__).read_text())
    (a.output/"model_source.py").write_text(Path(neural.__file__).read_text())
    reports={}
    for seed in plan["seeds"]:
        branch="macro_micro_neural"
        child=dict(parent,experiment=plan["experiment"],branches=[branch,"train_candidate_mean"],neural_spec=plan)
        child_path=a.output/f"seed{seed}_plan.json"
        child_path.write_text(json.dumps(child,indent=2))
        target=a.output/f"seed{seed}"
        counter=[0]
        def fit(x,labels,unused_params):
            fold=counter[0]
            counter[0]+=1
            return train_fold(x,labels,plan,seed,target/"checkpoints"/f"fold_{fold}")
        run(SimpleNamespace(plan=child_path,output=target),fit,neural.swing_prediction,branch,Path(neural.__file__))
        reports[str(seed)]=json.loads((target/"summary.json").read_text())
    result={"plan":plan,"plan_sha256":sha256(a.plan),"reports":reports,
            "all_seeds_pass":all(r["advance_to_further_research"] for r in reports.values()),"live_approved":False}
    (a.output/"summary.json").write_text(json.dumps(result,indent=2))
    print(json.dumps({"all_seeds_pass":result["all_seeds_pass"]}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,default=Path("configs/swing_v11_macro_micro.json"))
    p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())
