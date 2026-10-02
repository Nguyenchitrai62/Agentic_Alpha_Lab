"""v318: MANUAL product - combination of the components that generalised, at the AGENTS leverage baseline (registry v318).

Components (each judged on dev folds and then scored once on the most recent year in its own version - so v318 is DESIGNED WITH KNOWLEDGE OF THE
MOST RECENT YEAR; its most-recent-year number is reported but is NOT clean evidence; the prospective paper log is):
  books  M2 = (2 A + 2 PT + D) / 5, PT = pooled-experience TV member (v317, 77 coins for training)
  entry  pullback limit 0.75 sigma_4h in the signal direction, orders valid 3 bars (v315)
  management (v309 genes) G0 none | G1 loss_act = tighten (SL to `tighten` sigma_d on a lost signal while under water) |
                          G2 G1 + partial take-profit (2 sigma_d, 1/2) | G3 partial take-profit only
  risk   cap 2 (AGENTS baseline; every GA final with cap 4-6 failed the most recent year): target 0.25 | 0.30 (the v310 gene values)
CHOICE (fixed before running): dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k] (8 configurations, no neighbours: categorical);
TRANSFER if the chosen config beats G0 / target 0.25 (= v317 pullback M2) on the unseen dev year in both folds. Final choice on dev4; the most recent
year is computed once for it (contaminated, see above).

  python research/parallel/rounds/parallel-20260906-r2/v318/v318_manual_combo.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")
MGMT = {"G0": dict(), "G1": dict(loss_act="tighten"), "G2": dict(loss_act="tighten", partial=(2.0, 0.5)), "G3": dict(partial=(2.0, 0.5))}
RISK = {"t25": 0.25, "t30": 0.30}


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

    v310 = _load("v310_c", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_c", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda n: pd.read_parquet(C / f"member_{n}_pooledtv.parquet").reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("PT") + rd("PTq")) / 2
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    mix = (2 * A + 2 * PT + D) / 5
    W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mix  # (2, 2, 1) weights normalise to exactly the mix
    base_p9 = v310._policy9

    def run(mg, tk, full=False):
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=RISK[tk], cap=2.0, n_valid=3, **MGMT[mg])), full)
        finally:
            v310._policy9 = base_p9

    res = {(mg, tk): run(mg, tk) for mg in MGMT for tk in RISK}
    ref = res[("G0", "t25")]
    assert abs(v310.metrics(ref, [0, 1, 2, 3])["R"] - 3.011) < 0.003  # = v317 MANUAL pullback M2
    out = {"version": "v318", "grid": {}, "folds": {}}
    for k_, r in res.items():
        out["grid"]["/".join(k_)] = dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4))
        log(f"{k_} {out['grid']['/'.join(k_)]}")
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v310.fitness(res[x], ys))
        f_ch, f_ref = v310.fitness(res[ch], [k]), v310.fitness(ref, [k])
        out["folds"][k] = dict(choice=list(ch), test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), ref_test=v310.metrics(ref, [k]), F_ref=round(f_ref, 4))
        deltas.append(f_ch - f_ref)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} | ref {out['folds'][k]['ref_test']} F {f_ref:.4f}")
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v310.fitness(res[x], [0, 1, 2, 3]))
    full = run(*ch, full=True)
    out["final"] = dict(choice=list(ch), dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]),
                        five_years=v310.metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")},
                        contaminated_note="designed with knowledge of the most recent year (see docstring); prospective log = clean evidence")
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v318_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
