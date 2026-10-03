"""v349: HOUR-OF-DAY size multiplier for the MANUAL bracket dip limits, learned walk-forward from pooled experience (registry v349).

Dev-only diagnostic (research/diagnostics/dip_hour, anchors 2021-2024): M3 dip fills in the 08 and 12 UTC holding bars were positive in all four dev
years (12 UTC: win 0.70-0.90), the 04 / 16 / 20 UTC bars each had a losing year. The dip agents see the hour as one of seven features but act only
through coarse x1.5 / x0.5 rules. v349 adds an explicit per-hour size multiplier estimated WITHOUT the traded years: for the dev / test year starting
at anchor a, the pooled survivorship-free experience (v349_pooled_fills.py: 5 majors + 30 U2020 alts, bracket limits 3.0 / 4.0 sigma, TP 1 sigma,
native touch stop 8 sigma) with t_exit < a - 7 days gives the mean net return per fill by the UTC hour of the holding bar, mean_h, and overall, mean_all.
Rows (fixed before running; everything else = the deployed M3):
  M3  = no hour multiplier (reference, dev4 6.233)
  H1  = dip size x clip(mean_h / mean_all, 0.5, 1.5)
  H2  = dip size x (0 if mean_h <= 0 else 1)   (skip hours with a non-positive pooled mean)
Fitness / protocol as v347 / v348 (MANUAL fitness, all-trade win): dev folds k = 2, 3 on years [:k]; TRANSFER if H1 / H2 is chosen and beats M3 on
the unseen dev year in both folds; final choice on dev4; most recent year once. Contaminated by design; prospective log = clean evidence.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v349/v349_dip_hour_multiplier.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hour_tables(fills, anchors):
    out = []
    for a in anchors:
        f = fills[fills.t_exit < a - pd.Timedelta(days=7)]
        mh = f.groupby("hour").y.mean().reindex(range(0, 24, 4))
        out.append((mh, float(f.y.mean()), len(f)))
    return out


def main():
    v347 = _load("v347_h", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    W0 = v347.W["v310"].W
    idx, anchors = W0["idx"], W0["anchors"]
    fills = pd.read_parquet("artifacts/research/engine_real/v349_pooled_fills_m3.parquet")
    for c in ("t_exit", "bar"):
        fills[c] = pd.to_datetime(fills[c], utc=True)
    tabs = hour_tables(fills, anchors)
    hold_h = np.asarray((idx + pd.Timedelta(hours=4)).hour)
    yr = np.clip(np.searchsorted(np.array(anchors), np.asarray(idx + pd.Timedelta(hours=4)), side="right") - 1, 0, len(anchors) - 1)
    mults = {"M3": np.ones(len(idx))}
    for name, rule in (("H1", lambda m, a: np.clip(m / a, 0.5, 1.5)), ("H2", lambda m, a: float(m > 0))):
        mults[name] = np.array([rule(tabs[y][0][h], tabs[y][1]) for y, h in zip(yr, hold_h)], float)
    out = {"version": "v349", "hour_tables": {str(a.date()): dict(mean_h={int(h): round(float(v), 5) for h, v in t[0].items()}, mean_all=round(t[1], 5), n=t[2])
                                              for a, t in zip(anchors, tabs)}}
    size0 = v347.W["size"].copy()
    res = {}
    for k, m in mults.items():
        v347.W["size"] = size0 * m[:, None, None]
        res[k] = v347.run_genome(v347.encode(v347.SEEDS["CB"]))
    v347.W["size"] = size0
    assert abs(v347.W_metrics(res["M3"], [0, 1, 2, 3])["R"] - 6.233) < 0.003
    out["rows"] = {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                           years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    out["folds"], gains = {}, []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v347.fitness(res[x], ys))
        f_ch, f0 = v347.f_single(res[ch], [k]), v347.f_single(res["M3"], [k])
        out["folds"][k] = dict(choice=ch, test=dict(v347.W_metrics(res[ch], [k]), F=round(f_ch, 4)), m3_F=round(f0, 4))
        gains.append(ch != "M3" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], "vs M3", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v347.fitness(res[x], [0, 1, 2, 3]))
    v347.W["size"] = size0 * mults[ch][:, None, None]
    full = v347.run_genome(v347.encode(v347.SEEDS["CB"]), True)
    v347.W["size"] = size0
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v349_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
