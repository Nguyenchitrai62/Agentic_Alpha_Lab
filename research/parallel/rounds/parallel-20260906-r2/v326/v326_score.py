"""v326 step 3 (fixed with v326_pooled_gru_kaggle.py before the cloud run): score the pooled GRU member PD on the MANUAL M2 setting.
Inputs: artifacts/kaggle/v326/out/v326_pd_preds.parquet (Kaggle output). Books = v94.weights_ls(shorts=True) of pred (majors), cached as
artifacts/research/engine_real/member_PD_pooledgru.parquet. Rows (pullback 0.75 sigma_4h / 3 bars, cap 2, target 0.25, G2 grid trader):
  D0 M2 = (2A + 2PT + D)/5 | D1 (2A + 2PD + D)/5 | D2 (2A + PT + PD + D)/5
Choice on dev folds k = 2, 3 (v310 robust MANUAL fitness on years [:k]); TRANSFER if the choice beats D0 in both folds; final on dev4; the most
recent year computed once for the final choice. Per-seed and ensemble ICs from the kernel log are copied into the result.
  python research/parallel/rounds/parallel-20260906-r2/v326/v326_score.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")
OUT = Path("artifacts/kaggle/v326/out")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v144 = _load("v144_s", RD / "v144/v144_deploy_v3.py")
    ext = v144.v115.v114.v113
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    v92, v94 = ext.v92, ext.v94
    pr = pd.read_parquet(OUT / "v326_pd_preds.parquet")
    pr["t"] = pd.to_datetime(pr["t"], utc=True)
    panel = v92.build()[["t", "sym", "rib", "vol42"]]
    df = pr.merge(panel, on=["t", "sym"], how="left")
    W = v94.weights_ls(df, True)
    W.to_parquet(C / "member_PD_pooledgru.parquet")
    v310 = _load("v310_s", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_s", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    PD = rd("member_PD_pooledgru.parquet")
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    mixes = {"D0": (2 * A + 2 * PT + D) / 5, "D1": (2 * A + 2 * PD + D) / 5, "D2": (2 * A + PT + PD + D) / 5}
    base_p9 = v310._policy9

    def run(k, full=False):
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mixes[k]
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
        finally:
            v310._policy9 = base_p9

    res = {k: run(k) for k in mixes}
    assert abs(v310.metrics(res["D0"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out = {"version": "v326", "kernel_log": json.loads((OUT / "log.json").read_text()),
           "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4)) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, v, flush=True)
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v310.fitness(res[x], ys))
        f_ch, f_ref = v310.fitness(res[ch], [k]), v310.fitness(res["D0"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_D0=round(f_ref, 4))
        deltas.append(f_ch - f_ref)
        print("FOLD", k, out["folds"][k], flush=True)
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    ch = max(res, key=lambda x: v310.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v326_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
