"""v370: NEIGHBOURHOOD of M5's tighten rule - plateau or sharp peak? (registry v370, registered before running).

M5 (v367: M4 + loss_act tighten) moves a losing position's stop to 1.5 sigma_d from the bar open when the signal goes flat (engine trade param
"tighten" 1.5, the v216 GRID default). v370 scores the two neighbours of that distance with the goal-1 fitness that chose M5 (v310 fitness, book win).
Rows (fixed before running; everything else = M5): M5 = tighten 1.5 (reference, dev4 6.015) | TG10 = tighten 1.0 | TG20 = tighten 2.0.
PROTOCOL: dev folds k = 2, 3 on years [:k]; TRANSFER if TG10 / TG20 is chosen and beats M5 on the unseen dev year in both folds; final on dev4; the
most recent year computed once (reported as the neighbourhood's spread).

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v370/v370_m5_neighbourhood.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
TG = {"M5": 1.5, "TG10": 1.0, "TG20": 2.0}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_tg5", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    sim0 = eu.simulate

    def run(row, full=False):
        def outer(*a, **kw):
            kw["m_sl"], kw["m_tp"] = 5.0, 10.0
            kw["trade"] = dict(kw["trade"], tighten=TG[row])
            return sim0(*a, **kw)
        v310 = v347.W["v310"]
        enc0 = v310.encode
        eu.simulate = outer
        v310.encode = lambda d: enc0(dict(d, loss_act="tighten"))  # v347.run_genome encodes (target 0.25, cap 2, n_valid 3)
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim0
            v310.encode = enc0

    v310m = v347.W["v310"]
    v347.fitness, v347.f_single = v310m.fitness, v310m.fitness_pooled  # the goal-1 fitness that chose M5 (book win)
    res = {k: run(k) for k in TG}
    assert abs(v347.W_metrics(res["M5"], [0, 1, 2, 3])["R"] - 6.015) < 0.003
    out = {"version": "v370", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v347.fitness(res[x], ys))
        f_ch, f0 = v347.f_single(res[ch], [k]), v347.f_single(res["M5"], [k])
        out["folds"][k] = dict(choice=ch, test=dict(v347.W_metrics(res[ch], [k]), F=round(f_ch, 4)), m3_F=round(f0, 4))
        gains.append(ch != "M5" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], "vs M5", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v347.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v370_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
