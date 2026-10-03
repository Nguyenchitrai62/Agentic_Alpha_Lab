"""v371: BOT product - EXHAUSTIVE walk-forward search over the trader genes found in the MANUAL work, applied to R2 (registry v371).

The MANUAL research found three book-management levers (book_mult v340, book SL 5 / TP 10 v362, loss_act tighten v367); on R2 each was tested alone
(v345, v363, v368) and kept R2. v371 searches their JOINT space together with the two dip-risk genes of the ladder, exhaustively (no GA sampling
noise; kpack inputs ~4 s per simulation):
  book_mult (0.5, 0.75, 1.0) x book SL / TP ((4, 8), (5, 10), (6, 12), (4, 10)) x loss_act (close, tighten) x tighten distance (1.0, 1.5, 2.0)
  x dip risk budget (0.22, 0.26, 0.30) x dip close5 stop m_sleeve_sl (3.5, 4.0, 5.0)  -> 648 rows (tighten distance is idle when loss_act = close).
Everything else = v306 seed R2 (CB books, ladder 2.5 / 3 / 3.5 / 4 / 5 sigma, R2 agents, 8-sigma backstop, target 0.25, cap 2).
FITNESS = v306 BOT fitness (R/8, W/5, 15/DD, all-trade win/0.65; losing year -> -1 + R/100). CHOICE = flat optimum: among the 20 best rows on years
[:k], the highest mean fitness over the row and all its one-gene neighbours in the grid.
PROTOCOL (fixed before running): folds k = 1, 2, 3: choice on dev years [:k], scored on dev year k against R2; TRANSFER if it beats R2 in >= 2 of 3
folds. Final choice on dev4; the most recent year computed once for it. Contaminated by design (genes found after earlier looks at the last year).

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v371/v371_bot_trader_grid.py [--workers 3]
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

HERE = Path(__file__).parent
RD = HERE.parent
GENES = [("book_mult", (0.5, 0.75, 1.0)), ("sltp", ((4.0, 8.0), (5.0, 10.0), (6.0, 12.0), (4.0, 10.0))), ("loss_act", ("close", "tighten")),
         ("tighten", (1.0, 1.5, 2.0)), ("budget", (0.22, 0.26, 0.30)), ("sleeve_sl", (3.5, 4.0, 5.0))]
R2G = dict(book_mult=1.0, sltp=(4.0, 8.0), loss_act="close", tighten=1.5, budget=0.26, sleeve_sl=4.0)
W = {}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def decode(g):
    return {n: vals[i] for (n, vals), i in zip(GENES, g)}


def encode(d):
    return tuple(vals.index(d[n]) for n, vals in GENES)


def init_worker():
    v306 = _load("v306_tg", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    W.update(v306=v306, base=v306.encode(v306.SEEDS["R2"]))


def run_row(g, full=False):
    v306 = W["v306"]
    d = decode(g)
    eu = v306.W["eu"]
    sim0 = eu.simulate

    def sim(*a, **kw):
        kw["m_sl"], kw["m_tp"] = d["sltp"]
        kw["sleeve_risk_budget"], kw["m_sleeve_sl"] = d["budget"], d["sleeve_sl"]
        tr = dict(kw["trade"], book_mult=d["book_mult"], tighten=d["tighten"])
        if d["loss_act"] == "tighten":
            pol = tr["policy"]
            tr["policy"] = lambda i, a_, s_: "tighten" if s_["pos"] != 0 and s_["sgn"] == 0 and s_["upnl"] < 0 else pol(i, a_, s_)
        kw["trade"] = tr
        return sim0(*a, **kw)
    eu.simulate = sim
    try:
        res = v306.run_genome(W["base"], full)
    finally:
        eu.simulate = sim0
    res["g"] = list(g)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    grid = list(itertools.product(*[range(len(v)) for _, v in GENES]))
    cache_p = HERE / "eval_cache.jsonl"
    cache = {}
    if cache_p.exists():
        for line in cache_p.read_text().splitlines():
            if line.strip():
                x = json.loads(line)
                cache[tuple(x["g"])] = x
    todo = [g for g in grid if g not in cache]
    log(f"grid {len(grid)} cached {len(cache)} todo {len(todo)}")
    with mp.Pool(args.workers, initializer=init_worker) as pool:
        for n, x in enumerate(pool.imap_unordered(run_row, todo, chunksize=4)):
            cache[tuple(x["g"])] = x
            with cache_p.open("a") as fh:
                fh.write(json.dumps(x, default=str) + "\n")
            if n % 100 == 0:
                log(f"  evaluated {n + 1} / {len(todo)}")
        init_worker()
        v306 = W["v306"]
        g0 = encode(R2G)
        assert abs(v306.metrics(cache[g0], [0, 1, 2, 3])["R"] - 7.079) < 0.003
        fit = v306.fitness

        def neighbours(g):
            out = []
            for q, (_, vals) in enumerate(GENES):
                for v in range(len(vals)):
                    if v != g[q]:
                        c = list(g)
                        c[q] = v
                        out.append(tuple(c))
            return out

        def choose(ys):
            ft = {g: fit(cache[g], ys) for g in grid}
            top = sorted(grid, key=lambda g: -ft[g])[:20]
            flat = {g: float(np.mean([ft[g]] + [ft[c] for c in neighbours(g)])) for g in top}
            return max(flat, key=lambda g: flat[g]), ft
        out = {"version": "v371", "grid": len(grid), "r2_dev4": v306.metrics(cache[g0], [0, 1, 2, 3]), "folds": {}}
        wins = 0
        for k in (1, 2, 3):
            ys = list(range(k))
            ch, ft = choose(ys)
            f_ch, f0 = fit(cache[ch], [k]), fit(cache[g0], [k])
            out["folds"][k] = dict(choice={n: str(v) for n, v in decode(ch).items()}, train_F=round(ft[ch], 4),
                                   test=dict(v306.metrics(cache[ch], [k]), F=round(f_ch, 4)), r2_test=dict(v306.metrics(cache[g0], [k]), F=round(f0, 4)))
            wins += int(ch != g0 and f_ch > f0)
            log(f"FOLD {k} {out['folds'][k]}")
        out["transfer"] = dict(gain_folds=wins, holds=bool(wins >= 2))
        log(f"TRANSFER {out['transfer']}")
        ch, ft = choose([0, 1, 2, 3])
        full = pool.apply(run_row, (ch, True))
        out["final"] = dict(choice={n: str(v) for n, v in decode(ch).items()}, dev4=dict(v306.metrics(cache[ch], [0, 1, 2, 3]), F=round(ft[ch], 4)),
                            r2_F=round(ft[g0], 4), last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                            full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
        log(f"FINAL {json.dumps(out['final'], default=str)}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v371_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
