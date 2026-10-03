"""v352: the information-rich book of v351 (quarterly basis in member A) with ONE-WAY-EXPOSURE control, on the M3 structure (registry v352).

v351 QB1 (A_qb + B + D books in M3): dev4 6.551, worst dev year 3.778, book win 0.526 - better return and worst year than M3 - but DD 22.85; the
same pattern as every flow / venue extension (v237, v238, v244, v262): new information makes the book more one-directional. The G2 DD anatomy
(research/diagnostics/g2_dd) puts half of the drawdown in all-long / net-short concentration. Two controls (fixed before running; everything else
= v351 QB1 on the M3 structure, kpack inputs):
  M3     = CB books (reference, dev4 6.233)
  QBm60  = QB1 books with book_mult 0.60 instead of 0.75 (less book risk, same dip limits)
  QBn50  = QB1 books, each member cross-sectionally half-demeaned per bar (w - 0.5 * mean over the five coins), book_mult 0.75
Fitness / protocol as v347-v351 (MANUAL fitness, all-trade win): dev folds k = 2, 3 on years [:k]; TRANSFER if QBm60 / QBn50 is chosen and beats M3
on the unseen dev year in both folds; final on dev4; most recent year once. Contaminated by design; prospective log = clean evidence.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v352/v352_info_book_risk_control.py
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
C = Path("artifacts/research/engine_real")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_rc", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    W0 = v347.W["v310"].W
    idx, cols, eu = W0["idx"], W0["cols"], W0["eu"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    A_qb = (rd("member_A_qb.parquet") + rd("member_Aq_qb.parquet")) / 2
    X = v347.W["X"]
    keep = {n: X[n].copy() for n in ("wA", "wB", "wD")}
    half = lambda M: M - 0.5 * M.mean(axis=1, keepdims=True)
    sim_outer0 = eu.simulate

    def run(row, full=False):
        bm = 0.60 if row == "QBm60" else None
        if row != "M3":
            X["wA"] = A_qb
        if row == "QBn50":
            for n in ("wA", "wB", "wD"):
                X[n] = half(X[n])

        def outer(*a, **kw):
            if bm is not None:
                kw["trade"] = dict(kw["trade"], book_mult=bm)
            return sim_outer0(*a, **kw)
        eu.simulate = outer  # v347.run_genome wraps this; its book_mult 0.75 is overridden here for QBm60
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim_outer0
            for n, v in keep.items():
                X[n] = v.copy()

    res = {k: run(k) for k in ("M3", "QBm60", "QBn50")}
    assert abs(v347.W_metrics(res["M3"], [0, 1, 2, 3])["R"] - 6.233) < 0.003
    out = {"version": "v352", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    gains = []
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
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v352_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
