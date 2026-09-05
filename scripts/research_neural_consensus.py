"""Audit all24 neural checkpoints and evaluate fixed ensemble ablations on opened history."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from safetensors.torch import load_file
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.models.macro_micro_value import MacroMicroValue,swing_prediction
from agentic_alpha_lab.models.temporal_value import TemporalValue,predict as temporal_predict
from agentic_alpha_lab.models.ensemble_value import combine
from agentic_alpha_lab.backtest.swing import evaluate
from agentic_alpha_lab.backtest.engine import CostModel,ExecutionConfig
from agentic_alpha_lab.backtest.execution_stress import FillStress,run_stress


def run(a):
    torch.set_num_threads(2)
    plan=json.loads(a.plan.read_text())
    source,dataset=Path(plan["source_run"]),Path(plan["dataset"])
    original=json.loads((source/"summary.json").read_text())
    manifest=json.loads((dataset/"manifest.json").read_text())
    for name,digest in manifest["files"].items():
        if sha256(dataset/name)!=digest:
            raise ValueError("Changed dataset")
    if a.output.exists():
        raise FileExistsError("Choose new immutable experiment")
    a.output.mkdir(parents=True)
    (a.output/"plan.json").write_text(json.dumps(plan,indent=2))
    cfg=json.loads((dataset/"config.json").read_text())
    candles=pd.read_parquet(dataset/"candles.parquet")
    decisions=pd.read_parquet(dataset/"decisions.parquet")
    with np.load(dataset/"examples.npz",allow_pickle=False) as f:
        features=f["features"]
    temporal=plan.get("model_family","macro_micro")=="temporal"
    sequence=None
    if temporal:
        cache=Path(original["plan"]["cache"])
        cache_meta=json.loads((cache/"manifest.json").read_text())
        if cache_meta["state"]!="complete" or cache_meta["dataset_manifest_sha256"]!=sha256(dataset/"manifest.json"):
            raise ValueError("Sequence cache identity mismatch")
        for name,digest in cache_meta["files"].items():
            if sha256(cache/name)!=digest:
                raise ValueError("Changed sequence cache")
        clock=pd.read_parquet(cache/"decisions.parquet")
        if not pd.DatetimeIndex(clock.signal_time).equals(pd.DatetimeIndex(decisions.signal_time)):
            raise ValueError("Sequence cache row misalignment")
        sequence=np.load(cache/"sequences.npy",allow_pickle=False)
    execution=ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],max_holding_bars=max(cfg["holding_days"])*288)
    records,audits=[],[]
    bounds=original["reports"][str(plan["seeds"][0])]["plan"]["folds"]
    for fold,(start,end) in enumerate(bounds):
        mask=((decisions.signal_time>=pd.Timestamp(start))&(decisions.label_end<pd.Timestamp(end))).to_numpy()
        part=decisions.loc[mask].reset_index(drop=True)
        predictions=[]
        for seed in plan["seeds"]:
            checkpoint=source/f"seed{seed}"/"checkpoints"/f"fold_{fold}"
            meta=json.loads((checkpoint/"metadata.json").read_text())
            if sha256(checkpoint/"model.safetensors")!=meta["weights_sha256"]:
                raise ValueError("Changed neural weights")
            seed_report=original["reports"][str(seed)]
            if seed_report["dataset_manifest_sha256"]!=sha256(dataset/"manifest.json") or seed_report["plan"]["folds"]!=bounds:
                raise ValueError("Models do not share data/folds")
            state=load_file(str(checkpoint/"model.safetensors"))
            if temporal:
                if meta["cache_manifest_sha256"]!=sha256(cache/"manifest.json"):
                    raise ValueError("Checkpoint used a different sequence cache")
                model=TemporalValue(state["candidates"],**meta["network"])
            else:
                model=MacroMicroValue(meta["candidate_grid"],**meta["network"])
            model.load_state_dict(state)
            branch_name="temporal_neural" if temporal else "macro_micro_neural"
            saved=source/f"seed{seed}"/branch_name/f"fold_{fold}"/"predictions.npy"
            forecast=np.load(saved,allow_pickle=False)
            replay=temporal_predict(model,sequence[mask],features[mask]) if temporal else swing_prediction(model,features[mask],np.asarray(meta["candidate_grid"],np.float32))
            tolerance=1e-3 if temporal else 1e-5
            np.testing.assert_allclose(replay,forecast,rtol=tolerance,atol=tolerance)
            audits.append({"fold":fold,"seed":seed,"weights_sha256":meta["weights_sha256"],
                           "prediction_sha256":sha256(saved),"decisions_replayed":len(replay),
                           "max_error":float(np.max(np.abs(replay-forecast)))})
            predictions.append(forecast)
        for branch in plan["branches"]:
            output=a.output/branch["name"]/f"fold_{fold}"
            output.mkdir(parents=True)
            forecast,details=combine(predictions,branch["penalty"])
            report,signals,trades=evaluate(forecast,part,candles,cfg,f"opened_ensemble_fold_{fold}")
            signals=signals.drop(columns=["conditional_net_quantiles_percent","conditional_win_score"],errors="ignore")
            if branch["penalty"]:
                signals=signals.rename(columns={"expected_net_percent":"disagreement_adjusted_score_percent"})
            stressed,stress_trades,diagnostics=run_stress(candles,signals,100,CostModel(**cfg["costs"]),execution,FillStress(5,5,5,.00055,False))
            report.update({"branch":branch,"fold":fold,"start":start,"end":end,
                           "execution_stress":{"result":asdict(stressed),**diagnostics},
                           "independent_test":False,"confidence_calibrated":False})
            (output/"report.json").write_text(json.dumps(report,indent=2))
            signals.to_parquet(output/"signals.parquet",index=False)
            trades.to_csv(output/"trades.csv",index=False)
            pd.DataFrame([asdict(t) for t in stress_trades]).to_csv(output/"stress_trades.csv",index=False)
            np.savez_compressed(output/"predictions.npz",prediction=forecast,**details)
            records.append(report)
            print(json.dumps({"fold":fold,"branch":branch["name"],"net":report["result"]["total_return"],"dd":report["result"]["max_drawdown"],"fills":report["result"]["trades"],"stress_net":stressed.total_return}),flush=True)
    summaries={}
    for branch in plan["branches"]:
        rows=[r for r in records if r["branch"]["name"]==branch["name"]]
        positive=sum(r["result"]["total_return"]>0 and r["fee_stress"]["total_return"]>0 and r["execution_stress"]["result"]["total_return"]>0 for r in rows)
        dd=min(min(r["result"]["max_drawdown"],r["fee_stress"]["max_drawdown"],r["execution_stress"]["result"]["max_drawdown"]) for r in rows)
        fills=sum(r["result"]["trades"] for r in rows)
        summaries[branch["name"]]={"mean_fold_net":float(np.mean([r["result"]["total_return"] for r in rows])),"joint_positive_folds":positive,"worst_scenario_fold_dd":dd,"total_fills":fills,"advances":positive>=6 and dd>=-.2 and fills>=30}
    result={"plan":plan,"plan_sha256":sha256(a.plan),"source_summary_sha256":sha256(source/"summary.json"),
            "summaries":summaries,"audits":audits,"folds":records,"live_approved":False,"independent_test":False}
    (a.output/"summary.json").write_text(json.dumps(result,indent=2))
    (a.output/"driver_source.py").write_text(Path(__file__).read_text())
    print(json.dumps(summaries),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,default=Path("configs/swing_v12_consensus.json"))
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
