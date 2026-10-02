"""v331: MANUAL product - break-even trigger x break-even level x target on M2, aimed at the two floor metrics closest to their thresholds
(registry v331).

M2 (v317: (2A + 2PT + D)/5, pullback entry 0.75 sigma_4h / 3 bars, cap 2, target 0.25) misses the MANUAL floor on return (5y 3.16 vs 5), drawdown
(full path 20.57 vs < 20) and win rate (5y 0.537 vs >= 0.55). Break-even exits at entry are counted as losses (net -fees); a break-even level
slightly above entry turns them into small wins, an earlier trigger protects more trades, a lower target trims the drawdown. Three dials:
  be_k (break-even after + k sigma_d) 2.0 (M2) / 1.5      be_off (level above entry) 0.001 (M2) / 0.004      target 0.25 (M2) / 0.22
CHOICE (fixed before running): dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k] (8 configurations, categorical: no neighbours);
TRANSFER if the choice beats M2 on the unseen dev year in both folds. Final on dev4; the most recent year computed once (contaminated by design).

  python research/parallel/rounds/parallel-20260906-r2/v331/v331_manual_breakeven.py
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
GRID = [(bk, bo, tg) for bk in (2.0, 1.5) for bo in (0.001, 0.004) for tg in (0.25, 0.22)]


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

    v310 = _load("v310_be", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_be", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    ti = [n for n, _ in v310.GENES].index("target")  # target 0.22 is not a v310 gene value: add it (genomes are encoded fresh here)
    v310.GENES[ti] = ("target", (0.22,) + tuple(v for v in v310.GENES[ti][1] if v != 0.22))
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda n: pd.read_parquet(C / f"member_{n}_pooledtv.parquet").reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("PT") + rd("PTq")) / 2
    mix = (2 * W0["grp"]["wA"] + 2 * PT + W0["grp"]["wD"]) / 5
    W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mix
    base_p9 = v310._policy9

    def run(bk, bo, tg, full=False):
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=tg, cap=2.0, n_valid=3, be_k=bk, be_off=bo)), full)
        finally:
            v310._policy9 = base_p9

    res = {c: run(*c) for c in GRID}
    ref = res[(2.0, 0.001, 0.25)]
    assert abs(v310.metrics(ref, [0, 1, 2, 3])["R"] - 3.011) < 0.003
    for k, r in res.items():
        log(f"{k} dev4 {v310.metrics(r, [0, 1, 2, 3])} F {v310.fitness(r, [0, 1, 2, 3]):.4f}")

    def flat(c, ys):  # categorical grid: the configuration itself
        return v310.fitness(res[c], ys)

    out = {"version": "v331", "grid": {str(k): v310.metrics(r, [0, 1, 2, 3]) for k, r in res.items()}, "folds": {}}
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
    (HERE / "v331_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
