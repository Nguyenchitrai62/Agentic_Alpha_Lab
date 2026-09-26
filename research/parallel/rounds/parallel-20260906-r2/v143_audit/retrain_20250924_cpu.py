"""v143 audit 3: reproducibility. Retrain anchor 2025-09-24 on CPU seeds 0-4.

Uses artifacts/kaggle/v143/kernel/train_v143.py run_anchor/tensors (no edits),
dataset --data artifacts/kaggle/v143/dataset, writes pred_2025-09-24_cpu.parquet
+ log + repro_report.json to this audit folder. Compares Spearman IC of
mean(p6,p18) vs y6 against artifacts/kaggle/v143/local_out/pred_2025-09-24.parquet.
"""
import torch  # noqa: F401  (before pandas on Windows GPU hosts)
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
AUD = Path(__file__).resolve().parent
KERNEL = ROOT / "artifacts/kaggle/v143/kernel/train_v143.py"
DATA = ROOT / "artifacts/kaggle/v143/dataset"
SAVED = ROOT / "artifacts/kaggle/v143/local_out/pred_2025-09-24.parquet"

spec = importlib.util.spec_from_file_location("train_v143", KERNEL)
tv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tv)


def spearman(a, b):
    m = pd.DataFrame({"a": np.asarray(a, float), "b": np.asarray(b, float)}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(m.corr(method="spearman").iloc[0, 1])


def main():
    meta = json.loads((DATA / "feature_list.json").read_text())
    df = pd.read_parquet(DATA / "v143_panel.parquet")
    feats, syms = meta["features"], meta["syms"]
    times = np.sort(df["t"].unique())
    X, Y = tv.tensors(df, feats, syms, times)
    anchor = "2025-09-24"
    ns = pd.Timestamp(anchor, tz="UTC").value
    t0 = time.time()
    te_idx, P, log, info = tv.run_anchor(X, Y, times, ns, "cpu", (0, 1, 2, 3, 4), 40)
    secs = round(time.time() - t0, 1)
    rows = []
    for j, s in enumerate(syms):
        ok = X[te_idx, j, len(feats)] > 0
        rows.append(pd.DataFrame({"t": times[te_idx][ok], "sym": s, "p6": P[ok, j, 0], "p18": P[ok, j, 1], "p42": P[ok, j, 2]}))
    pred = pd.concat(rows, ignore_index=True)
    pred.to_parquet(AUD / "pred_2025-09-24_cpu.parquet", index=False)
    (AUD / "log_2025-09-24_cpu.json").write_text(json.dumps(log))
    # IC compare vs saved + vs panel y6
    panel = df[["t", "sym", "y6"]].copy()
    panel["t"] = pd.to_datetime(panel["t"], utc=True)
    saved = pd.read_parquet(SAVED).copy()
    saved["t"] = pd.to_datetime(saved["t"], utc=True)
    cpu = pred.copy()
    cpu["t"] = pd.to_datetime(cpu["t"], utc=True)
    out = {}
    for tag, fr in (("saved", saved), ("cpu", cpu)):
        m = fr.merge(panel, on=["t", "sym"], how="left")
        m["nn"] = 0.5 * (m["p6"] + m["p18"])
        g = m.dropna(subset=["y6"])
        out[tag] = {"n": int(len(g)), "ic_nn_y6": round(spearman(g["nn"], g["y6"]), 4),
                    "ic_p6_y6": round(spearman(g["p6"], g["y6"]), 4)}
    out["diff_ic_nn_y6_cpu_minus_saved"] = round(out["cpu"]["ic_nn_y6"] - out["saved"]["ic_nn_y6"], 4)
    out["seconds_cpu"] = secs
    out["info"] = info
    out["epochs"] = [l["epoch"] for l in log if l["epoch"] == max(x["epoch"] for x in log if x["seed"] == l["seed"])]
    out["needs_explanation"] = bool(abs(out["diff_ic_nn_y6_cpu_minus_saved"]) > 0.02)
    (AUD / "repro_report.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
