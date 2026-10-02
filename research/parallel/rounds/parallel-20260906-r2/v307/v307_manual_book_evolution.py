"""v307: MANUAL product (book orders only) - walk-forward evolution of the book components toward the user's floor (registry v307).

User 2026-10-02: the book (no dip ladder, a human can follow it) is scored on its own. GOAL 1 = MANDATORY floor, every metric: >= 5 %/month,
DD < 20%, win rate >= 55% (book trades); GOAL 2 = 8 %/month, DD < 15%, win >= 60%, easiest metric first. Today (research/diagnostics/
book_vs_bot, G2 books + rules, sleeve off): dev4 2.50 %/month, 2021 losing (-3.6%), dev DD 16.4, win ~50%; a higher vol target barely helps
(0.44: 2.76; cap 3: 2.91) - the binding limit is the trade structure / signal, not the risk dial. The book rules were tuned together with the dip
sleeve and never for the book alone; v307 searches the book space jointly with the v306 method.

ENGINE: engine_user trade mode, sleeve OFF (one resting limit per asset, minute-5 rule, SL market taker 0.055%, TP limit maker 0.02%, break-even,
grid adds / reduces at most once per cool-down, limit exit on signal loss, adverse funding longs 0.01%/8h, stop-first ties, 1m marks).
GENOME (20 genes, ranges from v208-v305):
  member weights 0..4 (cached walk-forward books, annual + quarterly averaged): A = O1 order-flow + TV, B = TV, D = Coinbase premium, P = path label,
    W = whale W2, T = TV-only A (T3), PB = path-label B, Dt = Coinbase + TV (v286)        (G2 books = A2 B2 D1)
  target 0.20 / 0.25 / 0.31 / 0.37 / 0.44    cap 2 / 3 / 4 (engine margin + 1m liquidation check)    m_sl 3 / 3.5 / 4 / 5 / 6 sigma_d
  m_tp 3 / 4 / 6 / 8 / 12 sigma_d (G2: 8 = 2 m_sl)    theta (open dead-band on |target|) 0.03 / 0.05 / 0.08 / 0.12
  be_k (break-even after + k sigma_d) 1 / 1.5 / 2 / 3 / off    partial TP off / (2 sigma, 1/2) / (3, 1/2) / (4, 1/3)
  k_off (entry limit offset, sigma_4h) 0.10 / 0.25 / 0.50    tighten 1.0 / 1.5 / 2.0    grid b_abs 0.02 / 0.03 / 0.05, b_rel 0.25 / 0.40 / 0.60, cool 3 / 6 / 12
SEEDS: G2 books + rules (manual form), t0.31, cap 3, P1 (+ path), W2 (+ whale), T3 (TV-only A), D-tv, v205-like (A + B, no D), TP 4, theta 0.08,
  break-even 1.0; rest of the population = seeds with three random gene changes.
FITNESS on years Ys (never the most recent year): R = geometric monthly net, W = worst-year monthly, DD = max yearly 1m-marked DD, WIN = book-trade
  win rate (net of fees, funding excluded, v213 definition), entries in Ys.
  floor terms g1 = (R / 5, 20 / DD, WIN / 0.55, min(1, 1 + W / 2)), each capped at 1:
    if any g1 < 1 -> F = 0.7 min(g1) + 0.3 mean(g1)       (push the hardest floor metric first: the floor is mandatory)
    else          -> F = 1 + 0.25 min(g2) + 0.75 mean(g2), g2 = (R / 8, 15 / DD, WIN / 0.60) capped at 1.2   (goal 2, easiest first)
GA: = v306 (population 32, 20 generations, 32 children, tournament 3, uniform crossover, mutation 2/20, (mu + lambda), de-duplication).
PROTOCOL (fixed before running; v306 fold-1 lesson: one training year overfits -> folds need >= 2 training years):
  WF folds k = 2, 3: evolve on dev years [:k] (GA seeds 307 / 308); winner scored on dev year k; baseline B_k = best SEED on [:k].
    TRANSFER holds if F_test(winner) - F_test(B_k) (mean over GA seeds) > 0 in BOTH folds.
  FINAL: evolve on dev4 (GA seeds 307 / 308 / 309); top ten pooled get 8 one-gene neighbours; finalist M = best neighbourhood mean.
  M becomes the recommended MANUAL pipeline only if TRANSFER holds and M meets goal 1 on dev4. The most recent year is scored ONCE for M.

  python research/parallel/rounds/parallel-20260906-r2/v307/v307_manual_book_evolution.py [--workers 3]
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v306 = _load("v306_m", RD / "v306/v306_walkforward_evolution.py")
MEM = ("wA", "wB", "wD", "wP", "wW", "wT", "wPB", "wDt")
GENES = [
    *[(n, (0, 1, 2, 3, 4)) for n in MEM],
    ("target", (0.20, 0.25, 0.31, 0.37, 0.44)), ("cap", (2.0, 3.0, 4.0)), ("m_sl", (3.0, 3.5, 4.0, 5.0, 6.0)), ("m_tp", (3.0, 4.0, 6.0, 8.0, 12.0)),
    ("theta", (0.03, 0.05, 0.08, 0.12)), ("be_k", (1.0, 1.5, 2.0, 3.0, None)), ("partial", (None, (2.0, 0.5), (3.0, 0.5), (4.0, 1 / 3))),
    ("k_off", (0.10, 0.25, 0.50)), ("tighten", (1.0, 1.5, 2.0)), ("b_abs", (0.02, 0.03, 0.05)), ("b_rel", (0.25, 0.40, 0.60)), ("cool", (3, 6, 12)),
]
POP, GENS, KIDS = 32, 20, 32
BASE = dict(wA=2, wB=2, wD=1, wP=0, wW=0, wT=0, wPB=0, wDt=0, target=0.25, cap=2.0, m_sl=4.0, m_tp=8.0, theta=0.05, be_k=2.0, partial=None,
            k_off=0.25, tighten=1.5, b_abs=0.03, b_rel=0.40, cool=6)
SEEDS = {"G2_manual": {}, "t031": dict(target=0.31), "cap3": dict(cap=3.0), "P1": dict(wP=1), "W2": dict(wW=1), "T3": dict(wA=0, wT=2),
         "Dtv": dict(wD=0, wDt=1), "v205": dict(wD=0), "tp4": dict(m_tp=4.0), "theta08": dict(theta=0.08), "be1": dict(be_k=1.0)}


def _v221():
    """v221 (engine_user + G2 constants); on Kaggle (env KPACK) the same audited engine and inputs from the kpack bundle."""
    import os
    if os.environ.get("KPACK"):
        return _load("kpack", RD / "kpack/kpack.py").fake_v221(os.environ["KPACK"])
    return _load("v221", RD / "v221/v221_grid_hysteresis.py")


def encode(d):
    full = dict(BASE, **d)
    return tuple(vals.index(full[n]) for n, vals in GENES)


def decode(g):
    return {n: vals[i] for (n, vals), i in zip(GENES, g)}


def valid(g):
    return sum(decode(g)[n] for n in MEM) > 0


W = {}


def init_worker():
    v221 = _v221()
    eu, v216 = v221.eu, v221.v216
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    D = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    grp = {"wA": (rd("member_A_O1_orders.parquet") + rd("member_Aq_O1_orders.parquet")) / 2,
           "wB": (rd("member_B_tv.parquet") + rd("member_Bq_tv.parquet")) / 2,
           "wD": (D + rd("members_quarterly_D.parquet")) / 2,
           "wP": (rd("member_PA_path.parquet") + rd("member_PAq_path.parquet")) / 2,
           "wW": (rd("member_A_whale.parquet") + rd("member_Aq_whale.parquet")) / 2,
           "wT": (rd("member_A_tv_annual.parquet") + rd("member_Aq_tv.parquet")) / 2,
           "wPB": (rd("member_PB_path.parquet") + rd("member_PBq_path.parquet")) / 2,
           "wDt": (rd("member_D_tv.parquet") + rd("member_Dq_tv.parquet")) / 2}
    W.update(eu=eu, v216=v216, KW=v221.KW, opens=opens, cols=cols, idx=idx, grp=grp, prep=eu.prepare(books154, opens),
             anchors=[pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS])
    v306.W.update(eu=eu)  # _trade_rows reads the fee constants from v306.W


def run_genome(g, full=False):
    d = decode(g)
    eu, idx, cols = W["eu"], W["idx"], W["cols"]
    books = pd.DataFrame(sum(d[n] * W["grp"][n] for n in MEM) / sum(d[n] for n in MEM), index=idx, columns=cols)
    trade = dict(W["v216"].GRID, policy=v306._policy(d["b_abs"], d["b_rel"], d["cool"]), theta=d["theta"], k_off=d["k_off"], tighten=d["tighten"])
    if d["be_k"] is None:
        trade.pop("be_k", None)
    else:
        trade["be_k"] = d["be_k"]
    if d["partial"] is not None:
        trade["partial_k"], trade["partial_frac"] = d["partial"]
    kw = dict(W["KW"], m_sl=d["m_sl"], m_tp=d["m_tp"], sleeve=False)
    ev = []
    r = eu.simulate(books, W["opens"], W["prep"], trade=trade, win_start=5, events=ev, target=d["target"], cap=d["cap"], **kw)
    tr = v306._trade_rows(ev)
    years = []
    for y in range(5 if full else 4):
        a0 = W["anchors"][y]
        a1 = a0 + pd.Timedelta(days=365)
        bk = [x[2] for x in tr if x[0] == "book" and a0 <= x[1] < a1]
        yy = r["yearly"][y]
        years.append(dict(net=yy["net_pct"], monthly=yy["monthly_pct"], dd=yy["dd_1m_pct"], n_book=len(bk), w_book=int(sum(v > 0 for v in bk)),
                          n_rung=0, w_rung=0))
    out = dict(g=list(g), years=years, liq=r["stats"].get("liq", 0))
    if full:
        out.update({k: r[k] for k in ("monthly_5y", "monthly_last_year", "gate_dd", "dd_1m", "dd_4h", "losing_years", "monthly_dev4")})
    return out


def metrics(res, ys):
    m = v306.metrics(res, ys)
    m["liq"] = res.get("liq", 0)
    return m


def fitness(res, ys):
    m = metrics(res, ys)
    g1 = np.minimum([m["R"] / 5, 20 / max(m["DD"], 1e-6), m["win_book"] / 0.55, min(1.0, 1 + m["W"] / 2)], 1.0)
    if g1.min() < 1:
        return float(0.7 * g1.min() + 0.3 * g1.mean())
    g2 = np.minimum([m["R"] / 8, 15 / max(m["DD"], 1e-6), m["win_book"] / 0.60], 1.2)
    return float(1 + 0.25 * g2.min() + 0.75 * g2.mean())


def mutate(g, rng):
    g = list(g)
    for q, (n, vals) in enumerate(GENES):
        if rng.random() < 2 / len(GENES):
            if rng.random() < 0.2 or len(vals) == 2:
                g[q] = rng.randrange(len(vals))
            else:
                g[q] = min(max(g[q] + rng.choice((-1, 1)), 0), len(vals) - 1)
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
        log(f"  seed {seed} years {ys} gen {gen} best {fit[pop[0]]:.4f} median {np.median([fit[x] for x in pop]):.4f} evals {len(fit)}")
    return sorted(fit, key=lambda x: -fit[x]), fit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    logf = (HERE / "evolution.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    pool = mp.Pool(args.workers, initializer=init_worker)
    ev = v306.Evaluator(pool, HERE / "eval_cache.jsonl")
    ev.pool = pool
    v306.run_genome = run_genome  # the Evaluator maps the module-level name it was given
    seeds = {k: encode(v) for k, v in SEEDS.items()}
    out = {"version": "v307", "genes": [(n, [str(v) for v in vals]) for n, vals in GENES], "seeds": {k: list(v) for k, v in seeds.items()},
           "folds": {}, "final": {}}
    sres = dict(zip(seeds, ev(list(seeds.values()))))
    m4 = metrics(sres["G2_manual"], [0, 1, 2, 3])
    log(f"G2_manual seed dev4 {m4}")
    assert abs(m4["R"] - 2.502) < 0.003, m4  # research/diagnostics/book_vs_bot MANUAL_book_only_t25
    out["seed_dev4"] = {k: dict(metrics(r, [0, 1, 2, 3]), F=round(fitness(r, [0, 1, 2, 3]), 4)) for k, r in sres.items()}
    for k, v in out["seed_dev4"].items():
        log(f"seed {k} {v}")
    for k in (2, 3):
        ys = list(range(k))
        bs = max(seeds, key=lambda s: fitness(sres[s], ys))
        fold = {"train_years": ys, "test_year": k, "best_seed": bs,
                "best_seed_test": dict(metrics(sres[bs], [k]), F=round(fitness(sres[bs], [k]), 4)),
                "G2_test": dict(metrics(sres["G2_manual"], [k]), F=round(fitness(sres["G2_manual"], [k]), 4)), "runs": {}}
        for sd in (307, 308):
            ranked, fit = evolve(ev, ys, sd + 1000 * k, log)
            w = ranked[0]
            rw = ev([w])[0]
            fold["runs"][sd] = {"winner": decode(w), "winner_g": list(w), "train": dict(metrics(rw, ys), F=round(fit[w], 4)),
                                "test": dict(metrics(rw, [k]), F=round(fitness(rw, [k]), 4))}
            log(f"FOLD {k} seed {sd} train {fold['runs'][sd]['train']} TEST {fold['runs'][sd]['test']} | best seed {bs} test {fold['best_seed_test']}")
        fold["delta_vs_best_seed"] = round(float(np.mean([r["test"]["F"] for r in fold["runs"].values()])) - fold["best_seed_test"]["F"], 4)
        out["folds"][k] = fold
        log(f"FOLD {k} delta F (evolved - best seed) on the unseen year {fold['delta_vs_best_seed']}")
    deltas = [out["folds"][k]["delta_vs_best_seed"] for k in (2, 3)]
    transfer = bool(all(x > 0 for x in deltas))
    out["transfer"] = {"deltas": deltas, "holds": transfer}
    log(f"TRANSFER {out['transfer']}")
    ys = [0, 1, 2, 3]
    pooled = {}
    for sd in (307, 308, 309):
        ranked, fit = evolve(ev, ys, sd + 4000, log)
        out["final"][f"seed_{sd}"] = {"winner": decode(ranked[0]), "F": round(fit[ranked[0]], 4), "dev4": metrics(ev([ranked[0]])[0], ys)}
        pooled.update(fit)
    top = sorted(pooled, key=lambda x: -pooled[x])[:10]
    rng = random.Random(4307)
    flat = {}
    for g in top:
        nb = []
        while len(nb) < 8:
            q = rng.randrange(len(GENES))
            c = list(g)
            c[q] = rng.choice([v for v in range(len(GENES[q][1])) if v != g[q]])
            c = tuple(c)
            if valid(c) and c not in nb:
                nb.append(c)
        flat[g] = float(np.mean([fitness(r, ys) for r in ev([g] + nb)]))
        log(f"top F {pooled[g]:.4f} neighbourhood mean {flat[g]:.4f} {decode(g)}")
    M = max(flat, key=lambda x: flat[x])
    rM = ev([M])[0]
    mM = metrics(rM, ys)
    goal1 = bool(mM["R"] >= 5 and mM["DD"] < 20 and mM["win_book"] >= 0.55 and mM["losing"] == 0)
    out["final"]["M"] = {"genome": decode(M), "g": list(M), "F_dev4": round(pooled[M], 4), "F_neigh": round(flat[M], 4), "dev4": mM,
                         "dev_years": rM["years"], "goal1_dev4": goal1}
    out["final"]["recommended"] = bool(transfer and goal1)
    fullM = pool.apply(run_genome, (M, True))
    out["final"]["M_full"] = {k: fullM[k] for k in ("monthly_5y", "monthly_last_year", "gate_dd", "dd_1m", "dd_4h", "losing_years", "monthly_dev4")}
    out["final"]["M_last_year"] = metrics(fullM, [4])
    log(f"FINAL M {out['final']['M']['genome']} dev4 {mM} goal1 {goal1} | full {out['final']['M_full']} | last year {out['final']['M_last_year']}"
        f" | recommended: {out['final']['recommended']}")
    pool.close()
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v307_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
