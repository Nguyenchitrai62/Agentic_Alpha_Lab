"""Audit individual-seed stability and no-market-feature control in continuous state."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_temporal_continuous import partition_indices
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.swing import swing_signals
from agentic_alpha_lab.backtest.engine import CostModel,ExecutionConfig,run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress,run_stress


def run(a):
    source=a.source/"training"
    summary=json.loads((source/"summary.json").read_text())
    plan=summary["plan"]
    parent=json.loads(Path(plan["parent_plan"]).read_text())
    dataset=Path(plan["dataset"])
    manifest=json.loads((dataset/"manifest.json").read_text())
    for name,digest in manifest["files"].items():
        if sha256(dataset/name)!=digest:
            raise ValueError("Dataset hash mismatch")
    decisions=pd.read_parquet(dataset/"decisions.parquet")
    candles=pd.read_parquet(dataset/"candles.parquet")
    cfg=json.loads((dataset/"config.json").read_text())
    indices=np.concatenate(partition_indices(decisions,parent))
    part=decisions.iloc[indices].reset_index(drop=True)
    if a.output.exists():
        raise FileExistsError("Choose immutable new audit output")
    a.output.mkdir(parents=True)
    specs=[(f"seed{seed}",seed,"temporal_neural") for seed in plan["seeds"]]
    specs.append(("train_candidate_mean",plan["seeds"][0],"train_candidate_mean"))
    results,files={},{}
    for name,seed,branch in specs:
        arrays=[]
        for fold in range(len(parent["folds"])):
            path=source/f"seed{seed}"/branch/f"fold_{fold}"/"predictions.npy"
            files[str(path)]=sha256(path)
            arrays.append(np.load(path,allow_pickle=False))
        prediction=np.concatenate(arrays)
        if prediction.shape!=(len(part),16,6) or not np.isfinite(prediction).all():
            raise ValueError("Invalid prediction alignment")
        signals=swing_signals(prediction,part,cfg)
        for exposure in plan["exposures"]:
            execution=ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],max_holding_bars=max(cfg["holding_days"])*288,leverage=exposure,max_leverage=exposure)
            normal,trades=run_backtest(candles,signals,100,CostModel(**cfg["costs"]),execution)
            fee,_=run_backtest(candles,signals,100,CostModel(**dict(cfg["costs"],fee_rate_per_fill=.00055)),execution)
            stress,stress_trades,diagnostics=run_stress(candles,signals,100,CostModel(**cfg["costs"]),execution,FillStress(5,5,5,.00055,False))
            key=f"{name}_exposure{exposure}"
            pd.DataFrame([asdict(t) for t in trades]).to_csv(a.output/f"{key}_trades.csv",index=False)
            pd.DataFrame([asdict(t) for t in stress_trades]).to_csv(a.output/f"{key}_stress_trades.csv",index=False)
            results[key]={"normal":asdict(normal),"fee_stress":asdict(fee),"execution_stress":asdict(stress),"diagnostics":diagnostics}
            print(json.dumps({"branch":key,**results[key]}),flush=True)
    result={"results":results,"prediction_files":files,"training_summary_sha256":sha256(source/"summary.json"),
        "independent_test":False,"live_approved":False,"note":"Diagnostic controls, not winner-seed selection. Same continuous global policy, all periods opened development. Candidate mean is fitted only on mature past labels and uses no market features."}
    (a.output/"summary.json").write_text(json.dumps(result,indent=2))
    (a.output/"driver_source.py").write_text(Path(__file__).read_text())


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
