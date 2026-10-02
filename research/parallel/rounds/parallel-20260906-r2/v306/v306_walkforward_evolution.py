"""v306: WALK-FORWARD EVOLUTION - recombine the components of the good / promising past pipelines with a genetic algorithm (registry v306).

User 2026-10-02: the base goal (>= 5 %/month, DD <= 20%, win ~56%) is reached by G2; new goal 8 %/month, DD < 15%, win rate > 65%, easiest goal
first, DD > 20 is no automatic reject. The pipelines so far were built by hand, one knob per version (v189-v305). Many knobs that helped one
metric were dropped because another metric moved (R1: dev4 7.81 but DD 20.3; H1: DD 16.5 but weaker worst year; P1 path member; B1 5-sigma close
stops; T1 book target; J3 5-action size). A genetic algorithm searches the JOINT space of those components. The danger is obvious - a search over
~10^12 configurations on four dev years overfits (v189-v197: dev4 3.90 -> 5.56 while the unseen year moved 2.34 -> 2.76). Therefore the
evolution itself is the pre-registered method and is judged WALK-FORWARD: the GA for test year Y sees only the years before Y.

ENGINE / DATA (all audited, unchanged): engine_user trade mode (one resting limit, minute-5 rule, SL market taker 0.055%, TP limit maker 0.02%,
adverse funding longs 0.01%/8h, stop-first ties), C4 dip-ladder rules (5m-close stops + exchange-native backstop, TP 1 sigma unless the agent
changes it), dip agents in the DEPLOYABLE BAR-OPEN form (state at the close of minute 0, as research/diagnostics/g2_exec), walk-forward member
books (cached, fitted before each anchor - embargo), agent tables artifacts/research/engine_real/v306_gene_tables.parquet (v306_gene_tables.py:
the v301 agents refitted on three rung sets, raw predictions stored; fits on pooled fills that exited before anchor - 7 days).

GENOME (21 genes + 7 rung bits, discrete values, all from ranges explored in v204-v305; the monthly-retrained member is EXCLUDED because its only
merit was the most recent year, v280):
  book members (integer weights 0..4, normalised): A = (A_O1 + Aq_O1)/2, B = (B_tv + Bq_tv)/2, D = Coinbase (D + Dq)/2, P = path (PA + PAq)/2,
    W = whale W2 (A_whale + Aq_whale)/2          G2 = A2 B2 D1
  target 0.20 / 0.22 / 0.25 / 0.28 / 0.31        m_sl (book stop, sigma_d) 3.0 / 3.5 / 4.0 / 5.0
  grid band b_abs 0.02 / 0.03 / 0.05, b_rel 0.25 / 0.40 / 0.60, cool 3 / 6 / 12 bars
  align (dip size x long-book / x otherwise) (1,1) / (1.25,0.75) / (1.5,0.5) / (1.75,0.25)
  rung bits for depths 2.0 2.5 3.0 3.5 4.0 4.5 5.0 sigma (>= 2 set)   fit G2 / R1 / U
  size rule: x up_mult if both halves predict > up_th * mu (up_th 1.5 / 2 / 3, up_mult 1.25 / 1.5 / 2.0); x dn_mult if both < dn_th * mu
    (dn_th -1 / 0 / 0.5, dn_mult 0 / 0.25 / 0.5 / 0.75)
  take-profit margin (both halves agree on a non-base action with gain > margin) off / 0.002 / 0.001 / 0.0005
  dip budget 0.18 / 0.22 / 0.26 / 0.30 / 0.34   rung size 1.25 / 1.5 / 1.75 / 2.0 / 2.25   close-stop 3.5 / 4.0 / 5.0 sigma   backstop 6 / 8 / 10
SEEDS = the past pipelines expressed in the genome: G2 (deployed), J1 (budget 0.18), R1 (2.0 rung, fit R1), Q2 (R1 + budget 0.18), R2 (2.5..5.0,
fit U), P1 (+ path member), B1 (5-sigma close stop), T1 (target 0.28), J3-like (x2 / skip), v297-like (target 0.22, budget 0.30), W2 member,
fit-U G2; the rest of the population = seeds with three random gene changes.

FITNESS on a set of years Ys (per-year metrics of engine_user; the most recent year is never part of Ys): R = geometric monthly net over Ys,
W = worst single-year monthly, DD = max yearly 1m-marked DD, WIN = win rate of ALL trades (book trades + dip rungs, entry in Ys);
g = (R / 8, W / 5, 15 / DD, WIN / 0.65), each capped at 1.2; F = 0.5 min(g) + 0.5 mean(g); a losing year -> F = -1 + R / 100.
GA: population 32, 20 generations, 32 children per generation (tournament 3, uniform crossover, per-gene mutation 2/28 to a neighbour value
(20%: any value), rung-bit flip), (mu + lambda) survival with de-duplication; GA seeds 306 / 307 / 308 (stochastic -> 3 seeds).

PROTOCOL (fixed before running):
  WF folds k = 1, 2, 3: evolve on dev years [:k]; winner W_k (highest train F) is scored on dev year k (unseen by that GA).
    Baselines on the same test year: B_k = the best SEED on years [:k] (= picking the best existing pipeline with the same data) and G2.
    TRANSFER holds if the mean over folds and GA seeds of F_test(W_k) - F_test(B_k) > 0 and it is > 0 in >= 2 of 3 folds (seed mean).
  FINAL fold 4: evolve on all four dev years (3 GA seeds); the ten best distinct genomes (pooled) get 8 random one-gene neighbours each; the
    finalist E = highest mean F over itself + neighbours (flat optimum, not the sharpest peak).
  E replaces G2 as the recommended pipeline only if TRANSFER holds and F_dev4(E) > F_dev4(G2). The most recent year is scored ONCE, for E
    only, at the end (reported against the user goals; never used to choose). If TRANSFER fails, E is reported as an in-sample curiosity only.

  python research/parallel/rounds/parallel-20260906-r2/v306/v306_walkforward_evolution.py [--workers 3]
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
FITN = ("G2", "R1", "U")
GENES = [
    ("wA", (0, 1, 2, 3, 4)), ("wB", (0, 1, 2, 3, 4)), ("wD", (0, 1, 2, 3, 4)), ("wP", (0, 1, 2, 3, 4)), ("wW", (0, 1, 2, 3, 4)),
    ("target", (0.20, 0.22, 0.25, 0.28, 0.31)), ("m_sl", (3.0, 3.5, 4.0, 5.0)),
    ("b_abs", (0.02, 0.03, 0.05)), ("b_rel", (0.25, 0.40, 0.60)), ("cool", (3, 6, 12)),
    ("align", ((1.0, 1.0), (1.25, 0.75), (1.5, 0.5), (1.75, 0.25))),
    *[(f"r{int(k * 10)}", (0, 1)) for k in U],
    ("fit", FITN), ("up_th", (1.5, 2.0, 3.0)), ("up_mult", (1.25, 1.5, 2.0)), ("dn_th", (-1.0, 0.0, 0.5)), ("dn_mult", (0.0, 0.25, 0.5, 0.75)),
    ("tp_margin", (None, 0.002, 0.001, 0.0005)), ("budget", (0.18, 0.22, 0.26, 0.30, 0.34)), ("size_mult", (1.25, 1.5, 1.75, 2.0, 2.25)),
    ("sleeve_sl", (3.5, 4.0, 5.0)), ("backstop", (6.0, 8.0, 10.0)),
]
NAMES = [g[0] for g in GENES]
POP, GENS, KIDS = 32, 20, 32
GA_SEEDS = (306, 307, 308)
G2 = dict(wA=2, wB=2, wD=1, wP=0, wW=0, target=0.25, m_sl=4.0, b_abs=0.03, b_rel=0.40, cool=6, align=(1.5, 0.5),
          r20=0, r25=1, r30=1, r35=1, r40=1, r45=0, r50=0, fit="G2", up_th=2.0, up_mult=1.5, dn_th=0.0, dn_mult=0.5, tp_margin=0.001,
          budget=0.26, size_mult=1.75, sleeve_sl=4.0, backstop=8.0)
SEEDS = {
    "G2": {},
    "J1": dict(budget=0.18),
    "R1": dict(r20=1, fit="R1"),
    "Q2": dict(r20=1, fit="R1", budget=0.18),
    "R2": dict(r50=1, fit="U"),
    "P1": dict(wP=1),
    "B1": dict(sleeve_sl=5.0),
    "T1": dict(target=0.28),
    "J3": dict(up_th=3.0, up_mult=2.0, dn_th=-1.0, dn_mult=0.0),
    "v297": dict(target=0.22, budget=0.30),
    "W2m": dict(wW=1),
    "G2_fitU": dict(fit="U"),
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _v221():
    """v221 (engine_user + G2 constants); on Kaggle (env KPACK) the same audited engine and inputs from the kpack bundle."""
    import os
    if os.environ.get("KPACK"):
        return _load("kpack", RD / "kpack/kpack.py").fake_v221(os.environ["KPACK"])
    return _load("v221", RD / "v221/v221_grid_hysteresis.py")


def encode(d):
    full = dict(G2, **d)
    return tuple(vals.index(full[n]) for n, vals in GENES)


def decode(g):
    return {n: vals[i] for (n, vals), i in zip(GENES, g)}


def valid(g):
    d = decode(g)
    return sum(d[n] for n in ("wA", "wB", "wD", "wP", "wW")) > 0 and sum(d[f"r{int(k * 10)}"] for k in U) >= 2


# ---------------------------------------------------------------- worker side
W = {}


def _policy(b_abs, b_rel, cool):
    """= v216.grid_policy with the cool-down as a parameter (v216 module constant COOL = 6)."""
    def pol(i, a, st):
        if st["pos"] == 0:
            return "open"
        side, tg, w, valid_ = st["pos"], st["tg"], st["w"], st["valid"]
        if st["sgn"] == -side:
            return {"tighten": 1, "close": 1} if "close" in valid_ else "tighten"
        if st["sgn"] == 0:
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


def init_worker():
    v221 = _v221()
    eu, v216 = v221.eu, v221.v216
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    m154 = pd.read_parquet(C / "members_v154.parquet")
    D = m154.xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    grp = {"wA": (rd("member_A_O1_orders.parquet") + rd("member_Aq_O1_orders.parquet")) / 2,
           "wB": (rd("member_B_tv.parquet") + rd("member_Bq_tv.parquet")) / 2,
           "wD": (D + rd("members_quarterly_D.parquet")) / 2,
           "wP": (rd("member_PA_path.parquet") + rd("member_PAq_path.parquet")) / 2,
           "wW": (rd("member_A_whale.parquet") + rd("member_Aq_whale.parquet")) / 2}
    tab = pd.read_parquet(C / "v306_gene_tables.parquet")
    ii = idx.get_indexer(tab["T"] - pd.Timedelta(hours=4))
    aa = np.array([cols.index(s) for s in tab["sym"]])
    kk = np.array([U.index(k) for k in tab["k"]])
    ff = np.array([FITN.index(f) for f in tab["fit"]])
    ok = ii >= 0
    T = {c: np.full((len(FITN), len(idx), len(cols), len(U)), np.nan) for c in ("pa", "pb", "mu", "qa0", "qa1", "qa2", "qb0", "qb1", "qb2")}
    for c in T:
        T[c][ff[ok], ii[ok], aa[ok], kk[ok]] = tab[c].to_numpy(float)[ok]
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    W.update(eu=eu, v216=v216, KW=v221.KW, books154=books154, opens=opens, cols=cols, idx=idx, grp=grp, T=T, anchors=anchors,
             prep=eu.prepare(books154, opens))


def _tables(d):
    T, fi = W["T"], FITN.index(d["fit"])
    pa, pb, mu = T["pa"][fi], T["pb"][fi], T["mu"][fi]
    size = np.ones_like(pa)
    up = (pa > d["up_th"] * mu) & (pb > d["up_th"] * mu)
    dn = (pa < d["dn_th"] * mu) & (pb < d["dn_th"] * mu)
    size[up] = d["up_mult"]
    size[dn & ~up] = d["dn_mult"]
    size[~np.isfinite(pa)] = 1.0
    tp = np.ones_like(pa)
    if d["tp_margin"] is not None:
        qa = np.stack([T[f"qa{c}"][fi] for c in range(3)], -1)
        qb = np.stack([T[f"qb{c}"][fi] for c in range(3)], -1)
        ba, bb = np.nanargmax(np.nan_to_num(qa, nan=-9), -1), np.nanargmax(np.nan_to_num(qb, nan=-9), -1)
        ga = np.take_along_axis(qa, ba[..., None], -1)[..., 0] - qa[..., 1]
        gb = np.take_along_axis(qb, bb[..., None], -1)[..., 0] - qb[..., 1]
        okk = (ba == bb) & (ba != 1) & (ga > d["tp_margin"]) & (gb > d["tp_margin"]) & np.isfinite(ga) & np.isfinite(gb)
        tp = np.where(okk, np.array((0.5, 1.0, 1.5))[ba], 1.0)
    return size, tp


def _trade_rows(events):
    """Book trades (v213.trade_stats net definition: maker / taker fees, funding excluded) and dip rungs: (entry time, net)."""
    MAKER, TAKER = W["eu"].MAKER, W["eu"].TAKER
    pos, out = {}, []
    for e in events:
        k, sym = e["kind"], e.get("symbol")
        if k in ("rung_tp", "rung_sl", "rung_timeout") and "ret" in e and e["ret"] is not None:
            out.append(("rung", e["t"], float(e["ret"])))
            continue
        if k == "book_fill":
            q = abs(e["weight"]) / e["price"]
            pos[sym] = dict(t=e["t"], side=1 if e["side"] == "buy" else -1, qty=q, cost=q * e["price"], proceeds=0.0, fees=q * e["price"] * MAKER)
            continue
        o = pos.get(sym)
        if o is None:
            continue
        if k == "book_add":
            q = abs(e["weight"]) / e["price"]
            o["qty"] += q; o["cost"] += q * e["price"]; o["fees"] += q * e["price"] * MAKER
        elif k in ("book_reduce", "book_partial"):
            q = min(abs(e["weight"]) / e["price"], o["qty"])
            o["qty"] -= q; o["proceeds"] += q * e["price"]; o["fees"] += q * e["price"] * MAKER
        elif k in ("book_stop", "book_tp", "book_close"):
            o["proceeds"] += o["qty"] * e["price"]
            o["fees"] += o["qty"] * e["price"] * (TAKER if k == "book_stop" else MAKER)
            out.append(("book", o["t"], (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]))
            pos.pop(sym)
    return out


def run_genome(g, full=False):
    """Simulate one genome. Returns per-DEV-year metrics only (the most recent year is stripped unless full=True, used once for E)."""
    d = decode(g)
    eu, idx, cols = W["eu"], W["idx"], W["cols"]
    wsum = sum(d[n] for n in W["grp"])
    books = pd.DataFrame(sum(d[n] * W["grp"][n] for n in W["grp"]) / wsum, index=idx, columns=cols)
    rungs = tuple(k for k in U if d[f"r{int(k * 10)}"])
    kmap = [U.index(k) for k in rungs]
    size, tp = _tables(d)
    hs = lambda i, a, r, f: float(size[i, a, kmap[r]])
    ht = lambda i, a, r, f: float(tp[i, a, kmap[r]])
    trade = dict(W["v216"].GRID, policy=_policy(d["b_abs"], d["b_rel"], d["cool"]))
    kw = dict(W["KW"], m_sl=d["m_sl"], align=d["align"], sleeve_risk_budget=d["budget"], size_mult=d["size_mult"],
              sleeve_stop_mode="close5", m_sleeve_sl=d["sleeve_sl"], sleeve_backstop=d["backstop"])
    ev = []
    r = eu.simulate(books, W["opens"], W["prep"], trade=trade, win_start=5, events=ev, sleeve_fill_size=hs, sleeve_tp=ht, rungs=rungs,
                    target=d["target"], **kw)
    tr = _trade_rows(ev)
    years = []
    ny = 5 if full else 4
    for y in range(ny):
        a0 = W["anchors"][y]
        a1 = a0 + pd.Timedelta(days=365)
        rows = [x for x in tr if a0 <= x[1] < a1]
        bk = [x[2] for x in rows if x[0] == "book"]
        rg = [x[2] for x in rows if x[0] == "rung"]
        yy = r["yearly"][y]
        years.append(dict(net=yy["net_pct"], monthly=yy["monthly_pct"], dd=yy["dd_1m_pct"], n_book=len(bk), w_book=int(sum(v > 0 for v in bk)),
                          n_rung=len(rg), w_rung=int(sum(v > 0 for v in rg))))
    out = dict(g=list(g), years=years)
    if full:
        out.update(monthly_5y=r["monthly_5y"], monthly_last_year=r["monthly_last_year"], gate_dd=r["gate_dd"], dd_1m=r["dd_1m"], dd_4h=r["dd_4h"],
                   losing_years=r["losing_years"], monthly_dev4=r["monthly_dev4"])
    return out


# ---------------------------------------------------------------- leader side
def metrics(res, ys):
    yy = [res["years"][y] for y in ys]
    R = 100 * (np.prod([1 + y["net"] / 100 for y in yy]) ** (1 / (12 * len(yy))) - 1)
    Wst = min(y["monthly"] for y in yy)
    DD = max(y["dd"] for y in yy)
    n = sum(y["n_book"] + y["n_rung"] for y in yy)
    win = sum(y["w_book"] + y["w_rung"] for y in yy) / max(n, 1)
    nb = sum(y["n_book"] for y in yy)
    wb = sum(y["w_book"] for y in yy) / max(nb, 1)
    nr = sum(y["n_rung"] for y in yy)
    wr = sum(y["w_rung"] for y in yy) / max(nr, 1)
    return dict(R=round(R, 3), W=round(Wst, 3), DD=round(DD, 2), win=round(win, 4), win_book=round(wb, 4), win_rung=round(wr, 4), trades=n,
                losing=sum(y["net"] < 0 for y in yy))


def fitness(res, ys):
    m = metrics(res, ys)
    if m["losing"]:
        return -1 + m["R"] / 100
    g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6), m["win"] / 0.65], 1.2)
    return float(0.5 * g.min() + 0.5 * g.mean())


class Evaluator:
    def __init__(self, pool, cache_path):
        self.pool, self.cache, self.path = pool, {}, cache_path
        if cache_path.exists():
            for line in cache_path.read_text().splitlines():
                x = json.loads(line)
                self.cache[tuple(x["g"])] = x

    def __call__(self, genomes):
        todo = list({g for g in genomes if g not in self.cache})
        if todo:
            for x in self.pool.imap_unordered(run_genome, todo):
                self.cache[tuple(x["g"])] = x
                with self.path.open("a") as fh:
                    fh.write(json.dumps(x) + "\n")
        return [self.cache[g] for g in genomes]


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
    ev = Evaluator(pool, HERE / "eval_cache.jsonl")
    g2 = encode({})
    seeds = {k: encode(v) for k, v in SEEDS.items()}
    out = {"version": "v306", "genes": [(n, [str(v) for v in vals]) for n, vals in GENES], "seeds": {k: list(v) for k, v in seeds.items()},
           "folds": {}, "final": {}}
    sres = dict(zip(seeds, ev(list(seeds.values()))))
    # reproduction check: the G2 seed = G2 bar-open (research/diagnostics/g2_exec G2_bar_open dev4 6.504)
    m4 = metrics(sres["G2"], [0, 1, 2, 3])
    log(f"G2 seed dev4 {m4}")
    assert abs(m4["R"] - 6.504) < 0.003, m4
    out["seed_dev4"] = {k: dict(metrics(r, [0, 1, 2, 3]), F=round(fitness(r, [0, 1, 2, 3]), 4)) for k, r in sres.items()}
    for k, v in out["seed_dev4"].items():
        log(f"seed {k} {v}")
    # walk-forward folds
    for k in (1, 2, 3):
        ys = list(range(k))
        bs = max(seeds, key=lambda s: fitness(sres[s], ys))
        fold = {"train_years": ys, "test_year": k, "best_seed": bs,
                "best_seed_test": dict(metrics(sres[bs], [k]), F=round(fitness(sres[bs], [k]), 4)),
                "G2_test": dict(metrics(sres["G2"], [k]), F=round(fitness(sres["G2"], [k]), 4)), "runs": {}}
        for sd in GA_SEEDS:
            ranked, fit = evolve(ev, ys, sd + 1000 * k, log)
            w = ranked[0]
            rw = ev([w])[0]
            fold["runs"][sd] = {"winner": decode(w), "winner_g": list(w), "train": dict(metrics(rw, ys), F=round(fit[w], 4)),
                                "test": dict(metrics(rw, [k]), F=round(fitness(rw, [k]), 4)),
                                "best_seed_train_F": round(fitness(sres[bs], ys), 4)}
            log(f"FOLD {k} seed {sd} train {fold['runs'][sd]['train']} TEST {fold['runs'][sd]['test']} | best seed {bs} test {fold['best_seed_test']}")
        fold["delta_vs_best_seed"] = round(float(np.mean([r["test"]["F"] for r in fold["runs"].values()])) - fold["best_seed_test"]["F"], 4)
        out["folds"][k] = fold
        log(f"FOLD {k} delta F (evolved - best seed) on the unseen year {fold['delta_vs_best_seed']}")
    deltas = [out["folds"][k]["delta_vs_best_seed"] for k in (1, 2, 3)]
    transfer = bool(np.mean(deltas) > 0 and sum(x > 0 for x in deltas) >= 2)
    out["transfer"] = {"deltas": deltas, "mean": round(float(np.mean(deltas)), 4), "holds": transfer}
    log(f"TRANSFER {out['transfer']}")
    # final fold on all four dev years
    ys = [0, 1, 2, 3]
    pooled = {}
    for sd in GA_SEEDS:
        ranked, fit = evolve(ev, ys, sd + 4000, log)
        out["final"][f"seed_{sd}"] = {"winner": decode(ranked[0]), "F": round(fit[ranked[0]], 4), "dev4": metrics(ev([ranked[0]])[0], ys)}
        pooled.update(fit)
    top = sorted(pooled, key=lambda x: -pooled[x])[:10]
    rng = random.Random(4306)
    flat = {}
    for g in top:
        nb = []
        while len(nb) < 8:
            q = rng.randrange(len(GENES))
            vals = GENES[q][1]
            c = list(g)
            c[q] = rng.choice([v for v in range(len(vals)) if v != g[q]])
            c = tuple(c)
            if valid(c) and c not in nb:
                nb.append(c)
        fs = [fitness(r, ys) for r in ev([g] + nb)]
        flat[g] = float(np.mean(fs))
        log(f"top F {pooled[g]:.4f} neighbourhood mean {flat[g]:.4f} {decode(g)}")
    E = max(flat, key=lambda x: flat[x])
    rE = ev([E])[0]
    out["final"]["E"] = {"genome": decode(E), "g": list(E), "F_dev4": round(pooled[E], 4), "F_neigh": round(flat[E], 4), "dev4": metrics(rE, ys),
                         "dev_years": rE["years"]}
    out["final"]["G2_F_dev4"] = round(fitness(sres["G2"], ys), 4)
    out["final"]["replaces_G2"] = bool(transfer and pooled[E] > fitness(sres["G2"], ys))
    # the most recent year: scored ONCE, for E only
    fullE = pool.apply(run_genome, (E, True))
    out["final"]["E_full"] = {k: fullE[k] for k in ("monthly_5y", "monthly_last_year", "gate_dd", "dd_1m", "dd_4h", "losing_years", "monthly_dev4")}
    out["final"]["E_last_year"] = dict(metrics(fullE, [4]), F=round(fitness(fullE, [4]), 4))
    log(f"FINAL E {out['final']['E']['genome']} dev4 {out['final']['E']['dev4']} | full {out['final']['E_full']} | last year {out['final']['E_last_year']}"
        f" | replaces G2: {out['final']['replaces_G2']}")
    pool.close()
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v306_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
