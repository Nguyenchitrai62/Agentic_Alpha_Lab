"""v167: temporal GRU (last 42 bars of the 70 engineered features, Kaggle GPU) as a fourth member (registry v167).

Training: research/parallel/rounds/parallel-20260906-r2/v167/kaggle/train_v167.py on Kaggle (private kernel
nguynchtrai/v167-temporal-gru-majors, dataset nguynchtrai/v165-majors-full-panel exported by v165_export.py): 2-layer GRU,
6 seeds, walk-forward anchors with per-target cutoffs/embargoes, early stopping on the last training
year. Outputs downloaded to artifacts/kaggle/v167/output/v167_out/pred_<anchor>.parquet.
Evaluation (fixed before the Kaggle run finished):
  NN prediction per target = gru_p6, gru_p18, gru_p42, gru_p84.
  Member E books on the v103 panel rows: v92 LO from p42, v94 LS from mean(p18, p42, p84), v103 LS from mean(p6, p18);
  v129 vol-forecast sizing (swap vol42 -> pvol, same vol models as v144), tranching, own book vol targets, 0.25/0.25/0.5.
  Primary: (A + B + D + E)/4 with v154 members A, B, D; secondary: E alone; per-architecture IC report.
  v144 realistic engine rows. Reference v154: 3.515/19.15.

  python research/parallel/rounds/parallel-20260906-r2/v167/v167_evaluate.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRED = Path("artifacts/kaggle/v167/output/v167_out")
PD = 6


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v144 = _load("v144", "v144/v144_deploy_v3.py")
    v151 = _load("v151", "v151/v151_info_ensemble.py")
    v154 = _load("v154", "v154/v154_ensemble_coinbase.py")
    v129, v125, v103 = v144.v129, v144.v125, v144.v103
    ext = v144.v115.v114.v113
    p103, A = v144.books_v142()
    _, B = v151.books_with_options()
    _, D = v154.books_coinbase()
    nn = pd.concat([pd.read_parquet(PRED / f"pred_{a}.parquet") for a in ext.v92.ANCHORS], ignore_index=True)
    nn["t"] = pd.to_datetime(nn["t"], utc=True)
    for k in ("p6", "p18", "p42", "p84"):
        nn[k] = nn[f"gru_{k}"]
    base = p103.merge(nn, on=["t", "sym"], how="inner")
    ic = {}
    for a in ext.v92.ANCHORS:
        g = base[(base.t >= pd.Timestamp(a, tz="UTC")) & (base.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))]
        ic[a] = {f"{arch}_{k}_vs_{y}": round(float(g[f"{arch}_{k}"].corr(g[y], method="spearman")), 4)
                 for arch in ("gru",) for k, y in (("p6", "y6"), ("p42", "y"))}
        print(a, ic[a], flush=True)
    f103 = [c for c in p103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    pv, _ = v129.vol_predict(p103, f103, ext.v92.ANCHORS, ext.v92.EMBARGO_BARS)

    def frame(pred):
        d = base[["t", "sym", "rib", "vol42"]].assign(pred=pred.to_numpy()).merge(pv, on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    ph = list(range(PD))
    W_lo = v125.phased(v125.raw_lo(frame(base["p42"])), ph)
    W94 = v125.phased(v125.raw_ls(frame(base[["p18", "p42", "p84"]].mean(axis=1))), ph)
    W103 = v125.phased(v125.raw_ls(frame(base[["p6", "p18"]].mean(axis=1))), ph)
    idx = W_lo.index.union(W94.index).union(W103.index)
    E = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(ext.v92.vol_target_scale(p103, W_lo).reindex(idx).fillna(1.0), axis=0) \
        + 0.25 * W94.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W94).reindex(idx).fillna(1.0), axis=0) \
        + 0.5 * W103.reindex(idx).fillna(0.0).mul(ext.v94.vol_target_scale(p103, W103).reindex(idx).fillna(1.0), axis=0)
    out = {"version": "v167", "ic": ic}
    allidx = A.index.union(B.index).union(D.index).union(E.index)
    ens = sum(X.reindex(allidx).fillna(0.0) for X in (A, B, D, E)) / 4
    out["primary_ensemble"] = v144.simulate(p103, ens)
    out["secondary_nn_alone"] = v144.simulate(p103, E.reindex(allidx).fillna(0.0))
    out["reference_v154"] = {"t25": (3.515, 19.15)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v167_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
