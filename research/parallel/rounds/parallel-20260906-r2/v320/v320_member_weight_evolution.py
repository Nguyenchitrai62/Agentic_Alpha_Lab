"""v320: MANUAL product - walk-forward EVOLUTION OF MEMBER WEIGHTS only (registry v320), rules fixed at the general MANUAL setting.

User 2026-10-02: weight many promising solutions with evolutionary computation instead of a fixed 80/20. v307-v313 evolved 20-28 genes and the
dev-fitted leverage / rule genes did not generalise; the member books (signals) are walk-forward by construction and their mix is the
low-dimensional, information-carrying part. v320 evolves ONLY the integer weights 0..4 of nine walk-forward member groups (normalised), with
the trade rules fixed at the general MANUAL setting found so far (v315 pullback entry 0.75 sigma_4h / 3 bars, G2 grid trader, SL 4 / TP 8 sigma_d,
target 0.25, cap 2 - the AGENTS leverage baseline):
  A  = O1 order-flow + TV (A + Aq)/2        B  = TV (B + Bq)/2          D  = Coinbase premium (D + Dq)/2      W = whale W2 (A_whale + Aq_whale)/2
  P  = path label O1 (PA + PAq)/2           PT = pooled TV (v317)        PP = pooled path-label TV (v319)       PF = pooled TV + flow (v319)
  G  = GP alphas (v312)
SEEDS: base (A2 B2 D1), v317 M2 (A2 PT2 D1), v319 rows X1..X3, equal weights, every single member alone.
GA: population 24, 15 generations, 24 children, tournament 3, uniform crossover, mutation +-1 per weight with probability 2/9, (mu + lambda);
fitness = v310 robust MANUAL fitness (0.5 worst single year + 0.5 pooled on the training years; MANUAL floor first, then goal 2 easiest first);
fold winner and final = flat-neighbourhood choice (top 10, 8 neighbours with one weight +-1). GA seeds 3201 / 3202.
PROTOCOL: folds k = 2, 3 -> winner scored on year k vs the best SEED on years [:k] (scored on year k); TRANSFER if the delta (mean over GA seeds) > 0
in both folds. Final on dev4 (both GA seeds pooled, flat choice); the most recent year computed once (the rule setting and members were shaped with
knowledge of the most recent year -> contaminated; the prospective log is the clean evidence).

  python research/parallel/rounds/parallel-20260906-r2/v320/v320_member_weight_evolution.py [--workers 3]
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
C = Path("artifacts/research/engine_real")
NAMES = ("A", "B", "D", "W", "P", "PT", "PP", "PF", "G")
POP, GENS, KIDS = 24, 15, 24


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seeds():
    s = {"base": dict(A=2, B=2, D=1), "M2": dict(A=2, PT=2, D=1), "X1": dict(A=2, PT=2, D=1, PP=1), "X2": dict(PF=2, PT=2, D=1),
         "X3": dict(PF=2, PT=2, D=1, PP=1), "equal": {n: 1 for n in NAMES}}
    s.update({f"only_{n}": {n: 1} for n in NAMES})
    return {k: tuple(v.get(n, 0) for n in NAMES) for k, v in s.items()}


W = {}


def init_worker():
    v310 = _load("v310_w", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_w", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    g = {"A": W0["grp"]["wA"], "B": W0["grp"]["wB"], "D": W0["grp"]["wD"], "W": W0["grp"]["wW"], "P": W0["grp"]["wP"],
         "PT": (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2,
         "PP": (rd("member_PP_pooled.parquet") + rd("member_PPq_pooled.parquet")) / 2,
         "PF": (rd("member_PF_pooled.parquet") + rd("member_PFq_pooled.parquet")) / 2,
         "G": (rd("member_G_gp.parquet") + rd("member_Gq_gp.parquet")) / 2}
    W.update(v310=v310, v315=v315, g={k: v.copy() for k, v in g.items()}, base_p9=v310._policy9)


def run_w(w, full=False):
    v310, v315 = W["v310"], W["v315"]
    mix = sum(wi * W["g"][n] for wi, n in zip(w, NAMES)) / sum(w)
    G = v310.W["grp"]
    G["wA"] = G["wB"] = G["wD"] = mix  # genome weights (2, 2, 1) normalise to exactly the mix
    v310._policy9 = v315.with_entry(0.75)
    v315.BASE_P9 = W["base_p9"]
    try:
        r = v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
    finally:
        v310._policy9 = W["base_p9"]
    r["g"] = list(w)
    return r


class Ev:
    def __init__(self, pool, path):
        self.pool, self.path, self.cache = pool, path, {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    x = json.loads(line)
                    self.cache[tuple(x["g"])] = x

    def __call__(self, ws):
        todo = list({w for w in ws if w not in self.cache})
        for x in self.pool.imap_unordered(run_w, todo):
            self.cache[tuple(x["g"])] = x
            with self.path.open("a") as fh:
                fh.write(json.dumps({k: x[k] for k in ("g", "years")}) + "\n")
        return [self.cache[w] for w in ws]


def neighbours(w, rng, n=8):
    out = []
    while len(out) < n:
        q = rng.randrange(len(w))
        c = list(w)
        c[q] = min(max(c[q] + rng.choice((-1, 1)), 0), 4)
        c = tuple(c)
        if sum(c) > 0 and c != w and c not in out:
            out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    logf = (HERE / "evolution.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v310 = _load("v310_m", RD / "v310/v310_manual_book_robust_evolution.py")
    fit = v310.fitness
    met = v310.metrics
    pool = mp.Pool(args.workers, initializer=init_worker)
    ev = Ev(pool, HERE / "eval_cache.jsonl")
    S = seeds()
    sres = dict(zip(S, ev(list(S.values()))))
    m2 = met(sres["M2"], [0, 1, 2, 3])
    assert abs(m2["R"] - 3.011) < 0.003, m2
    for k, r in sres.items():
        log(f"seed {k} {S[k]} dev4 {met(r, [0, 1, 2, 3])} F {fit(r, [0, 1, 2, 3]):.4f}")

    def evolve(ys, seed):
        rng = random.Random(seed)
        pop = list(S.values())
        while len(pop) < POP:
            pop.append(tuple(rng.choice((0, 0, 1, 2)) for _ in NAMES))
        pop = [p for p in dict.fromkeys(pop) if sum(p) > 0]
        F = {p: fit(r, ys) for p, r in zip(pop, ev(pop))}
        for gen in range(GENS):
            kids = []
            while len(kids) < KIDS:
                p1, p2 = (max(rng.sample(pop, 3), key=lambda x: F[x]) for _ in range(2))
                c = [a if rng.random() < 0.5 else b for a, b in zip(p1, p2)]
                for q in range(len(c)):
                    if rng.random() < 2 / len(NAMES):
                        c[q] = min(max(c[q] + rng.choice((-1, 1)), 0), 4)
                c = tuple(c)
                if sum(c) > 0 and c not in F and c not in kids:
                    kids.append(c)
            for c, r in zip(kids, ev(kids)):
                F[c] = fit(r, ys)
            pop = sorted(set(pop) | set(kids), key=lambda x: -F[x])[:POP]
            log(f"  seed {seed} years {ys} gen {gen} best {F[pop[0]]:.4f} {pop[0]}")
        return F

    def flat(F, ys, seed):
        rng = random.Random(seed + 7)
        top = sorted(F, key=lambda x: -F[x])[:10]
        fl = {w: float(np.mean([fit(r, ys) for r in ev([w] + neighbours(w, rng))])) for w in top}
        return max(fl, key=lambda x: fl[x]), fl

    out = {"version": "v320", "names": NAMES, "seeds": {k: dict(w=S[k], dev4=met(r, [0, 1, 2, 3])) for k, r in sres.items()}, "folds": {}}
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        bs = max(S, key=lambda s: fit(sres[s], ys))
        f_bs = fit(sres[bs], [k])
        runs = {}
        for sd in (3201, 3202):
            F = evolve(ys, sd + 1000 * k)
            w, _ = flat(F, ys, sd + 1000 * k)
            r = ev([w])[0]
            runs[sd] = dict(w=w, train=met(r, ys), test=met(r, [k]), F_test=round(fit(r, [k]), 4))
            log(f"FOLD {k} seed {sd} w {dict(zip(NAMES, w))} TEST {runs[sd]['test']} F {runs[sd]['F_test']} | best seed {bs} F {f_bs:.4f}")
        d = float(np.mean([x["F_test"] for x in runs.values()])) - f_bs
        out["folds"][k] = dict(runs=runs, best_seed=bs, best_seed_test=met(sres[bs], [k]), F_best_seed=round(f_bs, 4), delta=round(d, 4))
        deltas.append(d)
        log(f"FOLD {k} delta {d:.4f}")
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ys = [0, 1, 2, 3]
    Fall = {}
    for sd in (3201, 3202):
        Fall.update(evolve(ys, sd + 4000))
    w, fl = flat(Fall, ys, 4320)
    full = pool.apply(run_w, (w, True))
    out["final"] = dict(w=dict(zip(NAMES, w)), dev4=met(ev([w])[0], ys), F_neigh=round(fl[w], 4), last_year=met(full, [4]),
                        five_years=met(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")},
                        recommended=out["transfer"]["holds"])
    log(f"FINAL w {out['final']['w']} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    pool.close()
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v320_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
