"""Train registered temporal models, then evaluate all forecasts in one policy state."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
from research_temporal_value import main as train
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.models.ensemble_value import combine,directional_consensus
from agentic_alpha_lab.data.swing import grid
from agentic_alpha_lab.backtest.swing import swing_signals
from agentic_alpha_lab.backtest.engine import CostModel,ExecutionConfig,run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress,run_stress


def partition_indices(decisions,parent):
    end=pd.Timestamp(parent["complete_evaluation_until"])
    parts=[]
    previous=None
    for start,stop in parent["folds"]:
        start,stop=pd.Timestamp(start),pd.Timestamp(stop)
        if start>=stop or (previous is not None and start!=previous):
            raise ValueError("Continuous plan has a gap or overlap")
        previous=stop
        mask=((decisions.signal_time>=start)&(decisions.signal_time<stop)&(decisions.label_end<end)).to_numpy()
        parts.append(np.flatnonzero(mask))
    if previous!=end:
        raise ValueError("Final fold does not match evaluation cutoff")
    expected=np.flatnonzero(((decisions.signal_time>=pd.Timestamp(parent["folds"][0][0]))&(decisions.signal_time<end)&(decisions.label_end<end)).to_numpy())
    np.testing.assert_array_equal(np.concatenate(parts),expected)
    return parts


def require_tcn_audit(plan,source,audit_path):
    if plan.get("model_family")!="tcn_fusion":
        return
    if audit_path is None:
        raise ValueError("TCN cloud exports require a completed local full-forecast audit")
    audit=json.loads(Path(audit_path).read_text())
    summary=json.loads((source/"summary.json").read_text())
    if summary.get("state")!="complete" or summary.get("plan")!=plan:
        raise ValueError("Cloud export incomplete or plan mismatch")
    if audit.get("state")!="passed" or not audit.get("all_forecasts_replayed"):
        raise ValueError("Local replay audit has not passed")
    if audit.get("source_summary_sha256")!=sha256(source/"summary.json"):
        raise ValueError("Audit belongs to another training export")
    if audit.get("dataset_manifest_sha256")!=sha256(Path(plan["dataset"])/"manifest.json"):
        raise ValueError("Audit dataset identity mismatch")
    parent=json.loads(Path(plan["parent_plan"]).read_text())
    expected={(seed,fold) for seed in plan["seeds"] for fold in range(len(parent["folds"]))}
    actual=[(row["seed"],row["fold"]) for row in audit.get("folds",[])]
    if len(actual)!=len(expected) or set(actual)!=expected:
        raise ValueError("Audit omitted or duplicated registered models")
    for key,template in (("prediction_files","seed{seed}/temporal_neural/fold_{fold}/predictions.npy"),
                         ("weight_files","seed{seed}/checkpoints/fold_{fold}/model.safetensors")):
        paths={template.format(seed=seed,fold=fold) for seed,fold in expected}
        if set(audit.get(key,{}))!=paths:
            raise ValueError("Audit artifact coverage mismatch")
        for path in paths:
            if sha256(source/path)!=audit[key][path]:
                raise ValueError("Audited artifact changed")
    if set(audit.get("identical_policy_signals",{}))!={b["name"] for b in plan["ensemble_branches"]}:
        raise ValueError("Missing ensemble-policy parity audit")
    if plan.get("epoch_selection"):
        paths={f"seed{seed}/selection/fold_{fold}/{name}" for seed,fold in expected
               for name in ("selection.json","indices.npz","selected.safetensors")}
        if set(audit.get("selection_files",{}))!=paths:
            raise ValueError("Missing nested selection provenance")
        for path in paths:
            if sha256(source/path)!=audit["selection_files"][path]:
                raise ValueError("Nested selection artifacts changed")


def evaluate_continuous(plan,source,output,audit_path=None):
    require_tcn_audit(plan,source,audit_path)
    original=json.loads((source/"summary.json").read_text())
    parent=json.loads(Path(plan["parent_plan"]).read_text())
    dataset=Path(plan["dataset"])
    manifest=json.loads((dataset/"manifest.json").read_text())
    for name,digest in manifest["files"].items():
        if sha256(dataset/name)!=digest:
            raise ValueError("Dataset changed during training")
    decisions=pd.read_parquet(dataset/"decisions.parquet")
    candles=pd.read_parquet(dataset/"candles.parquet")
    cfg=json.loads((dataset/"config.json").read_text())
    end=pd.Timestamp(parent["complete_evaluation_until"])
    forecasts,indices,files=[],[],{}
    partitions=partition_indices(decisions,parent)
    for fold,(start,stop) in enumerate(parent["folds"]):
        selected=partitions[fold]
        batch=[]
        for seed in plan["seeds"]:
            report=original["reports"][str(seed)]
            if report["dataset_manifest_sha256"]!=sha256(dataset/"manifest.json") or report["plan"]["folds"]!=parent["folds"]:
                raise ValueError("Model/data/fold identity mismatch")
            path=source/f"seed{seed}"/"temporal_neural"/f"fold_{fold}"/"predictions.npy"
            prediction=np.load(path,allow_pickle=False)
            if prediction.shape!=(len(selected),16,6) or not np.isfinite(prediction).all():
                raise ValueError("Prediction shape/values mismatch")
            files[str(path)]=sha256(path)
            batch.append(prediction)
        forecasts.append(np.stack(batch))
        indices.append(selected)
    indices=np.concatenate(indices)
    expected=np.flatnonzero(((decisions.signal_time>=pd.Timestamp(parent["folds"][0][0]))&(decisions.signal_time<end)&(decisions.label_end<end)).to_numpy())
    np.testing.assert_array_equal(indices,expected)
    part=decisions.iloc[indices].reset_index(drop=True)
    predictions=np.concatenate(forecasts,axis=1)
    output.mkdir(parents=True)
    rows={}
    duration_years=(end-pd.Timestamp(parent["folds"][0][0])).total_seconds()/(365.2425*86400)
    for branch in plan["ensemble_branches"]:
        prediction,details=combine(predictions,branch["penalty"])
        if branch.get("require_direction_agreement"):
            allowed,votes=directional_consensus(predictions,np.asarray(grid(cfg))[:,0],cfg["policy"]["minimum_expected_net_percent"],cfg["policy"]["minimum_fill_score"])
            prediction[~allowed]=0
            details.update(allowed_candidates=allowed,seed_direction_votes=votes)
        signals=swing_signals(prediction,part,cfg).drop(columns=["conditional_net_quantiles_percent","conditional_win_score"],errors="ignore")
        if branch["penalty"]:
            signals=signals.rename(columns={"expected_net_percent":"disagreement_adjusted_score_percent"})
        target=output/branch["name"]
        target.mkdir()
        signals.to_parquet(target/"signals.parquet",index=False)
        np.savez_compressed(target/"predictions.npz",prediction=prediction,decision_indices=indices,**details)
        for exposure in plan["exposures"]:
            if not 0<exposure<=1:
                raise ValueError("Unvalidated leverage is forbidden")
            execution=ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],max_holding_bars=max(cfg["holding_days"])*288,leverage=exposure,max_leverage=exposure)
            normal,trades=run_backtest(candles,signals,100,CostModel(**cfg["costs"]),execution)
            fee,fee_trades=run_backtest(candles,signals,100,CostModel(**dict(cfg["costs"],fee_rate_per_fill=.00055)),execution)
            stress,stress_trades,diagnostics=run_stress(candles,signals,100,CostModel(**cfg["costs"]),execution,FillStress(5,5,5,.00055,False))
            key=f"{branch['name']}_exposure{exposure}"
            for name,values in (("normal",trades),("fee_stress",fee_trades),("execution_stress",stress_trades)):
                pd.DataFrame([asdict(t) for t in values]).to_csv(target/f"exposure{exposure}_{name}_trades.csv",index=False)
            months=pd.period_range(part.signal_time.iloc[0].tz_localize(None),part.signal_time.iloc[-1].tz_localize(None),freq="M")
            counts=signals.signal_time.dt.strftime("%Y-%m").value_counts() if len(signals) else {}
            rows[key]={"normal":asdict(normal),"fee_stress":asdict(fee),"execution_stress":asdict(stress),
                "execution_diagnostics":diagnostics,"signals_by_month":{str(m):int(counts.get(str(m),0)) for m in months},
                "signals":len(signals),"exposure":exposure,"confidence_calibrated":False,
                "passes_provisional_continuous_screen":all(r.total_return>0 and r.max_drawdown>=-.2 and r.trades>=30 for r in (normal,fee,stress))}
            for label in ("normal","fee_stress","execution_stress"):
                ratio=rows[key][label]["final_equity"]/100
                rows[key][label].update(annual_geometric_net=ratio**(1/duration_years)-1,
                                       monthly_geometric_net=ratio**(1/(12*duration_years))-1)
            rows[key]["duration_years"]=duration_years
            rows[key]["meets_user_5pct_monthly_target"]=all(rows[key][s]["monthly_geometric_net"]>=.05 and
                rows[key][s]["max_drawdown"]>=-.2 and rows[key][s]["trades"]>=30 for s in ("normal","fee_stress","execution_stress"))
            print(json.dumps({"continuous_branch":key,**rows[key]}),flush=True)
    result={"plan":plan,"results":rows,"decision_count":len(part),"first_signal_time":str(part.signal_time.iloc[0]),
        "last_signal_time":str(part.signal_time.iloc[-1]),"label_cutoff":str(end),"prediction_files":files,
        "training_summary_sha256":sha256(source/"summary.json"),"independent_test":False,"live_approved":False,
        "note":"One continuous policy and compounded equity state. Final immature label tail excluded once, not each quarter. Forward paper evidence and execution/mark-data validation still required; no confidence sizing or profit guarantee."}
    (output/"summary.json").write_text(json.dumps(result,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,default=Path("configs/swing_v15_temporal.json"))
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--training-source",type=Path,help="Reuse completed immutable training; no retraining")
    p.add_argument("--replay-audit",type=Path,help="Required passed audit.json for TCN cloud exports")
    a=p.parse_args()
    if a.output.exists():
        raise FileExistsError("Choose new immutable research output")
    a.output.mkdir(parents=True)
    plan=json.loads(a.plan.read_text())
    (a.output/"plan.json").write_text(json.dumps(plan,indent=2))
    (a.output/"driver_source.py").write_text(Path(__file__).read_text())
    source=a.training_source or a.output/"training"
    if a.training_source is None:
        train(SimpleNamespace(plan=a.plan,output=source))
    evaluate_continuous(plan,source,a.output/"continuous",audit_path=a.replay_audit)
