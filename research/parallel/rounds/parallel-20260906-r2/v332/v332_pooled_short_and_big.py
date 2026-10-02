"""v332: two last pooled-experience variants of the TV member for the MANUAL book (registry v332).

PT (v317) = v94 horizons 18 / 42 / 84 on v92 + 17 TV + BTC cross features, HGB depth 4 / 400 iterations, trained on 5 majors + 72 U2020 alts.
  PS  SHORT horizons 6 / 18 bars (1 / 3 days; the book's median holding is ~2 days) - same features, pooled rows, annual + quarterly fits
  PB  BIGGER trees: max_depth 6, 800 iterations (other hyper-parameters as PT) - with ~1M pooled rows the depth-4 model may be under-fitted
Everything else = v317 PT (cutoff = (quarter) start - (84 + 60) bars, labels ending before the cutoff, majors predicted, v94.weights_ls books).
ROWS (MANUAL M2 setting: pullback 0.75 sigma_4h / 3 bars, target 0.25, cap 2): X0 M2 = (2A + 2PT + D)/5 | X1 (2A + 2PB + D)/5 |
  X2 (2A + 2PT + D + PS)/6.
CHOICE: dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k]; TRANSFER if the choice beats X0 on the unseen year in both folds.
Final on dev4; the most recent year once (contaminated by design; prospective log = clean evidence).

  python research/parallel/rounds/parallel-20260906-r2/v332/v332_pooled_short_and_big.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor as HGB

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v317 = _load("v317_sb", RD / "v317/v317_pooled_tv_member.py")


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    names = ("PS", "PSq", "PB", "PBq")
    if not all((C / f"member_{n}_pooled_v332.parquet").exists() for n in names):
        v144 = _load("v144_sb", RD / "v144/v144_deploy_v3.py")
        v94 = v144.v115.v114.v113.v94
        hz0 = v94.HORIZONS
        panel, feats, v92, v94b = v317.build_panel(log)
        # add the 6-bar target (same definition as v94.add_targets)
        import numpy as np
        out = []
        for s, g in panel.groupby("sym", sort=False):
            g = g.sort_values("t").copy()
            o = g["open"].to_numpy()
            n = len(g)
            fwd = np.full(n, np.nan)
            fwd[: n - 1 - 6] = np.log(o[1 + 6:] / o[1: n - 6])
            g["y6"] = np.clip(fwd / (g["vol42"].to_numpy() * np.sqrt(6)), -4, 4)
            out.append(g)
        panel = pd.concat(out, ignore_index=True)
        for n, (kind, q) in {"PS": ("short", False), "PSq": ("short", True), "PB": ("big", False), "PBq": ("big", True)}.items():
            if (C / f"member_{n}_pooled_v332.parquet").exists():
                continue
            if kind == "short":
                v94b.HORIZONS = (6, 18)
                v317.HistGradientBoostingRegressor = HGB
            else:
                v94b.HORIZONS = hz0
                v317.HistGradientBoostingRegressor = lambda **kw: HGB(**dict(kw, max_depth=6, max_iter=800))
            W, ic = v317.fit_books(panel, feats, v92, v94b, True, q, log, n)
            v94b.HORIZONS, v317.HistGradientBoostingRegressor = hz0, HGB
            W.to_parquet(C / f"member_{n}_pooled_v332.parquet")
            log(f"member {n} IC dev (vs y42) {ic}")
    v310 = _load("v310_sb", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_sb", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    PS = (rd("member_PS_pooled_v332.parquet") + rd("member_PSq_pooled_v332.parquet")) / 2
    PB = (rd("member_PB_pooled_v332.parquet") + rd("member_PBq_pooled_v332.parquet")) / 2
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    mixes = {"X0": (2 * A + 2 * PT + D) / 5, "X1": (2 * A + 2 * PB + D) / 5, "X2": (2 * A + 2 * PT + D + PS) / 6}
    base_p9 = v310._policy9

    def run(k, full=False):
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mixes[k]
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
        finally:
            v310._policy9 = base_p9

    res = {k: run(k) for k in mixes}
    assert abs(v310.metrics(res["X0"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out = {"version": "v332", "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4)) for k, r in res.items()},
           "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v310.fitness(res[x], ys))
        f_ch, f0 = v310.fitness(res[ch], [k]), v310.fitness(res["X0"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_X0=round(f0, 4))
        deltas.append(f_ch - f0)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs X0 {f0:.4f}")
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v310.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v332_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
