"""v311: MANUAL product - EVOLVED SUB-ACCOUNT ENSEMBLE of many walk-forward-evolved book pipelines (registry v311).

User 2026-10-02: combine many promising solutions with weights found by evolutionary computation instead of a fixed mix. v307-v310 produce,
in every walk-forward fold, a whole POPULATION of book configurations evolved on the years before the test year; a single winner of a 20-27 gene
search is noisy (v307: fold 2 transfers, fold 3 does not). Splitting capital across several good configurations (separate sub-accounts, each a
complete MANUAL pipeline a human or a bot can follow; rebalanced to the weights once a year at the anchor) diversifies the rule noise.

CANDIDATE POOL (walk-forward, no look-ahead): for test year k the pool = the seeds of each source version + the TOP_N genomes (by the v310 robust
training fitness on years [:k]) of each GA run that version made FOR THAT FOLD (fitness on years [:k] only). The GA runs are replayed exactly from
the versions' eval caches (deterministic given their seeds), so the pool never contains a genome produced by a search that saw year k. For the
final (most recent year) the pool comes from the dev4 runs.
Sources: v308 (leverage / governor / short / break-even), v309 (+ management genes), v310 (robust choice); v307 if available (same protocol).
ENSEMBLE GENOME: integer weight 0..4 per pool member (normalised; >= 1 member). Per year y (anchor to anchor) the combined sub-account equity is
  e(t) = sum_k w_k eq_k(t) / eq_k(start of y),   1m-marked e_min(t) = sum_k w_k eq_min_k(t) / eq_k(start of y)   (sum of per-account minima:
  conservative; peaks from the summed 1m maxima, as engine_user summarize), net_y = e(end) - 1, DD_y = max(1 - min(e, e_min) / running max); trades = all book trades of the members with w > 0 (each counted once).
FITNESS = the v310 robust MANUAL fitness on those metrics (goal-1 floor first: R / 5, 20 / DD, book win / 0.55, no losing year; then goal 2
easiest first), training on years [:k]. GA: population 40, 40 generations, tournament 3, uniform crossover, mutation 2 / n (+-1 weight),
(mu + lambda); flat-neighbourhood choice (top 10, 8 one-weight neighbours). GA seeds 3111 / 3112.
PROTOCOL (fixed before running): folds k = 2, 3: ensemble E_k scored on year k against (a) the best seed (as v307-v310) and (b) the single flat
winner of the source run with the highest training fitness. ENSEMBLE TRANSFER holds if F_test(E_k) - F_test(best seed) > 0 in both folds AND
mean over folds of F_test(E_k) - F_test(single winner) > 0. Final: pool from the dev4 runs, weights on dev4, flat choice; the most recent year
is scored once for the final ensemble only.

  python research/parallel/rounds/parallel-20260906-r2/v311/v311_evolved_subaccount_ensemble.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import random
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
TOP_N = 8
SOURCES = {  # version: (script, fold GA seeds, final GA seeds)
    "v307": ("v307/v307_manual_book_evolution.py", (307, 308), (307, 308, 309)),
    "v308": ("v308/v308_manual_book_leverage_evolution.py", (318, 328), (318, 328, 338)),
    "v309": ("v309/v309_manual_book_management_evolution.py", (319, 329), (319, 329, 339)),
    "v310": ("v310/v310_manual_book_robust_evolution.py", (3101, 3102), (3101, 3102, 3103)),
}
EPOP, EGENS = 40, 40


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v310 = _load("v310_e", RD / "v310/v310_manual_book_robust_evolution.py")


class Replay:
    """Cache-backed evaluator for one source version; misses are simulated in-process (never expected for a replay)."""

    def __init__(self, mod, cache_path, extra_path):
        self.mod, self.cache, self.misses, self.extra = mod, {}, 0, extra_path
        for p in (cache_path, extra_path):
            if p.exists():
                for line in p.read_text().splitlines():
                    if line.strip():
                        x = json.loads(line)
                        self.cache[tuple(x["g"])] = x

    def __call__(self, genomes):
        out = []
        for g in genomes:
            if g not in self.cache:
                self.misses += 1
                self.cache[g] = self.mod.run_genome(g)
                with self.extra.open("a") as fh:
                    fh.write(json.dumps(self.cache[g]) + "
")
            out.append(self.cache[g])
        return out


def main():
    logf = (HERE / "ensemble.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    mods, evs = {}, {}
    shared = None
    for v, (path, _, _) in SOURCES.items():
        cache = RD / v / "eval_cache.jsonl"
        if not cache.exists():
            log(f"source {v}: no eval cache -> skipped")
            continue
        m = _load("src_" + v, RD / path)
        if shared is None:
            m.init_worker()
            shared = m.W
        else:
            m.W.update(shared)
            m.v306.W.update(eu=shared["eu"])
        mods[v], evs[v] = m, Replay(m, cache, HERE / f"extra_cache_{v}.jsonl")
    eu = shared["eu"]
    sim0 = eu.simulate
    cap = {}

    def sim_capture(*a, **k):
        po = {}
        r = sim0(*a, path_out=po, **k)
        cap["path"] = po
        return r

    def candidate(v, g):
        """per-year trades from the cache, per-bar equity paths from one re-simulation (results asserted equal to the cache)."""
        eu.simulate = sim_capture
        try:
            r = mods[v].run_genome(g)
        finally:
            eu.simulate = sim0
        c = evs[v].cache[tuple(g)]
        assert [y["net"] for y in r["years"]] == [y["net"] for y in c["years"]], (v, g)
        return dict(v=v, g=list(g), eq=cap["path"]["eq"], eq_min=cap["path"]["eq_min"], eq_max=cap["path"]["eq_max"], years=c["years"])

    idx = shared["idx"]
    anchors = shared["anchors"]
    yb = []
    for a0 in anchors:
        mk = np.asarray((idx >= a0) & (idx < a0 + pd.Timedelta(days=365)))
        first = int(np.argmax(mk))
        yb.append((first, mk))

    def ens_metrics(cands, w, ys, years_override=None):
        w = np.asarray(w, float)
        w = w / w.sum()
        yy = []
        for y in ys:
            first, mk = yb[y]
            base = lambda c: c["eq"][first - 1] if first > 0 else 1.0  # = engine_user summarize
            e = sum(wi * c["eq"][mk] / base(c) for wi, c in zip(w, cands) if wi > 0)
            em = sum(wi * c["eq_min"][mk] / base(c) for wi, c in zip(w, cands) if wi > 0)
            ex = sum(wi * c["eq_max"][mk] / base(c) for wi, c in zip(w, cands) if wi > 0)
            peak = np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, ex)]))[1:]
            dd = float(np.max(1 - np.minimum(e, em) / peak))
            net = float(e[-1] - 1)
            nb = sum(c["years"][y]["n_book"] for wi, c in zip(w, cands) if wi > 0)
            wb = sum(c["years"][y]["w_book"] for wi, c in zip(w, cands) if wi > 0)
            yy.append(dict(net=round(100 * net, 2), monthly=round(100 * ((1 + net) ** (1 / 12) - 1), 3), dd=round(100 * dd, 2), n_book=nb, w_book=wb,
                           n_rung=0, w_rung=0))
        return dict(years={y: v for y, v in zip(ys, yy)})

    def efit(cands, w, ys):
        r = ens_metrics(cands, w, ys)
        res = {"years": [r["years"].get(y, None) for y in range(max(ys) + 1)]}
        return v310.fitness(res, ys), res

    def evolve_w(cands, ys, seed):
        rng = random.Random(seed)
        n = len(cands)
        pop = [tuple(1 if j == i else 0 for j in range(n)) for i in range(n)][:EPOP // 2] + [tuple([1] * n)]
        while len(pop) < EPOP:
            pop.append(tuple(rng.choice((0, 0, 0, 1, 2)) for _ in range(n)))
        pop = [p for p in dict.fromkeys(pop) if sum(p) > 0]
        fit = {p: efit(cands, p, ys)[0] for p in pop}
        for _ in range(EGENS):
            kids = []
            while len(kids) < EPOP:
                p1, p2 = (max(rng.sample(pop, 3), key=lambda x: fit[x]) for _ in range(2))
                c = [a if rng.random() < 0.5 else b for a, b in zip(p1, p2)]
                for q in range(n):
                    if rng.random() < 2 / n:
                        c[q] = min(max(c[q] + rng.choice((-1, 1)), 0), 4)
                c = tuple(c)
                if sum(c) > 0 and c not in fit and c not in kids:
                    kids.append(c)
            for c in kids:
                fit[c] = efit(cands, c, ys)[0]
            pop = sorted(set(pop) | set(kids), key=lambda x: -fit[x])[:EPOP]
        top = sorted(fit, key=lambda x: -fit[x])[:10]
        flat = {}
        for p in top:
            nb = []
            while len(nb) < 8:
                q = rng.randrange(n)
                c = list(p)
                c[q] = min(max(c[q] + rng.choice((-1, 1)), 0), 4)
                c = tuple(c)
                if sum(c) > 0 and c != p and c not in nb:
                    nb.append(c)
            flat[p] = float(np.mean([efit(cands, x, ys)[0] for x in [p] + nb]))
        best = max(flat, key=lambda x: flat[x])
        return best, fit[best], flat[best]

    def pool_for(ys, fold_seeds_of, offset):
        cands, singles = [], []
        for v, m in mods.items():
            seeds = [m.encode(d) for d in m.SEEDS.values()]
            gen = set(seeds)
            for sd in fold_seeds_of(v):
                _, fit = m.evolve(evs[v], ys, sd + offset, lambda s: None)
                w, _ = v310_flat(m, evs[v], fit, ys, sd + offset)
                singles.append((v, w, fit))
                ranked = sorted(fit, key=lambda x: -v310.fitness(evs[v]([x])[0], ys))
                gen.update(ranked[:TOP_N])
            for g in gen:
                cands.append((v, g))
        return cands, singles

    def v310_flat(m, ev, fit, ys, sd):
        # the single flat winner of a source run under the v310 robust fitness (the v310 fold rule), for the comparison row
        rescored = {g: v310.fitness(ev([g])[0], ys) for g in fit}
        top = sorted(rescored, key=lambda x: -rescored[x])[:10]
        rng = random.Random(sd + 7)
        flat = {}
        for g in top:
            nb = []
            while len(nb) < 8:
                q = rng.randrange(len(m.GENES))
                c = list(g)
                c[q] = rng.choice([u for u in range(len(m.GENES[q][1])) if u != g[q]])
                c = tuple(c)
                if m.valid(c) and c not in nb:
                    nb.append(c)
            flat[g] = float(np.mean([v310.fitness(r, ys) for r in ev([g] + nb)]))
        return max(flat, key=lambda x: flat[x]), flat

    out = {"version": "v311", "sources": list(mods), "folds": {}, "final": {}}
    deltas_seed, deltas_single = [], []
    for k in (2, 3):
        ys = list(range(k))
        cands, singles = pool_for(ys, lambda v: SOURCES[v][1], 1000 * k)
        C = [candidate(v, g) for v, g in cands]
        log(f"fold {k}: pool {len(C)} candidates from {sorted(set(v for v, _ in cands))}; replay misses {sum(e.misses for e in evs.values())}")
        for c in C[:5]:  # the sub-account combination of ONE member must equal the engine's yearly numbers (training years only)
            one = ens_metrics([c], [1], ys)["years"]
            assert all(abs(one[y]["net"] - c["years"][y]["net"]) < 0.02 and abs(one[y]["dd"] - c["years"][y]["dd"]) < 0.02 for y in ys), (one, c["years"])
        if os.environ.get("V311_SMOKE"):
            log("smoke: pool built, single-member check passed; stopping before any ensemble fitness")
            return
        seedC = [c for c, (v, g) in zip(C, cands) if g in [mods[v].encode(d) for d in mods[v].SEEDS.values()]]
        bs = max(range(len(seedC)), key=lambda i: v310.fitness({"years": seedC[i]["years"]}, ys))
        bs_test = v310.fitness({"years": seedC[bs]["years"]}, [k])
        sv, sg, _ = max(singles, key=lambda t: v310.fitness(evs[t[0]]([t[1]])[0], ys))
        single_test = v310.fitness(evs[sv]([sg])[0], [k])
        runs = {}
        for sd in (3111, 3112):
            w, ftr, fl = evolve_w(C, ys, sd + 100 * k)
            fte, res = efit(C, w, [k])
            runs[sd] = dict(weights={f"{C[i]['v']}:{i}": w[i] for i in range(len(C)) if w[i]}, F_train=round(ftr, 4), F_neigh=round(fl, 4),
                            F_test=round(fte, 4), test=v310.metrics(res, [k]), train=v310.metrics(efit(C, w, ys)[1], ys))
            log(f"FOLD {k} ensemble seed {sd} members {sum(1 for x in w if x)} train {runs[sd]['train']} F {ftr:.4f} TEST {runs[sd]['test']} F {fte:.4f}")
        fe = float(np.mean([r["F_test"] for r in runs.values()]))
        out["folds"][k] = dict(runs=runs, best_seed_test_F=round(bs_test, 4), single=dict(v=sv, g=list(sg), test_F=round(single_test, 4),
                               test=v310.metrics(evs[sv]([sg])[0], [k])), delta_vs_seed=round(fe - bs_test, 4), delta_vs_single=round(fe - single_test, 4))
        deltas_seed.append(fe - bs_test)
        deltas_single.append(fe - single_test)
        log(f"FOLD {k} ensemble F {fe:.4f} vs best seed {bs_test:.4f} vs single winner ({sv}) {single_test:.4f}")
    transfer = bool(all(d > 0 for d in deltas_seed) and np.mean(deltas_single) > 0)
    out["transfer"] = dict(deltas_seed=[round(x, 4) for x in deltas_seed], deltas_single=[round(x, 4) for x in deltas_single], holds=transfer)
    log(f"ENSEMBLE TRANSFER {out['transfer']}")
    ys = [0, 1, 2, 3]
    cands, _ = pool_for(ys, lambda v: SOURCES[v][2], 4000)
    C = [candidate(v, g) for v, g in cands]
    w, ftr, fl = evolve_w(C, ys, 3119)
    res4 = efit(C, w, ys)[1]
    out["final"] = dict(pool=len(C), weights={f"{C[i]['v']}:{list(C[i]['g'])}": w[i] for i in range(len(C)) if w[i]}, F_dev4=round(ftr, 4),
                        F_neigh=round(fl, 4), dev4=v310.metrics(res4, ys), dev_years=res4["years"])
    # the most recent year: once, for the final ensemble only (members re-simulated with the full output)
    full = []
    for i in range(len(C)):
        if w[i]:
            v, g = C[i]["v"], tuple(C[i]["g"])
            eu.simulate = sim_capture
            try:
                r = mods[v].run_genome(g, True)
            finally:
                eu.simulate = sim0
            full.append((w[i], dict(C[i], years=r["years"], eq=cap["path"]["eq"], eq_min=cap["path"]["eq_min"], eq_max=cap["path"]["eq_max"])))
    resL = efit([c for _, c in full], [x for x, _ in full], [4])[1]
    resA = efit([c for _, c in full], [x for x, _ in full], [0, 1, 2, 3, 4])[1]
    out["final"]["last_year"] = v310.metrics(resL, [4])
    out["final"]["five_years"] = v310.metrics(resA, [0, 1, 2, 3, 4])
    out["final"]["recommended"] = transfer
    log(f"FINAL ensemble members {len(full)} dev4 {out['final']['dev4']} | 5y {out['final']['five_years']} | last year {out['final']['last_year']}"
        f" | recommended {transfer}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v311_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
