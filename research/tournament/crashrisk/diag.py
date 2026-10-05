"""Disclosed post-score diagnostic (no selection): BOT bar returns by predicted-risk bucket and the dial during the worst episodes."""
import json, pickle
import numpy as np, pandas as pd
from run_crashrisk import RUNS
D = pd.read_parquet("dial_hourly.parquet"); D["T"] = pd.to_datetime(D["T"], utc=True); D = D.set_index("T")
P = pd.read_parquet("panel.parquet"); P["T"] = pd.to_datetime(P["T"], utc=True); P = P.set_index("T")
runs = pickle.loads(RUNS.read_bytes())
out = {}
for strat in ("R2", "R2K"):
    rows = []
    for s in range(4):
        r = runs[s][strat]; t = pd.to_datetime(r["t"], utc=True); eq = np.asarray(r["eq"]); mn = np.asarray(r["eq_min"])
        prev = np.concatenate([[1.0], eq[:-1]])
        rows.append(pd.DataFrame({"T": t - pd.Timedelta(hours=4), "r": eq / prev - 1, "rmin": mn / prev - 1}))
    B = pd.concat(rows); B = B[B["T"] < pd.Timestamp("2025-09-24", tz="UTC")]
    B["m1"] = D["D1_clf_80_95"].reindex(B["T"]).to_numpy(); B["crash"] = P["crash24"].reindex(B["T"]).to_numpy()
    B["bucket"] = pd.cut(B["m1"], [0.49, 0.5001, 0.75, 0.9999, 1.01], labels=["m=0.5", "0.5-0.75", "0.75-1", "m=1"])
    g = B.groupby("bucket", observed=True).agg(n=("r", "size"), mean_r_bp=("r", lambda x: 1e4 * x.mean()), sum_r=("r", "sum"),
                                                 worst_rmin=("rmin", "min"), crash_rate=("crash", "mean"))
    print(strat, "\n", g.round(4)); out[strat] = g.round(5).reset_index().astype({"bucket": str}).to_dict("records")
    w = B.nsmallest(10, "rmin")[["T", "r", "rmin", "m1", "crash"]]
    print("worst 10 intrabar minima", strat, "\n", w.round(4)); out[strat + "_worst"] = w.astype({"T": str}).round(4).to_dict("records")
ep = {}
for a, b in (("2024-01-02 12:00", "2024-01-03 18:00"), ("2022-11-07", "2022-11-10"), ("2021-12-03 12:00", "2021-12-04 12:00")):
    x = D.loc[pd.Timestamp(a, tz="UTC"):pd.Timestamp(b, tz="UTC"), "D1_clf_80_95"]
    ep[f"{a}..{b}"] = dict(mean=round(float(x.mean()), 3), min=round(float(x.min()), 3))
print(ep); out["episodes_D1"] = ep
json.dump(out, open("diag.json", "w"), indent=1, default=str)
