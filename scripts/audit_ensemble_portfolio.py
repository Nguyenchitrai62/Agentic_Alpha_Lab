"""Replay frozen fold signals as one compounded portfolio, explicitly flat in gaps."""
import torch
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.backtest import engine,execution_stress
from agentic_alpha_lab.backtest.engine import CostModel,ExecutionConfig,run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress,run_stress


def run(a):
    exposure=getattr(a,"exposure",1.0)
    if not 0<exposure<=1:
        raise ValueError("This audit allows fixed exposure <=1x only")
    summary=json.loads((a.source/"summary.json").read_text())
    dataset=Path(summary["plan"]["dataset"])
    manifest=json.loads((dataset/"manifest.json").read_text())
    for name,digest in manifest["files"].items():
        if sha256(dataset/name)!=digest:
            raise ValueError("Changed dataset")
    if a.output.exists():
        raise FileExistsError("Choose new immutable audit output")
    a.output.mkdir(parents=True)
    cfg=json.loads((dataset/"config.json").read_text())
    candles=pd.read_parquet(dataset/"candles.parquet")
    execution=ExecutionConfig(entry_expiry_bars=cfg["entry_expiry_bars"],max_holding_bars=max(cfg["holding_days"])*288,
                              leverage=exposure,max_leverage=exposure)
    results={}
    for branch in summary["plan"]["branches"]:
        rows=sorted([r for r in summary["folds"] if r["branch"]["name"]==branch["name"]],key=lambda r:r["start"])
        parts,files=[],{}
        previous=None
        for row in rows:
            start,end=pd.Timestamp(row["start"]),pd.Timestamp(row["end"])
            if previous is not None and start<previous:
                raise ValueError("Overlapping evaluation folds")
            previous=end
            path=a.source/branch["name"]/f"fold_{row['fold']}"/"signals.parquet"
            part=pd.read_parquet(path)
            if len(part) and not ((part.signal_time>=start)&(part.signal_time<end)).all():
                raise ValueError("Signal outside declared fold")
            files[str(path)]=sha256(path)
            parts.append(part)
        signals=pd.concat(parts,ignore_index=True).sort_values("bar_index")
        if signals.bar_index.duplicated().any():
            raise ValueError("Duplicate signal across folds")
        counts=signals.signal_time.dt.strftime("%Y-%m").value_counts()
        if len(counts) and counts.max()>cfg["policy"]["maximum_signals_per_month"]:
            raise ValueError("Fold reset violated monthly cap")
        if (signals.signal_time.diff().dropna()<pd.Timedelta(days=cfg["policy"]["cooldown_days"])).any():
            raise ValueError("Fold reset violated cooldown")
        normal,trades=run_backtest(candles,signals,100,CostModel(**cfg["costs"]),execution)
        fee,fee_trades=run_backtest(candles,signals,100,CostModel(**dict(cfg["costs"],fee_rate_per_fill=.00055)),execution)
        stressed,stress_trades,diagnostics=run_stress(candles,signals,100,CostModel(**cfg["costs"]),execution,FillStress(5,5,5,.00055,False))
        for key,actual in (("result",normal),("fee_stress",fee),("execution_stress",stressed)):
            reports=[r[key]["result"] if key=="execution_stress" else r[key] for r in rows]
            expected=100*float(np.prod([1+r["total_return"] for r in reports]))
            if exposure==1.0:
                np.testing.assert_allclose(actual.final_equity,expected,rtol=1e-10,atol=1e-9)
            if actual.trades!=sum(r["trades"] for r in reports):
                raise ValueError("Stitched execution changed trade count")
        output=a.output/branch["name"]
        output.mkdir()
        for name,values in (("normal",trades),("fee_stress",fee_trades),("execution_stress",stress_trades)):
            pd.DataFrame([asdict(t) for t in values]).to_csv(output/f"{name}_trades.csv",index=False)
        months=pd.period_range(pd.Timestamp(rows[0]["start"]).tz_localize(None),pd.Timestamp(rows[-1]["end"]).tz_localize(None),freq="M")
        counts={str(month):int(counts.get(str(month),0)) for month in months}
        results[branch["name"]]={"normal":asdict(normal),"fee_stress":asdict(fee),"execution_stress":asdict(stressed),
            "stress_diagnostics":diagnostics,"signals_by_calendar_month":counts,"signal_files":files,
            "fold_intervals":[[r["start"],r["end"]] for r in rows],"flat_outside_evaluation_folds":True,
            "all_scenarios_positive_and_dd_below20":all(r.total_return>0 and r.max_drawdown>=-.2 for r in (normal,fee,stressed))}
        print(json.dumps({"branch":branch["name"],"normal":asdict(normal),"fee_stress":asdict(fee),"execution_stress":asdict(stressed)}),flush=True)
    report={"source_summary_sha256":sha256(a.source/"summary.json"),"dataset_manifest_sha256":sha256(dataset/"manifest.json"),
        "results":results,"fixed_exposure":exposure,"independent_test":False,"live_approved":False,
        "caveats":["Post-hoc audit of opened development, not full-period or live evidence.",
                   "Capital100 is carried between predefined evaluation folds; no orders in their gaps.",
                   "Do not annualize this selectively covered history or treat its calendar coverage as full trading.",
                   "No signal, threshold or training changes; fixed exposure is explicitly reported, not calibrated confidence sizing. Close-sampled, not exchange mark drawdown.",
                   "Per-fold profitability gate is unchanged even if stitched net is positive."],
        "sources":{str(Path(m.__file__)):sha256(Path(m.__file__)) for m in (engine,execution_stress)}}
    (a.output/"summary.json").write_text(json.dumps(report,indent=2))
    (a.output/"driver_source.py").write_text(Path(__file__).read_text())


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--exposure",type=float,default=1.0)
    run(parser.parse_args())
