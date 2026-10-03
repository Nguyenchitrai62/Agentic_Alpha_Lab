"""v367: M4 trader-management rows judged with the GOAL-1 fitness (book win rate) (registry v367; POST-HOC, disclosed).

AGENTS.md goal 1 (MANUAL) asks for a BOOK win rate >= 55 %, and the original v310 MANUAL fitness (fitness_pooled / fitness) uses the book win rate.
From v338 on the MANUAL rows were judged with the ALL-trade win rate (book + dip limits). v366 showed (dev rows seen before this registration) that
loss_act "tighten" lifts M4's book win rate to 0.648 (all trades 0.701) at a lower dev return. v367 re-judges goal-relevant rows with the ORIGINAL v310
MANUAL fitness (book win rate), everything else unchanged. Rows (fixed before running): M4 (reference), LT (loss_act tighten), LTH (loss_act hold).
PROTOCOL: dev folds k = 2, 3 with v310.fitness on years [:k]; TRANSFER if LT / LTH is chosen and beats M4 on the unseen dev year in both folds (v310
single-year fitness); final on dev4 with v310.fitness; the most recent year computed once for the final. POST-HOC: the fitness change was decided after
seeing v366's dev rows (never the most recent year of LT / LTH); the prospective paper log is the clean evidence.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v367/v367_m4_bookwin_fitness.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
MG = {"M4": {}, "LT": dict(loss_act="tighten"), "LTH": dict(loss_act="hold")}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_bw", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    sim0 = eu.simulate

    def run(row, full=False):
        def outer(*a, **kw):
            kw["m_sl"], kw["m_tp"] = 5.0, 10.0
            return sim0(*a, **kw)
        v310 = v347.W["v310"]
        enc0 = v310.encode
        eu.simulate = outer
        v310.encode = lambda d: enc0(dict(d, **MG[row]))  # v347.run_genome encodes (target 0.25, cap 2, n_valid 3)
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim0
            v310.encode = enc0

    v310m = v347.W["v310"]
    v347.fitness, v347.f_single = v310m.fitness, v310m.fitness_pooled  # goal-1 fitness: book win rate
    res = {k: run(k) for k in MG}
    assert abs(v347.W_metrics(res["M4"], [0, 1, 2, 3])["R"] - 6.392) < 0.003
    out = {"version": "v367", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
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
    (HERE / "v367_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
