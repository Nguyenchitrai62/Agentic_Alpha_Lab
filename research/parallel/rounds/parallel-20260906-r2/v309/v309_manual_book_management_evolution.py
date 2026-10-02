"""v309: MANUAL product v3 - trader-management genes for the WIN RATE on top of v308 (registry v309).

Why: the MANUAL floor needs book win >= 55%; v307 fold-2 winners reached 5.3-5.8 %/month on the unseen 2023 but with win 46-52%. A trend book
loses its many small trades at the limit exit on signal loss (G2 dev: close exits win 48%, research/diagnostics/book_vs_bot/book_anatomy.py).
Three trader actions (all executable by a human: limit close or SL move at the 4h decision, from minute 5), decided from the state the engine
passes to trade["policy"] (upnl = open profit in sigma_d at the bar open, signal sign, valid actions):
  loss_act  on signal LOSS while the position is under water: close (audited v216 grid) / tighten (SL moved to `tighten` sigma_d from the price, the tighten gene) / hold
  opp_act   on an OPPOSITE signal while under water: close + tighten (audited) / tighten only
  lock      profit lock: limit close as soon as upnl >= lock sigma_d at a decision: off / 2 / 3 / 4 / 6
Everything else = v308 (genes, members, leverage / governor / short / break-even level / validity, fitness: MANUAL goal 1 floor first then goal 2
easiest first, GA, folds k = 2, 3, transfer rule, flat-neighbourhood finalist, most recent year scored once). With loss_act = close, opp_act =
close and lock = off the policy is the v216 grid policy exactly (seed G2_manual must reproduce 2.502).

  python research/parallel/rounds/parallel-20260906-r2/v309/v309_manual_book_management_evolution.py [--workers 3]
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
    ("target", (0.30, 0.37, 0.44, 0.52, 0.60)), ("cap", (3.0, 4.0, 5.0, 6.0)), ("m_sl", (3.0, 3.5, 4.0, 5.0, 6.0)), ("m_tp", (3.0, 4.0, 6.0, 8.0, 12.0)),
    ("theta", (0.03, 0.05, 0.08, 0.12)), ("be_k", (1.0, 1.5, 2.0, 3.0, None)), ("partial", (None, (2.0, 0.5), (3.0, 0.5), (4.0, 1 / 3))),
    ("k_off", (0.10, 0.25, 0.50)), ("tighten", (1.0, 1.5, 2.0)), ("b_abs", (0.02, 0.03, 0.05)), ("b_rel", (0.25, 0.40, 0.60)), ("cool", (3, 6, 12)),
    ("gov", ((0.20, 0.10), (0.18, 0.08), (0.16, 0.08), (0.15, 0.06), (0.25, 0.15))), ("short", (0.50, 0.75, 1.00, 1.25)),
    ("be_off", (0.001, 0.002, 0.004)), ("n_valid", (2, 3, 6)),
    ("loss_act", ("close", "tighten", "hold")), ("opp_act", ("close", "tighten")), ("lock", (None, 2.0, 3.0, 4.0, 6.0)),
]
POP, GENS, KIDS = 32, 20, 32
BASE = dict(wA=2, wB=2, wD=1, wP=0, wW=0, wT=0, wPB=0, wDt=0, target=0.30, cap=3.0, m_sl=4.0, m_tp=8.0, theta=0.05, be_k=2.0, partial=None,
            k_off=0.25, tighten=1.5, b_abs=0.03, b_rel=0.40, cool=6, gov=(0.20, 0.10), short=1.0, be_off=0.001, n_valid=2,
            loss_act="close", opp_act="close", lock=None)
SEEDS = {"G2_manual": dict(target=0.25, cap=2.0), "c4t37": dict(target=0.37, cap=4.0), "c4t44": dict(target=0.44, cap=4.0),
         "loss_tight": dict(target=0.37, cap=4.0, loss_act="tighten"), "loss_hold": dict(target=0.37, cap=4.0, loss_act="hold"), "opp_tight": dict(target=0.37, cap=4.0, opp_act="tighten"),
         "lock3": dict(target=0.37, cap=4.0, lock=3.0), "lock4": dict(target=0.37, cap=4.0, lock=4.0), "beoff4": dict(target=0.37, cap=4.0, be_off=0.004),
         "tight_lock4": dict(target=0.37, cap=4.0, loss_act="tighten", lock=4.0), "v205": dict(target=0.37, cap=4.0, wD=0), "W2": dict(target=0.37, cap=4.0, wW=1)}

def _v221():
    """v221 (engine_user + G2 constants); on Kaggle (env KPACK) the same audited engine and inputs from the kpack bundle."""
    import os
    if os.environ.get("KPACK"):
        return _load("kpack", RD / "kpack/kpack.py").fake_v221(os.environ["KPACK"])
    return _load("v221", RD / "v221/v221_grid_hysteresis.py")


def encode(d):
    full = dict(BASE, **d)
    return tuple(vals.index(full[n]) for n, vals in GENES)


# the reference seed G2_manual (target 0.25, cap 2) lies outside the v308 ranges: both values are prepended to their gene lists
GENES[8] = ("target", (0.25,) + GENES[8][1])
GENES[9] = ("cap", (2.0,) + GENES[9][1])


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


def _policy9(b_abs, b_rel, cool, loss_act, opp_act, lock):
    """v216 grid policy (= v306._policy) + the v309 management genes; defaults (close, close, None) = v216 exactly."""
    def pol(i, a, st):
        if st["pos"] == 0:
            return "open"
        side, tg, w, valid_ = st["pos"], st["tg"], st["w"], st["valid"]
        under = st["upnl"] < 0
        if lock is not None and st["upnl"] >= lock and "close" in valid_:
            return "close"
        if st["sgn"] == -side:
            if under and opp_act == "tighten":
                return "tighten"
            return {"tighten": 1, "close": 1} if "close" in valid_ else "tighten"
        if st["sgn"] == 0:
            if under and loss_act != "close":
                return loss_act
            return "close" if "close" in valid_ else "hold"
        if st["since_adj"] < cool:
            return "hold"
        band = max(b_abs, b_rel * abs(tg))
        diff = abs(tg) - w
        if diff > band and "add" in valid_:
            return {"add": diff}
        if -diff > band and "reduce" in valid_ and w > 0:
            return {"reduce": min(1.0, -diff / w)}
        return "hold"
    return pol


def run_genome(g, full=False):
    d = decode(g)
    eu, idx, cols = W["eu"], W["idx"], W["cols"]
    books = pd.DataFrame(sum(d[n] * W["grp"][n] for n in MEM) / sum(d[n] for n in MEM), index=idx, columns=cols)
    books = books.where(books >= 0, books * d["short"])
    trade = dict(W["v216"].GRID, policy=_policy9(d["b_abs"], d["b_rel"], d["cool"], d["loss_act"], d["opp_act"], d["lock"]), theta=d["theta"], k_off=d["k_off"], tighten=d["tighten"],
                 be_off=d["be_off"], n_valid=d["n_valid"])
    if d["be_k"] is None:
        trade.pop("be_k", None)
    else:
        trade["be_k"] = d["be_k"]
    if d["partial"] is not None:
        trade["partial_k"], trade["partial_frac"] = d["partial"]
    kw = dict(W["KW"], m_sl=d["m_sl"], m_tp=d["m_tp"], sleeve=False)
    ev = []
    r = eu.simulate(books, W["opens"], W["prep"], trade=trade, win_start=5, events=ev, target=d["target"], cap=d["cap"], gov=d["gov"], **kw)
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
    out = {"version": "v309", "genes": [(n, [str(v) for v in vals]) for n, vals in GENES], "seeds": {k: list(v) for k, v in seeds.items()},
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
        for sd in (319, 329):
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
    for sd in (319, 329, 339):
        ranked, fit = evolve(ev, ys, sd + 4000, log)
        out["final"][f"seed_{sd}"] = {"winner": decode(ranked[0]), "F": round(fit[ranked[0]], 4), "dev4": metrics(ev([ranked[0]])[0], ys)}
        pooled.update(fit)
    top = sorted(pooled, key=lambda x: -pooled[x])[:10]
    rng = random.Random(4309)
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
    (HERE / "v309_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
