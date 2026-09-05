"""Audit calibration with explicit label maturity and one continuous trading state."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research_temporal_continuous import partition_indices,require_tcn_audit
from agentic_alpha_lab.models.ensemble_value import combine
from agentic_alpha_lab.models import causal_calibration
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest.swing import swing_signals
from agentic_alpha_lab.backtest.engine import CostModel,ExecutionConfig,run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress,run_stress


def run(a):
    plan=json.loads(a.plan.read_text()); source=Path(plan["source"]); ds=Path(plan["dataset"])
    original=json.loads((source/"summary.json").read_text())
    require_tcn_audit(original.get("plan",{}),source,plan.get("replay_audit"))
    if plan.get("embargo_days",8)!=8:
        raise ValueError("Current calibrator implements exactly8day label embargo")
    if any(not 0<exposure<=1 for exposure in plan["exposures"]):
        raise ValueError("Unvalidated leverage is forbidden in this calibration experiment")
    parent=json.loads(Path(plan["parent_plan"]).read_text())
    manifest=json.loads((ds/"manifest.json").read_text())
    for name,digest in manifest["files"].items():
        if sha256(ds/name)!=digest: raise ValueError("Changed dataset")
    decisions=pd.read_parquet(ds/"decisions.parquet"); candles=pd.read_parquet(ds/"candles.parquet")
    cfg=json.loads((ds/"config.json").read_text())
    with np.load(ds/"examples.npz",allow_pickle=False) as values: labels=values["labels"]
    parts=partition_indices(decisions,parent); indices=np.concatenate(parts)
    part=decisions.iloc[indices].reset_index(drop=True); forecasts=[]; provenance={}
    for fold,selected in enumerate(parts):
        batch=[]
        for seed in plan["seeds"]:
            report=original["reports"][str(seed)]
            if report["dataset_manifest_sha256"]!=sha256(ds/"manifest.json") or report["plan"]["folds"]!=parent["folds"]:
                raise ValueError("Forecast/data/fold mismatch")
            path=source/f"seed{seed}"/"temporal_neural"/f"fold_{fold}"/"predictions.npy"
            p=np.load(path,allow_pickle=False)
            if p.shape!=(len(selected),16,6) or not np.isfinite(p).all(): raise ValueError("Invalid forecasts")
            provenance[str(path)]=sha256(path); batch.append(p)
        forecasts.append(np.stack(batch))
    raw=np.concatenate(forecasts,axis=1); base,details=combine(raw,plan["penalty"])
    score=details["selection_score_percent"]; fill=details["mean_fill_score"]
    if a.output.exists(): raise FileExistsError("Immutable experiment exists")
    a.output.mkdir(parents=True)
    (a.output/"plan.json").write_text(json.dumps(plan,indent=2))
    (a.output/"driver_source.py").write_text(Path(__file__).read_text())
    (a.output/"calibration_source.py").write_text(Path(causal_calibration.__file__).read_text())
    duration=(pd.Timestamp(parent["complete_evaluation_until"])-pd.Timestamp(parent["folds"][0][0])).total_seconds()/(365.2425*86400)
    results={}; mappings={}
    for window in [None]+plan["windows_previous_quarters"]:
        name="identity" if window is None else f"isotonic_{window or 'all'}"
        output=base.copy(); mapping=[]
        if window is not None:
            offset=0
            for fold,selected in enumerate(parts):
                first=0 if window==0 else max(0,fold-window)
                asof=parent["folds"][fold][0]; left=parent["folds"][first][0]
                current=slice(offset,offset+len(selected))
                mapped,record,mask=causal_calibration.calibrate(score,labels[indices,...,0],part,asof,left,score[current])
                output[current,...,0]=mapped/fill[current]
                record.update(fold=fold,eligible_dataset_indices=indices[mask].tolist())
                mapping.append(record); offset+=len(selected)
        signals=swing_signals(output,part,cfg)
        target=a.output/name; target.mkdir()
        signals.to_parquet(target/"signals.parquet",index=False)
        np.savez_compressed(target/"predictions.npz",prediction=output,decision_indices=indices)
        (target/"calibrators.json").write_text(json.dumps(mapping,indent=2)); mappings[name]=mapping
        for exposure in plan["exposures"]:
            execution=ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],max_holding_bars=max(cfg["holding_days"])*288,leverage=exposure,max_leverage=exposure)
            normal,trades=run_backtest(candles,signals,100,CostModel(**cfg["costs"]),execution)
            fee,ft=run_backtest(candles,signals,100,CostModel(**dict(cfg["costs"],fee_rate_per_fill=.00055)),execution)
            stress,st,diagnostic=run_stress(candles,signals,100,CostModel(**cfg["costs"]),execution,FillStress(5,5,5,.00055,False))
            scenarios={}
            for label,result,items in (("normal",normal,trades),("fee_stress",fee,ft),("execution_stress",stress,st)):
                ratio=result.final_equity/100
                scenarios[label]={**asdict(result),"annual_geometric_net":ratio**(1/duration)-1,
                                  "monthly_geometric_net":ratio**(1/(12*duration))-1}
                pd.DataFrame([asdict(t) for t in items]).to_csv(target/f"exposure{exposure}_{label}_trades.csv",index=False)
            counts=signals.signal_time.dt.strftime("%Y-%m").value_counts() if len(signals) else {}
            months=pd.period_range(pd.Timestamp(parent["folds"][0][0]).tz_localize(None),pd.Timestamp(parent["complete_evaluation_until"]).tz_localize(None),freq="M")
            report={"scenarios":scenarios,"signals":len(signals),"months":{str(m):int(counts.get(str(m),0)) for m in months},
                    "execution_diagnostics":diagnostic,"duration_years":duration,
                    "meets_user_target_in_all_scenarios":all(r["monthly_geometric_net"]>=.05 and r["max_drawdown"]>=-.2 and r["trades"]>=30 for r in scenarios.values())}
            results[f"{name}_{exposure}"]=report
            print(json.dumps({"branch":name,"exposure":exposure,"signals":len(signals),"metrics":{s:{k:r[k] for k in ["total_return","max_drawdown","trades","monthly_geometric_net"]} for s,r in scenarios.items()}}),flush=True)
    (a.output/"summary.json").write_text(json.dumps({"results":results,"plan":plan,"plan_sha256":sha256(a.plan),
        "prediction_files":provenance,"dataset_manifest_sha256":sha256(ds/"manifest.json"),"source_summary_sha256":sha256(source/"summary.json"),
        "independent_test":False,"live_approved":False,"previous_probe_invalid":True},indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--plan",type=Path,default=Path("configs/swing_v17_causal_calibration.json"));p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
