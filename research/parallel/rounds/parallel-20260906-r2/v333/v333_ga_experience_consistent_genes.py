"""v333: MANUAL product - learn from the GA EXPERIENCE: keep only genes whose effect is positive in EVERY training year (registry v333).

The walk-forward GAs (v309 / v310, identical 27-gene space) evaluated ~9.7k book configurations, each with per-dev-year results (eval caches).
Their single winners overfit (a configuration can win on one strong year), so v333 uses the whole population as experience instead of its
best member: per training year y, a ridge regression of the single-year MANUAL fitness F({y}) on the one-hot gene values; a gene value is ADOPTED
only if its coefficient minus the base value's coefficient is > 0 in EVERY training year and > 0.005 on average (the most consistent value wins).
Risk genes are NOT selectable (every dev year rewards leverage, the most recent year did not - v307 / v314): target 0.25, cap 2 and the governor
stay at the AGENTS baseline. Base = the audited G2 manual configuration (v310 seed G2_manual: dev4 2.502).
PROTOCOL (fixed before running): folds k = 2, 3: genes chosen from years [:k] (caches only - no new search), the resulting configuration simulated
and scored on year k against the base; TRANSFER if it beats the base (v310 single-year fitness) in both folds. Final: genes from the four dev years;
the most recent year computed once. Contaminated by design (the gene families were shaped with knowledge of the most recent year in v307-v318);
prospective log = clean evidence.

  python research/parallel/rounds/parallel-20260906-r2/v333/v333_ga_experience_consistent_genes.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge

HERE = Path(__file__).parent
RD = HERE.parent
FIXED = ("target", "cap", "gov")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v310 = _load("v310_x", RD / "v310/v310_manual_book_robust_evolution.py")
    cache = {}
    for v in ("v309", "v310"):
        for line in (RD / v / "eval_cache.jsonl").read_text().splitlines():
            if line.strip():
                x = json.loads(line)
                cache[tuple(x["g"])] = x
    G = np.array(list(cache), int)
    names = [n for n, _ in v310.GENES]
    sizes = [len(vals) for _, vals in v310.GENES]
    off = np.cumsum([0] + sizes[:-1])
    X = np.zeros((len(G), sum(sizes)))
    for q in range(len(names)):
        X[np.arange(len(G)), off[q] + G[:, q]] = 1.0
    Fy = {y: np.array([v310.fitness_pooled(cache[tuple(g)], [y]) for g in G]) for y in range(4)}
    base = v310.encode(v310.SEEDS["G2_manual"])
    print("genomes", len(G), "one-hot columns", X.shape[1], flush=True)

    def choose(ys):
        coef = {}
        for y in ys:
            coef[y] = Ridge(alpha=10.0).fit(X, Fy[y]).coef_
        g = list(base)
        picks = {}
        for q, n in enumerate(names):
            if n in FIXED:
                continue
            b = base[q]
            best, best_m = b, 0.005
            for vi in range(sizes[q]):
                if vi == b:
                    continue
                d = [coef[y][off[q] + vi] - coef[y][off[q] + b] for y in ys]
                if all(x > 0 for x in d) and float(np.mean(d)) > best_m:
                    best, best_m = vi, float(np.mean(d))
            if best != b:
                g[q] = best
                picks[n] = dict(value=str(v310.GENES[q][1][best]), mean_delta=round(best_m, 4))
        return tuple(g), picks

    v310.init_worker()
    rb = v310.run_genome(base)
    assert abs(v310.metrics(rb, [0, 1, 2, 3])["R"] - 2.502) < 0.003
    out = {"version": "v333", "genomes": len(G), "folds": {}}
    deltas = []
    for k in (2, 3):
        g, picks = choose(list(range(k)))
        r = cache.get(g) or v310.run_genome(g)
        f, f0 = v310.fitness_pooled(r, [k]), v310.fitness_pooled(rb, [k])
        out["folds"][k] = dict(picks=picks, test=v310.metrics(r, [k]), F_test=round(f, 4), base_test=v310.metrics(rb, [k]), F_base=round(f0, 4))
        deltas.append(f - f0)
        print("FOLD", k, picks, "TEST", out["folds"][k]["test"], "F", round(f, 4), "| base", round(f0, 4), flush=True)
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    g, picks = choose([0, 1, 2, 3])
    full = v310.run_genome(g, True)
    out["final"] = dict(picks=picks, genome=v310.decode(g), dev4=v310.metrics(full, [0, 1, 2, 3]), last_year=v310.metrics(full, [4]),
                        five_years=v310.metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v333_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
