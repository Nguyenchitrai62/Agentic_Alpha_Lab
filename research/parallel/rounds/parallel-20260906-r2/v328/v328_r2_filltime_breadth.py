"""v328: BOT product - R2 with FILL-TIME dip agents, with and without the flush-breadth features (registry v328).

R2 (v321) decides the dip size / take-profit once per bar at the bar open (state at the close of minute 0) - the conservative deployable form.
The BOT runs automatically, so a decision AT THE FILL (state at the close of minute f-1, the v293-v302 research form) is executable too, and v302
found that three market-breadth features of the flush (mean / min 30-minute move of the five majors, number of majors already through their
2.5-sigma bid) lower the G2 drawdown (dev DD 17.33 -> 16.49) when known at the fill. Rows (fixed before running; R2 books / rules / ladder
2.5 / 3 / 3.5 / 4 / 5 sigma, agents fitted on the pooled 35-coin fills of all seven depths 2.0 .. 5.0, cross-fitted halves, fills exited before
anchor - 7 days, S1 size and X4 take-profit rules, budget 0.26):
  R2_open   = v321 R2 (bar-open lookup table; reproduces dev4 7.079)
  F0        R2 agents deciding at the fill, the seven v293 state features
  F1        R2 agents deciding at the fill, seven + the three v302 breadth features (both agents)
CHOICE: dev folds k = 1, 2, 3 with the v306 BOT fitness on years [:k]; TRANSFER if a fill-time row is chosen and beats R2_open on the unseen dev year
in >= 2 of 3 folds. Final choice on dev4; the most recent year computed once for it (R2_open's 5.655 is known).

  python research/parallel/rounds/parallel-20260906-r2/v328/v328_r2_filltime_breadth.py
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
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
R2 = (2.5, 3.0, 3.5, 4.0, 5.0)


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

    v302 = _load("v302_f", RD / "v302/v302_flush_breadth.py")
    v293 = v302.v293
    v306 = _load("v306_f", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu, idx, cols = v306.W["eu"], v306.W["idx"], v306.W["cols"]
    g = v306.encode(v306.SEEDS["R2"])
    hooks = {}
    for key, (sc, tc) in {"F0": (list(range(7)), list(range(7))), "F1": (list(range(10)), list(range(10)))}.items():
        v293.RUNGS = U  # experience of every depth
        hooks[key] = v302.build_hooks_breadth(eu, idx, cols, sc, tc)
        log(f"hooks {key} built")
    v293.RUNGS = R2  # the state's rung-depth feature = the R2 ladder depth of rung index r
    tables0 = v306._tables
    sim0 = eu.simulate

    def run(key, full=False):
        if key == "R2_open":
            return v306.run_genome(g, full)
        size, tp = hooks[key]

        def sim(*a, **kw):
            kw["sleeve_fill_size"], kw["sleeve_tp"] = size, tp
            return sim0(*a, **kw)
        eu.simulate = sim
        try:
            return v306.run_genome(g, full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in ("R2_open", "F0", "F1")}
    assert abs(v306.metrics(res["R2_open"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out = {"version": "v328", "rows": {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v306.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains = 0
    for k in (1, 2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v306.fitness(res[x], ys))
        f_ch, f_o = v306.fitness(res[ch], [k]), v306.fitness(res["R2_open"], [k])
        out["folds"][k] = dict(choice=ch, test=v306.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_open=round(f_o, 4))
        gains += int(ch != "R2_open" and f_ch > f_o)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs R2_open {f_o:.4f}")
    out["transfer"] = dict(gain_folds=gains, holds=bool(gains >= 2))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v306.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v306.metrics(res[ch], [0, 1, 2, 3]), last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v328_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
