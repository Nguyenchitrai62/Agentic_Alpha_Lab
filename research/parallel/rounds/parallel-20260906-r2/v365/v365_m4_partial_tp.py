"""v365: PARTIAL take-profit on M4's book - the book win rate goal (registry v365, registered before running).

Goal 1 (MANUAL) asks for a book win rate >= 55 %; M4 (M3 with book SL 5 / TP 10 sigma_d) has 0.507 dev / 0.519 over five years (all trades 0.64).
v309 found that a partial take-profit raises the MANUAL book win rate (0.63-0.68) at some cost in return. Rows (fixed before running; engine trade-mode
partial_k (sigma_d from the entry) / partial_frac of the position closed by a limit there, the rest keeps SL 5 / TP 10; everything else = M4):
  M4     = no partial (reference, dev4 6.392)
  P3h    = half at 3 sigma_d
  P2t    = a third at 2 sigma_d
Fitness / protocol as v347-v364 (MANUAL fitness, all-trade win; the book win rate is reported per row): dev folds k = 2, 3 on years [:k]; TRANSFER if
P3h / P2t is chosen and beats M4 on the unseen dev year in both folds; final on dev4; most recent year once.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v365/v365_m4_partial_tp.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
PART = {"M4": None, "P3h": (3.0, 0.5), "P2t": (2.0, 1 / 3)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_pt", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    sim0 = eu.simulate

    def run(row, full=False):
        def outer(*a, **kw):
            kw["m_sl"], kw["m_tp"] = 5.0, 10.0
            if PART[row] is not None:
                kw["trade"] = dict(kw["trade"], partial_k=PART[row][0], partial_frac=PART[row][1])
            return sim0(*a, **kw)
        eu.simulate = outer
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in PART}
    assert abs(v347.W_metrics(res["M4"], [0, 1, 2, 3])["R"] - 6.392) < 0.003
    out = {"version": "v365", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v347.fitness(res[x], ys))
        f_ch, f0 = v347.f_single(res[ch], [k]), v347.f_single(res["M4"], [k])
        out["folds"][k] = dict(choice=ch, test=dict(v347.W_metrics(res[ch], [k]), F=round(f_ch, 4)), m3_F=round(f0, 4))
        gains.append(ch != "M4" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], "vs M4", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v347.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v365_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
