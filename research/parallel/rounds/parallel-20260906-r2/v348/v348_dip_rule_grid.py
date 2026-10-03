"""v348: EXHAUSTIVE walk-forward search over the dip-agent DECISION RULES of the deployed MANUAL pipeline M3 (registry v348, registered before running).

M3 (v342 L2 on CB books; dev4 6.233) turns the frozen R2 dip agents' bar-open predictions into decisions with rules copied from the BOT
(v295 S1 size rule, v294 X4 take-profit rule, fit "U"); they were never chosen for the MANUAL product. The kpack inputs make one simulation ~4 s,
so the whole rule grid can be evaluated (no GA sampling noise):
  fit (G2, R1, U) x up_th (1.5, 2.0, 3.0) x up_mult (1.25, 1.5, 2.0) x dn_th (-1.0, 0.0, 0.5) x dn_mult (0.0, 0.25, 0.5, 0.75)
  x tp_margin (None, 0.002, 0.001, 0.0005)  = 1296 rule sets (size x up_mult if both cross-fitted halves predict > up_th x mu, x dn_mult if
  both < dn_th x mu; TP 0.5 / 1.0 / 1.5 sigma only if both halves prefer it by > tp_margin; v306._tables).
Everything else = M3 (CB books x0.75, pullback entry 0.75 sigma / 3 bars, bracket dip limits 3.0 / 4.0 sigma, size_mult 4.375, native touch stop
8 sigma, budget 0.26, sleeve_start 16, target 0.25, cap 2).
FITNESS: v347 MANUAL fitness (v310 form, all-trade win rate); training F_train(Ys) = 0.5 * min_y F({y}) + 0.5 * F(Ys).
CHOICE inside a fold = flat optimum: among the 20 best rule sets on F_train, the highest mean F_train over the rule set and ALL its one-gene
neighbours in the grid.
PROTOCOL (fixed before running): folds k = 2, 3: choice on dev years [:k], scored on dev year k against the deployed M3 rules
(U, 2.0, 1.5, 0.0, 0.5, 0.001); TRANSFER if the choice beats M3 on the unseen year in BOTH folds. Final choice on dev4; most recent year computed
once for it; it replaces the M3 rules only if TRANSFER holds and its dev4 F_train exceeds M3's. Contaminated by design; prospective log = clean.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v348/v348_dip_rule_grid.py [--workers 3]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
GENES = [("fit", ("G2", "R1", "U")), ("up_th", (1.5, 2.0, 3.0)), ("up_mult", (1.25, 1.5, 2.0)), ("dn_th", (-1.0, 0.0, 0.5)),
         ("dn_mult", (0.0, 0.25, 0.5, 0.75)), ("tp_margin", (None, 0.002, 0.001, 0.0005))]
M3 = dict(fit="U", up_th=2.0, up_mult=1.5, dn_th=0.0, dn_mult=0.5, tp_margin=0.001)
W = {}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v347 = _load("v347_rules", RD / "v347/v347_member_weight_evolution.py")


def encode(d):
    return tuple(vals.index(d[n]) for n, vals in GENES)


def decode(g):
    return {n: vals[i] for (n, vals), i in zip(GENES, g)}


def init_worker():
    v347.init_worker()
    W.update(v306=v347.W["v306"])
    v306 = W["v306"]
    v306.W["T"] = _tables_T()


def _tables_T():
    """Reload the v306 prediction tables (v347.init_worker frees them after building the M3 tables)."""
    v306 = v347.W["v306"]
    C = v347.W["v310"].W["eu"].er.CACHE
    idx, cols = v347.W["v310"].W["idx"], v347.W["v310"].W["cols"]
    tab = pd.read_parquet(C / "v306_gene_tables.parquet")
    ii = idx.get_indexer(tab["T"] - pd.Timedelta(hours=4))
    aa = np.array([cols.index(s) for s in tab["sym"]])
    kk = np.array([U.index(k) for k in tab["k"]])
    ff = np.array([v306.FITN.index(f) for f in tab["fit"]])
    ok = ii >= 0
    T = {c: np.full((len(v306.FITN), len(idx), len(cols), len(U)), np.nan) for c in ("pa", "pb", "mu", "qa0", "qa1", "qa2", "qb0", "qb1", "qb2")}
    for c in T:
        T[c][ff[ok], ii[ok], aa[ok], kk[ok]] = tab[c].to_numpy(float)[ok]
    return T


def run_rules(g, full=False):
    size, tp = W["v306"]._tables(decode(g))
    v347.W["size"], v347.W["tp"] = size, tp
    res = v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
    res["g"] = list(g)
    return res


def neighbours(g):
    out = []
    for q, (_, vals) in enumerate(GENES):
        for v in range(len(vals)):
            if v != g[q]:
                c = list(g)
                c[q] = v
                out.append(tuple(c))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    cache_p = HERE / "eval_cache.jsonl"
    cache = {}
    if cache_p.exists():
        for line in cache_p.read_text().splitlines():
            if line.strip():
                x = json.loads(line)
                cache[tuple(x["g"])] = x
    grid = list(itertools.product(*[range(len(v)) for _, v in GENES]))
    todo = [g for g in grid if g not in cache]
    log(f"grid {len(grid)} cached {len(cache)} todo {len(todo)}")
    with mp.Pool(args.workers, initializer=init_worker) as pool:
        for n, x in enumerate(pool.imap_unordered(run_rules, todo, chunksize=4)):
            cache[tuple(x["g"])] = x
            with cache_p.open("a") as fh:
                fh.write(json.dumps(x, default=str) + "\n")
            if n % 100 == 0:
                log(f"  evaluated {n + 1} / {len(todo)}")
        g0 = encode(M3)
        assert abs(v347.W_metrics(cache[g0], [0, 1, 2, 3])["R"] - 6.233) < 0.003
        fit = v347.fitness

        def choose(ys):
            ft = {g: fit(cache[g], ys) for g in grid}
            top = sorted(grid, key=lambda g: -ft[g])[:20]
            flat = {g: float(np.mean([ft[g]] + [ft[c] for c in neighbours(g)])) for g in top}
            return max(flat, key=lambda g: flat[g]), ft, flat
        out = {"version": "v348", "grid": len(grid), "m3_dev4": dict(v347.W_metrics(cache[g0], [0, 1, 2, 3]), F=round(fit(cache[g0], [0, 1, 2, 3]), 4)),
               "folds": {}}
        gains = []
        for k in (2, 3):
            ys = list(range(k))
            ch, ft, flat = choose(ys)
            f_ch, f0 = v347.f_single(cache[ch], [k]), v347.f_single(cache[g0], [k])
            out["folds"][k] = dict(choice=decode(ch), train_F=round(ft[ch], 4), flat=round(flat[ch], 4), m3_train_F=round(ft[g0], 4),
                                   test=dict(v347.W_metrics(cache[ch], [k]), F=round(f_ch, 4)), m3_test=dict(v347.W_metrics(cache[g0], [k]), F=round(f0, 4)))
            gains.append(ch != g0 and f_ch > f0)
            log(f"FOLD {k} choice {decode(ch)} TEST {out['folds'][k]['test']} vs M3 {out['folds'][k]['m3_test']}")
        out["transfer"] = bool(all(gains))
        log(f"TRANSFER {out['transfer']}")
        ys = [0, 1, 2, 3]
        ch, ft, flat = choose(ys)
        full = pool.apply(run_rules, (ch, True))
        out["final"] = dict(choice=decode(ch), dev4=dict(v347.W_metrics(cache[ch], ys), F=round(ft[ch], 4)), flat=round(flat[ch], 4),
                            m3_F=round(ft[g0], 4), last_year=v347.W_metrics(full, [4]), five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]),
                            full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")},
                            replaces_m3=bool(out["transfer"] and ft[ch] > ft[g0]))
        log(f"FINAL {json.dumps(out['final'], default=str)}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v348_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
