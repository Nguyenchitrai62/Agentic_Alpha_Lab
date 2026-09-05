import torch
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from agentic_alpha_lab.data.swing import SwingStore
from agentic_alpha_lab.data.training import sha256
from agentic_alpha_lab.data.sequence_context import encode_windows


def run(a):
    meta=json.loads((a.dataset/"manifest.json").read_text())
    for name,digest in meta["files"].items():
        if sha256(a.dataset/name)!=digest:
            raise ValueError("Source snapshot changed")
    if a.output.exists():
        raise FileExistsError("Choose new immutable cache")
    cfg=json.loads((a.dataset/"config.json").read_text())
    candles=pd.read_parquet(a.dataset/"candles.parquet")
    decisions=pd.read_parquet(a.dataset/"decisions.parquet")
    with np.load(a.dataset/"examples.npz",allow_pickle=False) as f:
        existing=f["features"]
    store=SwingStore(candles,cfg)
    sequences=[]
    for i,timestamp in enumerate(decisions.signal_time):
        w,_,_,features,_,_=store.sample(timestamp)
        np.testing.assert_allclose(features,existing[i],rtol=1e-6,atol=1e-6)
        sequences.append(encode_windows(w))
        if (i+1)%1000==0:
            print(f"sequence cache {i+1}/{len(decisions)}",flush=True)
    a.output.mkdir(parents=True)
    np.save(a.output/"sequences.npy",np.stack(sequences))
    decisions[["signal_time"]].to_parquet(a.output/"decisions.parquet",index=False)
    manifest={"state":"complete","rows":len(decisions),"shape":[len(decisions),5,128,6],
              "dataset_manifest_sha256":sha256(a.dataset/"manifest.json"),"script_sha256":sha256(Path(__file__)),
              "encoding":"window-only logOHLC/lastclose scaled by pastlogreturnstd>=0.001; log1pvol centered by pastmedian; clips fixed",
              "files":{n:sha256(a.output/n) for n in ("sequences.npy","decisions.parquet")},
              "independent_test":False}
    (a.output/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--dataset",type=Path,default=Path("data/processed/swing_regime_research_v4"))
    p.add_argument("--output",type=Path,required=True)
    run(p.parse_args())
