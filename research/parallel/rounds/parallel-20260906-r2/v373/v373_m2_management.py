"""v373: M2 structure (ONE human-placeable dip limit per coin at 3.0 sigma) with the M4 / M5 book management (registry v373).

Why: M2 (v340 RA2 deployment form: M1 book x0.75 + one bracket dip limit 3.0 sigma, touch stop 8 sigma, R2 agents' size / TP) has the lowest
drawdown of the MANUAL family (gate DD 13.95, 5y 4.93) - the only design inside goal 2's DD < 15. M4's book SL 5 / TP 10 sigma_d and M5's
loss_act tighten each lifted M3 (two dip limits). Question: do they lift the low-DD M2 structure toward goal 2 (8 %/month, DD < 15, book win 60 %)
without raising its DD? Data / books / agents / costs exactly as v367 (kpack inputs, CB books, engine_user trade mode, Bybit fees, adverse funding,
minute-5 rule, limit entries, SL market / TP limit, stop-first). Nothing is fitted here.
Rows (fixed before running): M2 (reference: one 3.0-sigma dip, default book SL / TP), M2S (M2 + book SL 5 / TP 10 sigma_d), M2ST (M2S + loss_act
tighten, the M5 rule).
PROTOCOL (as v367): goal-1 fitness = v310.fitness (book win rate); dev folds k = 2, 3 choose on years [:k]; TRANSFER if a non-reference row is
chosen and beats M2 on the unseen dev year in both folds (v310 single-year fitness); final = dev4 choice; the most recent year computed once for the
final only. Secondary (report only, never used to choose): the final under stop_slip 0.5 (system audit 2026-10-03 stress row).

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v373/v373_m2_management.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
ROWS = {"M2": dict(sl=None, mg={}), "M2S": dict(sl=(5.0, 10.0), mg={}), "M2ST": dict(sl=(5.0, 10.0), mg=dict(loss_act="tighten"))}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_m2", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    sim0 = eu.simulate
    v310 = v347.W["v310"]

    def run(row, full=False, extra=None):
        spec = ROWS[row]

        def outer(*a, **kw):
            kw["rungs"] = (3.0,)  # M2: only the 3.0-sigma limit (rung index 0 = the R2 table's 3.0-sigma rung, as in v340 / v342)
            if spec["sl"]:
                kw["m_sl"], kw["m_tp"] = spec["sl"]
            kw.update(extra or {})
            return sim0(*a, **kw)
        enc0 = v310.encode
        eu.simulate = outer
        v310.encode = lambda d: enc0(dict(d, **spec["mg"]))
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim0
            v310.encode = enc0

    v347.fitness, v347.f_single = v310.fitness, v310.fitness_pooled  # goal-1 fitness: book win rate
    res = {k: run(k) for k in ROWS}
    print("M2 dev4", v347.W_metrics(res["M2"], [0, 1, 2, 3]), flush=True)  # reference check: replay dev4 5.23 (backend history_tm v340)
    out = {"version": "v373", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v347.fitness(res[x], ys))
        f_ch, f0 = v347.f_single(res[ch], [k]), v347.f_single(res["M2"], [k])
        out["folds"][k] = dict(choice=ch, test=dict(v347.W_metrics(res[ch], [k]), F=round(f_ch, 4)), ref_F=round(f0, 4))
        gains.append(ch != "M2" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], "vs M2", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v347.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    try:  # POST-RUN FIX (disclosed): the kpack fast engine has no stop_slip hook; the first run crashed here after the folds
        s50 = run(ch, True, dict(stop_slip=0.5))
        out["final"]["stress_s50"] = dict(five_years=v347.W_metrics(s50, [0, 1, 2, 3, 4]), dev4=v347.W_metrics(s50, [0, 1, 2, 3]),
                                          full={q: s50[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    except TypeError as exc:
        out["final"]["stress_s50"] = f"not run: {exc}"
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v373_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
