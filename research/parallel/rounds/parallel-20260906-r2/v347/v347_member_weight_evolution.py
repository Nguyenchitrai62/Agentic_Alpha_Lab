"""v347: EVOLVED BOOK-MEMBER WEIGHTS under the deployed MANUAL structure M3 (registry v347, registered before running; parent v342-v346).

User suggestion (2026-10-02): combine many promising solutions with weights found by evolutionary computation instead of fixed mixes. Earlier GAs
(v306-v310, v313) searched member weights TOGETHER with leverage / management genes and every final picked leverage that failed the most recent
year. v347 evolves ONLY the weights of the nine audited walk-forward book members; the trade structure and the risk level stay fixed at the deployed
MANUAL pipeline M3 (v342 L2 on CB books): pullback entry 0.75 sigma_4h valid 3 bars, v216 grid in position, SL 4 / TP 8 sigma_d, target 0.25,
cap 2, book_mult 0.75, two bracket dip limits at 3.0 / 4.0 sigma_4h (size_mult 4.375, exchange-native touch stop 8 sigma, budget 0.26 at 8 sigma,
sleeve_start 16, R2 agents' size / TP at the bar open from the v306 fit-"U" tables), engine_user costs.
GENOME: integer weights 0..4 for A (O1 orders), B (TV), D (Coinbase premium), P (path label PA), W (whale flow), T (TV annual A), PB (path B),
Dt (TV D), PT (pooled 77-coin TV member, v317); books = sum(w_m X_m) / sum(w_m) (at least one weight > 0). 5^9 genomes.
FITNESS (MANUAL): v310 fitness_pooled with the book win rate replaced by the all-trade win rate (book + dip fills); training F_train(Ys) =
0.5 * min_y F({y}) + 0.5 * F(Ys) (v310 robust form). Single-year test scores use F({y}).
SEEDS: CB (A2 B2 D1 = the deployed M3), M2 (A2 PT2 D1), T3-like (A2 B2 D1 T1), W2-like (+W1), P1-like (+P1), equal (all 1), A-only (A1),
PT-heavy (A1 PT2 D1); the rest of the population = seeds with three random gene changes.
GA: population 20, 10 generations, 20 children each (tournament 3, uniform crossover, per-gene mutation 2/9 to a neighbour value, 20% any value),
(mu + lambda) survival; winner of a run = flat choice (the five best distinct genomes, each with six random one-gene neighbours; the highest
neighbourhood mean of F_train wins).
PROTOCOL (fixed before running):
  part "folds": GA on dev years [:k] for k = 2, 3 (GA seed 3471 + k); winner W_k scored on dev year k vs the deployed CB seed.
    TRANSFER holds if F_test(W_k) > F_test(CB) in BOTH folds.
  part "final": GA on all four dev years (GA seed 3475) -> M (flat choice); the most recent year is computed ONCE for M (full run).
  M replaces the deployed M3 books only if TRANSFER holds and F_train(dev4, M) > F_train(dev4, CB). Contaminated by design (the member set and the
  M3 structure were built after earlier looks at the most recent year): prospective paper log = clean evidence.
Runs on Kaggle CPU (kpack: same audited engine / inputs; the CB seed must reproduce dev4 6.233), parts split over the two accounts.

  python research/parallel/rounds/parallel-20260906-r2/v347/v347_member_weight_evolution.py --part folds|final [--workers 4]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import random
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
AG = dict(fit="U", up_th=2.0, up_mult=1.5, dn_th=0.0, dn_mult=0.5, tp_margin=0.001)
MEM = ("wA", "wB", "wD", "wP", "wW", "wT", "wPB", "wDt", "wPT")
GENES = [(n, (0, 1, 2, 3, 4)) for n in MEM]
SEEDS = {"CB": dict(wA=2, wB=2, wD=1), "M2": dict(wA=2, wD=1, wPT=2), "T3": dict(wA=2, wB=2, wD=1, wT=1), "W2": dict(wA=2, wB=2, wD=1, wW=1),
         "P1": dict(wA=2, wB=2, wD=1, wP=1), "equal": {n: 1 for n in MEM}, "A_only": dict(wA=1), "PT_heavy": dict(wA=1, wD=1, wPT=2)}
POP, GENS, KIDS = 20, 10, 20
W = {}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def encode(d):
    return tuple(int(d.get(n, 0)) for n in MEM)


def valid(g):
    return sum(g) > 0


def init_worker():
    v306 = _load("v306_w", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    size, tp = v306._tables(AG)
    for k in ("prep", "books154", "T"):  # free the BOT-side arrays; v310 loads its own engine inputs
        v306.W.pop(k, None)
    v310 = _load("v310_w", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_w", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    C = W0["eu"].er.CACHE
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    X = dict(W0["grp"])
    X["wPT"] = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    W.update(v306=v306, v310=v310, v315=v315, size=size, tp=tp, X={n: X[n].copy() for n in MEM}, base_p9=v310._policy9)


def run_genome(g, full=False):
    v306, v310, v315, W0 = W["v306"], W["v310"], W["v315"], W["v310"].W
    eu = W0["eu"]
    size, tp = W["size"], W["tp"]
    kus = [U.index(k) for k in (3.0, 4.0)]
    books = sum(w * W["X"][n] for n, w in zip(MEM, g)) / sum(g)
    keep = {n: v for n, v in W0["grp"].items()}
    for n in W0["grp"]:
        W0["grp"][n] = np.zeros_like(books)
    W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = books
    v310._policy9 = v315.with_entry(0.75)
    v315.BASE_P9 = W["base_p9"]
    sim0 = eu.simulate
    RUNG = {}

    def sim(*a, **kw):
        kw.update(sleeve=True, rungs=(3.0, 4.0), sleeve_stop_mode="touch", m_sleeve_sl=8.0, sleeve_risk_budget=0.26, size_mult=4.375,
                  align=(1.5, 0.5), sleeve_start=16,
                  sleeve_fill_size=lambda i, aa, r, f: float(size[i, aa, kus[r]]), sleeve_tp=lambda i, aa, r, f: float(tp[i, aa, kus[r]]))
        kw["trade"] = dict(kw["trade"], book_mult=0.75)
        out = sim0(*a, **kw)
        rows = v306._trade_rows(kw["events"])
        for y in range(5):
            a0 = W0["anchors"][y]
            rg = [x[2] for x in rows if x[0] == "rung" and a0 <= x[1] < a0 + pd.Timedelta(days=365)]
            RUNG[y] = (len(rg), int(sum(v > 0 for v in rg)))
        return out
    eu.simulate = sim
    try:
        res = v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
    finally:
        eu.simulate = sim0
        v310._policy9 = W["base_p9"]
        W0["grp"].update(keep)
    for y, yy in enumerate(res["years"]):
        yy["n_rung"], yy["w_rung"] = RUNG[y]
    res["g"] = list(g)
    return res


def metrics(res, ys):
    return W_metrics(res, ys)


def W_metrics(res, ys):
    yy = [res["years"][y] for y in ys]
    R = 100 * (np.prod([1 + y["net"] / 100 for y in yy]) ** (1 / (12 * len(yy))) - 1)
    n = sum(y["n_book"] + y["n_rung"] for y in yy)
    nb = sum(y["n_book"] for y in yy)
    return dict(R=round(R, 3), W=round(min(y["monthly"] for y in yy), 3), DD=round(max(y["dd"] for y in yy), 2),
                win=round(sum(y["w_book"] + y["w_rung"] for y in yy) / max(n, 1), 4), win_book=round(sum(y["w_book"] for y in yy) / max(nb, 1), 4),
                trades=n, losing=sum(y["net"] < 0 for y in yy))


def f_single(res, ys):
    """v310 fitness_pooled with the all-trade win rate in place of the book win rate."""
    m = W_metrics(res, ys)
    g1 = np.minimum([m["R"] / 5, 20 / max(m["DD"], 1e-6), m["win"] / 0.55, min(1.0, 1 + m["W"] / 2)], 1.0)
    if g1.min() < 1:
        return float(0.7 * g1.min() + 0.3 * g1.mean())
    g2 = np.minimum([m["R"] / 8, 15 / max(m["DD"], 1e-6), m["win"] / 0.60], 1.2)
    return float(1 + 0.25 * g2.min() + 0.75 * g2.mean())


def fitness(res, ys):
    if len(ys) == 1:
        return f_single(res, ys)
    return float(0.5 * min(f_single(res, [y]) for y in ys) + 0.5 * f_single(res, ys))


class Evaluator:
    def __init__(self, pool, path):
        self.pool, self.path, self.cache = pool, path, {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    x = json.loads(line)
                    self.cache[tuple(x["g"])] = x

    def __call__(self, genomes):
        todo = list({g for g in genomes if g not in self.cache})
        for x in self.pool.imap_unordered(run_genome, todo):
            self.cache[tuple(x["g"])] = x
            with self.path.open("a") as fh:
                fh.write(json.dumps(x, default=str) + "\n")
        return [self.cache[g] for g in genomes]


def mutate(g, rng):
    g = list(g)
    for q in range(len(GENES)):
        if rng.random() < 2 / len(GENES):
            g[q] = rng.randrange(5) if rng.random() < 0.2 else min(max(g[q] + rng.choice((-1, 1)), 0), 4)
    return tuple(g)


def evolve(ev, ys, seed, log):
    rng = random.Random(seed)
    seeds = [encode(v) for v in SEEDS.values()]
    pop = list(dict.fromkeys(seeds))
    while len(pop) < POP:
        c = rng.choice(seeds)
        for _ in range(3):
            c = mutate(c, rng)
        if valid(c) and c not in pop:
            pop.append(c)
    fit = {g: fitness(r, ys) for g, r in zip(pop, ev(pop))}
    for gen in range(GENS):
        kids = []
        while len(kids) < KIDS:
            p1, p2 = (max(rng.sample(pop, 3), key=lambda x: fit[x]) for _ in range(2))
            c = mutate(tuple(a if rng.random() < 0.5 else b for a, b in zip(p1, p2)), rng)
            if valid(c) and c not in fit and c not in kids:
                kids.append(c)
        for g, r in zip(kids, ev(kids)):
            fit[g] = fitness(r, ys)
        pop = sorted(set(pop) | set(kids), key=lambda x: -fit[x])[:POP]
        log(f"  years {ys} gen {gen} best {fit[pop[0]]:.4f} {pop[0]} median {np.median([fit[x] for x in pop]):.4f} evals {len(fit)}")
    return fit


def flat_choice(ev, fit, ys, rng, log):
    top = sorted(fit, key=lambda x: -fit[x])[:5]
    flat = {}
    for g in top:
        nb = []
        while len(nb) < 6:
            c = list(g)
            q = rng.randrange(len(GENES))
            c[q] = rng.choice([v for v in range(5) if v != g[q]])
            c = tuple(c)
            if valid(c) and c not in nb:
                nb.append(c)
        flat[g] = float(np.mean([fitness(r, ys) for r in ev([g] + nb)]))
        log(f"  flat {g} F {fit[g]:.4f} neighbourhood {flat[g]:.4f}")
    return max(flat, key=lambda x: flat[x])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("folds", "final"), required=True)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    logf = (HERE / f"evolution_{args.part}.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    pool = mp.Pool(args.workers, initializer=init_worker)
    ev = Evaluator(pool, HERE / f"eval_cache_{args.part}.jsonl")
    seeds = {k: encode(v) for k, v in SEEDS.items()}
    sres = dict(zip(seeds, ev(list(seeds.values()))))
    m4 = W_metrics(sres["CB"], [0, 1, 2, 3])
    log(f"CB seed dev4 {m4}")
    assert abs(m4["R"] - 6.233) < 0.003, m4  # the deployed M3 (backend/history_tm.py "v342")
    out = {"version": "v347", "part": args.part, "seed_dev4": {k: dict(W_metrics(r, [0, 1, 2, 3]), F=round(fitness(r, [0, 1, 2, 3]), 4))
                                                               for k, r in sres.items()}}
    for k, v in out["seed_dev4"].items():
        log(f"seed {k} {v}")
    if args.part == "folds":
        out["folds"] = {}
        for k in (2, 3):
            ys = list(range(k))
            fit = evolve(ev, ys, 3471 + k, log)
            w = flat_choice(ev, fit, ys, random.Random(3481 + k), log)
            rw = ev([w])[0]
            out["folds"][k] = dict(winner=dict(zip(MEM, w)), train=dict(W_metrics(rw, ys), F=round(fitness(rw, ys), 4)),
                                   test=dict(W_metrics(rw, [k]), F=round(f_single(rw, [k]), 4)),
                                   cb_test=dict(W_metrics(sres["CB"], [k]), F=round(f_single(sres["CB"], [k]), 4)))
            log(f"FOLD {k} winner {w} TEST {out['folds'][k]['test']} vs CB {out['folds'][k]['cb_test']}")
        out["transfer"] = bool(all(out["folds"][k]["test"]["F"] > out["folds"][k]["cb_test"]["F"] for k in (2, 3)))
        log(f"TRANSFER {out['transfer']}")
    else:
        ys = [0, 1, 2, 3]
        fit = evolve(ev, ys, 3475, log)
        M = flat_choice(ev, fit, ys, random.Random(3485), log)
        rM = ev([M])[0]
        full = pool.apply(run_genome, (M, True))
        out["final"] = dict(M=dict(zip(MEM, M)), dev4=dict(W_metrics(rM, ys), F=round(fitness(rM, ys), 4)),
                            beats_cb_dev4=bool(fitness(rM, ys) > fitness(sres["CB"], ys)), last_year=W_metrics(full, [4]),
                            five_years=W_metrics(full, [0, 1, 2, 3, 4]),
                            full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
        log(f"FINAL {json.dumps(out['final'], default=str)}")
    pool.close()
    raw = json.dumps(out, indent=1, default=str)
    (HERE / f"v347_result_{args.part}.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
