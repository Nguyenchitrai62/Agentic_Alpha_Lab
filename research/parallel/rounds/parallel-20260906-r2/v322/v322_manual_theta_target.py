"""v322: MANUAL product - walk-forward choice of the signal threshold (theta) x vol target on the best general MANUAL setting (registry v322).

Setting = v317 M2: books (2 A + 2 PT + D) / 5 with the pooled TV member, pullback entry 0.75 sigma_4h / 3 bars, G2 grid trader, SL 4 / TP 8 sigma_d,
cap 2 (AGENTS baseline). Two dials only: theta (minimum |target weight| to open, the book's trade filter) 0.05 (M2) / 0.08 / 0.12 and target
0.25 (M2) / 0.30 / 0.37 (within cap 2). theta 0.08 lowered the dev DD of the G2 manual book (v307 seed: 3.05 %/month, DD 15.2 vs 2.50 / 16.4);
a higher theta keeps only strong signals (fewer, better trades) and may allow a higher target at the same DD.
CHOICE (fixed before running): dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k], averaged over the grid point and its +-1-step
neighbours (flat choice); TRANSFER if the choice beats M2 (theta 0.05, target 0.25) on the unseen dev year in both folds. Final on dev4; the most
recent year computed once (the setting was shaped with knowledge of the most recent year - contaminated; prospective log = clean evidence).

  python research/parallel/rounds/parallel-20260906-r2/v322/v322_manual_theta_target.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")
THETAS = (0.05, 0.08, 0.12)
TARGETS = (0.25, 0.30, 0.37)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v310 = _load("v310_q", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_q", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda n: pd.read_parquet(C / f"member_{n}_pooledtv.parquet").reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("PT") + rd("PTq")) / 2
    mix = (2 * W0["grp"]["wA"] + 2 * PT + W0["grp"]["wD"]) / 5
    W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mix
    base_p9 = v310._policy9

    def run(th, tg, full=False):
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=tg, cap=2.0, n_valid=3, theta=th)), full)
        finally:
            v310._policy9 = base_p9

    res = {(th, tg): run(th, tg) for th in THETAS for tg in TARGETS}
    ref = res[(0.05, 0.25)]
    assert abs(v310.metrics(ref, [0, 1, 2, 3])["R"] - 3.011) < 0.003
    for k, r in res.items():
        log(f"{k} dev4 {v310.metrics(r, [0, 1, 2, 3])} F {v310.fitness(r, [0, 1, 2, 3]):.4f}")

    def flat(c, ys):
        a, b = THETAS.index(c[0]), TARGETS.index(c[1])
        nb = [c] + [(THETAS[a + d], c[1]) for d in (-1, 1) if 0 <= a + d < 3] + [(c[0], TARGETS[b + d]) for d in (-1, 1) if 0 <= b + d < 3]
        return float(np.mean([v310.fitness(res[x], ys) for x in nb]))

    out = {"version": "v322", "grid": {str(k): v310.metrics(r, [0, 1, 2, 3]) for k, r in res.items()}, "folds": {}}
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: flat(x, ys))
        f_ch, f_ref = v310.fitness(res[ch], [k]), v310.fitness(ref, [k])
        out["folds"][k] = dict(choice=list(ch), test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_M2=round(f_ref, 4))
        deltas.append(f_ch - f_ref)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs M2 {f_ref:.4f}")
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: flat(x, [0, 1, 2, 3]))
    full = run(*ch, full=True)
    out["final"] = dict(choice=list(ch), dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v322_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
