"""v364: NEIGHBOURHOOD of M4's book bracket - is SL 5 / TP 10 a plateau or a sharp peak? (registry v364, registered before running).

v362 picked SL 5 / TP 10 sigma_d for the MANUAL book on dev4 (paper pipeline M4) but the fold transfer was not confirmed. v364 scores the two
one-step neighbours that separate the stop from the take-profit effect. Rows (fixed before running; everything else = M3 / M4, kpack inputs):
  M4     = SL 5 / TP 10 (reference, dev4 6.392)
  S5T8   = SL 5 / TP 8
  S4T10  = SL 4 / TP 10
Fitness / protocol as v347-v362 (MANUAL fitness, all-trade win): dev folds k = 2, 3 on years [:k]; TRANSFER if S5T8 / S4T10 is chosen and beats M4 on
the unseen dev year in both folds; final on dev4; most recent year once (reported as the neighbourhood's spread, never used to choose).

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v364/v364_m4_neighbourhood.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
SLTP = {"M4": (5.0, 10.0), "S5T8": (5.0, 8.0), "S4T10": (4.0, 10.0)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_nb", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    sim0 = eu.simulate

    def run(row, full=False):
        def outer(*a, **kw):
            if SLTP[row] is not None:
                kw["m_sl"], kw["m_tp"] = SLTP[row]
            return sim0(*a, **kw)
        eu.simulate = outer
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in SLTP}
    assert abs(v347.W_metrics(res["M4"], [0, 1, 2, 3])["R"] - 6.392) < 0.003
    out = {"version": "v364", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
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
    (HERE / "v364_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
