"""v314: MANUAL product - LOW-DIMENSIONAL walk-forward risk dial on the audited G2 book rules (registry v314).

Why (dev folds, v307): a 20-gene GA transfers in one fold (unseen 2023 +0.189) but not in the other (unseen 2024 -0.004), and its winners change
many rules at once (theta, stop width, break-even, partial take-profit, cool-down). Overfitting grows with the degrees of freedom; the dev
diagnostic (research/diagnostics/book_vs_bot) showed that the book's flat return frontier came from ONE mechanical limit, the vol-scale cap 2.
v314 keeps every audited G2 book rule (members A2 B2 D1, grid trader, SL 4 sigma_d, TP 8 sigma_d, break-even +2 sigma_d, theta 0.05) and chooses
ONLY the risk dial walk-forward: target in {0.25, 0.30, 0.37, 0.44, 0.52} x cap in {2, 3, 4, 5} (20 configurations; engine_user cross margin +
1m liquidation check, majors only).
Disclosure: designed after v307, whose fold-3 transfer failure (dev) motivated the reduction; v307's final genome was also scored once on the
most recent year (0.10 %/month) - that score is not used here (no configuration of v314 is chosen with it).
CHOICE for a test year k (k = 2, 3 dev folds; k = 4 the most recent year, once): the v310 robust MANUAL fitness on years [:k] (0.5 worst single
year + 0.5 pooled; MANUAL goal-1 floor first: R / 5, 20 / DD, book win / 0.55, no losing year; then goal 2 easiest first), averaged over the
configuration and its grid neighbours (+-1 step of target or cap) -> flat choice.
REPORT per fold: the chosen dial on the unseen year vs (a) the audited G2 manual (target 0.25, cap 2) and (b) the v307 fold winners (same fitness,
same year). TRANSFER holds if F_test(chosen) > F_test(G2 manual) in both dev folds. The most recent year is scored once for the dev4 choice.

  python research/parallel/rounds/parallel-20260906-r2/v314/v314_manual_risk_dial_walkforward.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
RD = HERE.parent
TARGETS = (0.25, 0.30, 0.37, 0.44, 0.52)
CAPS = (2.0, 3.0, 4.0, 5.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v310 = _load("v310_d", RD / "v310/v310_manual_book_robust_evolution.py")


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v310.init_worker()
    grid = {(t, c): v310.encode(dict(target=t, cap=c)) for t in TARGETS for c in CAPS}
    res = {k: v310.run_genome(g) for k, g in grid.items()}
    ref = res[(0.25, 2.0)]
    assert abs(v310.metrics(ref, [0, 1, 2, 3])["R"] - 2.502) < 0.003
    for k, r in res.items():
        log(f"dial {k} dev4 {v310.metrics(r, [0, 1, 2, 3])}")

    def flat(k, ys):
        ti, ci = TARGETS.index(k[0]), CAPS.index(k[1])
        nb = [k] + [(TARGETS[ti + d], k[1]) for d in (-1, 1) if 0 <= ti + d < len(TARGETS)] + \
             [(k[0], CAPS[ci + d]) for d in (-1, 1) if 0 <= ci + d < len(CAPS)]
        return float(np.mean([v310.fitness(res[x], ys) for x in nb]))

    v307 = json.loads((RD / "v307/v307_result.json").read_text())
    out = {"version": "v314", "grid": {str(k): v310.metrics(r, [0, 1, 2, 3]) for k, r in res.items()}, "folds": {}}
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: flat(x, ys))
        f_ch, f_ref = v310.fitness(res[ch], [k]), v310.fitness(ref, [k])
        v7 = {sd: r["test"] for sd, r in v307["folds"][str(k)]["runs"].items()}
        out["folds"][k] = dict(choice=list(ch), train=v310.metrics(res[ch], ys), test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4),
                               G2_manual_test=v310.metrics(ref, [k]), F_G2=round(f_ref, 4), v307_winners_test=v7)
        deltas.append(f_ch - f_ref)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} | G2 manual F {f_ref:.4f} | v307 winners {v7}")
    out["transfer"] = dict(deltas=[round(d, 4) for d in deltas], holds=bool(all(d > 0 for d in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ys = [0, 1, 2, 3]
    ch = max(res, key=lambda x: flat(x, ys))
    full = v310.run_genome(grid[ch], True)
    out["final"] = dict(choice=list(ch), dev4=v310.metrics(res[ch], ys), last_year=v310.metrics(full, [4]),
                        five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={k: full[k] for k in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years", "monthly_dev4")},
                        recommended=out["transfer"]["holds"])
    log(f"FINAL choice {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v314_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
