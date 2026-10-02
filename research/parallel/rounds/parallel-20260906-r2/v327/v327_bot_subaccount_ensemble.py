"""v327: BOT product - EVOLVED SUB-ACCOUNT ENSEMBLE of the existing BOT pipelines (registry v327; the user's suggestion: combine many solutions
with weights found by evolutionary computation instead of a fixed mix).

Candidates = the twelve v306 seed pipelines (G2, J1, R1, Q2, R2, P1, B1, T1, J3, v297, W2m, G2_fitU): complete BOT pipelines (book + learned dip
ladder, bar-open agents) that differ in rung sets, dip agents, budgets, members, close stops and book target. Each runs in its own sub-account; the
sub-accounts are rebalanced to the weights once a year at the anchor; per year y the combined equity e(t) = sum_k w_k eq_k(t) / eq_k(start of y),
1m-marked min = sum of the per-account 1m minima (conservative), peaks from the summed per-account 1m maxima (as engine_user summarize);
trades = all book trades and dip rungs of the members with w > 0.
GENOME: integer weight 0..4 per candidate (normalised; >= 1 member). GA: population 40, 40 generations, tournament 3, uniform crossover, +-1 mutation
(probability 2/12 per weight), (mu + lambda); fitness = v306 BOT fitness (R / 8, W / 5, 15 / DD, all-trade win / 0.65, capped 1.2,
0.5 min + 0.5 mean) on the training years; flat-neighbourhood choice (top 10, 8 one-weight neighbours). GA seeds 3271 / 3272.
PROTOCOL (fixed before running): folds k = 1, 2, 3 (as v306): weights evolved on years [:k], scored on year k against the best single candidate on
years [:k] (= the v306 / v321 procedure, R2 in every fold). TRANSFER if the ensemble (mean over GA seeds) beats it in >= 2 of 3 folds and on the
mean delta. Final: weights on dev4 (GA seeds pooled, flat choice); the most recent year computed once (R2 alone: 5.655, known).

  python research/parallel/rounds/parallel-20260906-r2/v327/v327_bot_subaccount_ensemble.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
EPOP, EGENS = 40, 40


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v306 = _load("v306_e", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu = v306.W["eu"]
    sim0, cap = eu.simulate, {}

    def sim_capture(*a, **k):
        po = {}
        r = sim0(*a, path_out=po, **k)
        cap["p"] = po
        return r

    names = list(v306.SEEDS)
    C, full_runs = [], {}
    for n in names:
        eu.simulate = sim_capture
        try:
            r = v306.run_genome(v306.encode(v306.SEEDS[n]), True)  # 5 years: the paths are needed for the final score only once
        finally:
            eu.simulate = sim0
        p = cap["p"]
        C.append(dict(name=n, eq=p["eq"], eq_min=p["eq_min"], eq_max=p["eq_max"], years=r["years"]))
        log(f"candidate {n} dev4 {v306.metrics(r, [0, 1, 2, 3])}")
    idx, anchors = v306.W["idx"], v306.W["anchors"]
    yb = []
    for a0 in anchors:
        mk = np.asarray((idx >= a0) & (idx < a0 + pd.Timedelta(days=365)))
        yb.append((int(np.argmax(mk)), mk))

    def ens(w, ys):
        w = np.asarray(w, float) / sum(w)
        out = {"years": [None] * 5}
        for y in ys:
            first, mk = yb[y]
            act = [(wi, c) for wi, c in zip(w, C) if wi > 0]
            base = lambda c: c["eq"][first - 1] if first > 0 else 1.0
            e = sum(wi * c["eq"][mk] / base(c) for wi, c in act)
            em = sum(wi * c["eq_min"][mk] / base(c) for wi, c in act)
            ex = sum(wi * c["eq_max"][mk] / base(c) for wi, c in act)
            peak = np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, ex)]))[1:]
            dd, net = float(np.max(1 - np.minimum(e, em) / peak)), float(e[-1] - 1)
            agg = {k: sum(c["years"][y][k] for _, c in act) for k in ("n_book", "w_book", "n_rung", "w_rung")}
            out["years"][y] = dict(net=round(100 * net, 2), monthly=round(100 * ((1 + net) ** (1 / 12) - 1), 3), dd=round(100 * dd, 2), **agg)
        return out

    for c in C[:3]:  # one member alone must equal the engine's yearly numbers
        one = ens([1 if x is c else 0 for x in C], [0, 1, 2, 3])
        assert all(abs(one["years"][y]["net"] - c["years"][y]["net"]) < 0.02 and abs(one["years"][y]["dd"] - c["years"][y]["dd"]) < 0.02 for y in range(4))

    fit = lambda w, ys: v306.fitness(ens(w, ys), ys)
    n = len(C)

    def evolve(ys, seed):
        rng = random.Random(seed)
        pop = [tuple(1 if j == i else 0 for j in range(n)) for i in range(n)] + [tuple([1] * n)]
        while len(pop) < EPOP:
            pop.append(tuple(rng.choice((0, 0, 0, 1, 2)) for _ in range(n)))
        pop = [p for p in dict.fromkeys(pop) if sum(p) > 0]
        F = {p: fit(p, ys) for p in pop}
        for _ in range(EGENS):
            kids = []
            while len(kids) < EPOP:
                p1, p2 = (max(rng.sample(pop, 3), key=lambda x: F[x]) for _ in range(2))
                c = [a if rng.random() < 0.5 else b for a, b in zip(p1, p2)]
                for q in range(n):
                    if rng.random() < 2 / n:
                        c[q] = min(max(c[q] + rng.choice((-1, 1)), 0), 4)
                c = tuple(c)
                if sum(c) > 0 and c not in F and c not in kids:
                    kids.append(c)
            for c in kids:
                F[c] = fit(c, ys)
            pop = sorted(set(pop) | set(kids), key=lambda x: -F[x])[:EPOP]
        return F

    def flat(F, ys, seed):
        rng = random.Random(seed)
        top = sorted(F, key=lambda x: -F[x])[:10]
        fl = {}
        for p in top:
            nb = []
            while len(nb) < 8:
                q = rng.randrange(n)
                c = list(p)
                c[q] = min(max(c[q] + rng.choice((-1, 1)), 0), 4)
                c = tuple(c)
                if sum(c) > 0 and c != p and c not in nb:
                    nb.append(c)
            fl[p] = float(np.mean([fit(x, ys) for x in [p] + nb]))
        return max(fl, key=lambda x: fl[x]), fl

    out = {"version": "v327", "candidates": names, "folds": {}}
    deltas, wins = [], 0
    for k in (1, 2, 3):
        ys = list(range(k))
        single = max(range(n), key=lambda i: fit(tuple(1 if j == i else 0 for j in range(n)), ys))
        f_single = fit(tuple(1 if j == single else 0 for j in range(n)), [k])
        runs = {}
        for sd in (3271, 3272):
            F = evolve(ys, sd + 100 * k)
            w, _ = flat(F, ys, sd + 100 * k + 7)
            runs[sd] = dict(w={names[i]: w[i] for i in range(n) if w[i]}, F_test=round(fit(w, [k]), 4),
                            test=v306.metrics(ens(w, [k]), [k]), train=v306.metrics(ens(w, ys), ys))
            log(f"FOLD {k} seed {sd} w {runs[sd]['w']} TEST {runs[sd]['test']} F {runs[sd]['F_test']} | best single {names[single]} F {f_single:.4f}")
        d = float(np.mean([r["F_test"] for r in runs.values()])) - f_single
        deltas.append(d)
        wins += int(d > 0)
        out["folds"][k] = dict(runs=runs, best_single=names[single], F_single=round(f_single, 4), delta=round(d, 4))
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], wins=wins, holds=bool(wins >= 2 and np.mean(deltas) > 0))
    log(f"TRANSFER {out['transfer']}")
    ys = [0, 1, 2, 3]
    Fall = {}
    for sd in (3271, 3272):
        Fall.update(evolve(ys, sd + 400))
    w, fl = flat(Fall, ys, 3279)
    out["final"] = dict(w={names[i]: w[i] for i in range(n) if w[i]}, dev4=v306.metrics(ens(w, ys), ys), F_neigh=round(fl[w], 4),
                        last_year=v306.metrics(ens(w, [4]), [4]), five_years=v306.metrics(ens(w, [0, 1, 2, 3, 4]), [0, 1, 2, 3, 4]),
                        recommended=out["transfer"]["holds"])
    log(f"FINAL {out['final']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v327_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
