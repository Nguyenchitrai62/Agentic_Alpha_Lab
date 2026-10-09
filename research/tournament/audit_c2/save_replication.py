"""Save replication.json (Part A) — BEFORE opening any oc_chronos output."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_repc2", RD / "v388" / "v388_bot_stop_distance.py")
rm = _load("rm_repc2", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")

STRAT_REF = "R2B1D17BFG2"
STRAT_C2 = "R2B1D17BFG2C2"


def geo(rs):
    return round(100 * float(np.prod([1 + r / 100 for r in rs]) ** (1 / len(rs)) - 1), 3)


def main():
    # fits (recompute blind)
    import sys
    sys.path.insert(0, str(ROOT / "research/tournament"))
    import harness
    d = harness.load()
    f = pd.read_parquet(ROOT / "research/tournament/oc_chronos/chronos_features_4shift.parquet",
                        columns=["sym", "shift", "T", "ch_q10"])
    f0 = f[f["shift"] == 0][["sym", "T", "ch_q10"]].copy()
    f0["T"] = pd.to_datetime(f0["T"], utc=True)
    d["T"] = pd.to_datetime(d["T"], utc=True)
    anchors = [pd.Timestamp(a, tz="UTC") for a in
               ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
    fits = {}
    for a in anchors:
        cut = a - pd.Timedelta(days=7)
        tr = d[d.sym.isin(harness.MAJORS) & (d.t_exit < cut)]
        m = tr.merge(f0, on=["sym", "T"], how="inner")
        m["risk"] = -m["ch_q10"]
        rho = float(m["risk"].corr(m["y_dep"], method="spearman"))
        direction = int(1 if rho > 0 else (-1 if rho < 0 else 0))
        fits[str(a.date())] = dict(direction=direction, q20=float(m["risk"].quantile(0.20)),
                                   q80=float(m["risk"].quantile(0.80)), rho=rho,
                                   n_train=int(len(tr)), n_joined=int(len(m)))

    c2runs = pickle.loads((HERE / "audit_c2_runs.pkl").read_bytes())
    ref = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    runs = {}
    for s in range(4):
        runs[s] = {STRAT_REF: ref[s][STRAT_REF], STRAT_C2: c2runs[s][STRAT_C2]}

    out_years = {}
    for strat in (STRAT_REF, STRAT_C2):
        out_years[strat] = [rm.year_reset(runs, strat, y) for y in range(5)]

    g1 = v388.Y1 + pd.Timedelta(hours=12)
    full = {}
    for strat in (STRAT_REF, STRAT_C2):
        e, mn = v388.mix(runs, strat, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
        full[strat] = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)

    def summ(ys):
        Rs = [y["R"] for y in ys]
        return dict(R=geo(Rs), W=round(min(Rs), 3), DD=max(y["DD"] for y in ys),
                    losing=sum(r < 0 for r in Rs), years=[[y["R"], y["DD"]] for y in ys])

    rep = {
        "meta": {
            "blind": True,
            "fits_from": "harness.load() majors t_exit<A-7d joined to shift-0 ch_q10 on (sym,T); risk=-ch_q10",
            "engine": "v421 rule inv k1.0 kd1.7 bear G2.0 + per-(coin,holding-bar) C2 mult 1.25/0.75/1 (missing->1); holding bar H=idx+4h; anchor=latest A<=H",
            "ref_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl (bit-exact)",
            "c2_src": "research/tournament/audit_c2/audit_c2_runs.pkl (4-phase, win_start=5, gate costs)",
            "g2_reproduced": out_years[STRAT_REF],
        },
        "fits": fits,
        "years_ref": out_years[STRAT_REF],
        "years_c2": out_years[STRAT_C2],
        "dev4_ref": summ(out_years[STRAT_REF][:4]),
        "dev4_c2": summ(out_years[STRAT_C2][:4]),
        "y4_ref": out_years[STRAT_REF][4],
        "y4_c2": out_years[STRAT_C2][4],
        "y5_ref": summ(out_years[STRAT_REF]),
        "y5_c2": summ(out_years[STRAT_C2]),
        "full_path_dd_ref": full[STRAT_REF],
        "full_path_dd_c2": full[STRAT_C2],
    }
    raw = json.dumps(rep, indent=1)
    (HERE / "replication.json").write_text(raw)
    print(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
