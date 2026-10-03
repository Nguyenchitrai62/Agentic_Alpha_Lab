"""v356: a THIRD human-placeable bracket dip limit (5.0 sigma) on the deployed MANUAL pipeline M3 (registry v356, registered before running).

M3 = CB books x0.75 + bracket dip limits at 3.0 / 4.0 sigma (size_mult 4.375 per rung, native touch stop 8 sigma, budget 0.26 at 8 sigma, R2 agents
per rung depth at the bar open); dev4 6.233. The R2 BOT gained from a 5-sigma rung (R2 > G2 on every row); v343 tested (3, 5) INSTEAD of (3, 4),
not the three-rung set. Three bracket limits per coin and 4h bar stay human-placeable (one batch at each 4h close). Rows (fixed before running):
  M3   = rungs (3.0, 4.0), size_mult 4.375 (reference)
  L3   = rungs (3.0, 4.0, 5.0), size_mult 4.375 per rung
  L3h  = rungs (3.0, 4.0, 5.0), size_mult 2.92 per rung (about M3's total dip size split over three depths)
Fitness / protocol as v347-v354 (MANUAL fitness, all-trade win): dev folds k = 2, 3 on years [:k]; TRANSFER if L3 / L3h is chosen and beats M3 on the
unseen dev year in both folds; final on dev4; most recent year once. Contaminated by design; prospective log = clean evidence.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v356/v356_three_rung_manual.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
ROWS = {"M3": ((3.0, 4.0), 4.375), "L3": ((3.0, 4.0, 5.0), 4.375), "L3h": ((3.0, 4.0, 5.0), 2.92)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_l3", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    size, tp = v347.W["size"], v347.W["tp"]
    sim0 = eu.simulate

    def run(row, full=False):
        rungs, smult = ROWS[row]
        kus = [U.index(k) for k in rungs]

        def outer(*a, **kw):
            kw.update(rungs=rungs, size_mult=smult, sleeve_fill_size=lambda i, aa, r, f: float(size[i, aa, kus[r]]),
                      sleeve_tp=lambda i, aa, r, f: float(tp[i, aa, kus[r]]))
            return sim0(*a, **kw)
        eu.simulate = outer
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in ROWS}
    assert abs(v347.W_metrics(res["M3"], [0, 1, 2, 3])["R"] - 6.233) < 0.003
    out = {"version": "v356", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
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
    (HERE / "v356_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
