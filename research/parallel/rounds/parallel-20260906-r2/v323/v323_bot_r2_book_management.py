"""v323: BOT product - R2 with the book components that generalised in the MANUAL research (registry v323).

R2 (v321: G2 + 5-sigma rung, dip agents fitted on every rung depth) is the walk-forward BOT pipeline (5y 6.79, most recent year 5.66, DD 18.39).
Its book part still uses the plain v216 grid trader. Two MANUAL findings generalised to the most recent year: the pullback entry limit
(v315: 0.75 sigma_4h, orders valid 3 bars) and the management gene loss_act = tighten (v309 / v318: on a lost signal while under water, move the
SL to `tighten` sigma_d instead of closing; book win 63-68%). Rows (fixed before running; everything else = R2 exactly, v306 machinery):
  B0 R2 | B1 R2 + loss_act tighten | B2 R2 + pullback entry 0.75 / n_valid 3 | B3 R2 + pullback + loss_act tighten
CHOICE: dev folds k = 2, 3 with the v306 BOT fitness on years [:k] (rows only, no neighbours: categorical); TRANSFER if the choice beats B0 on the
unseen dev year in both folds. Final on dev4; the most recent year computed once for the choice (components were shaped with knowledge of the most
recent year in the MANUAL research -> contaminated; the R2 / G2 paper logs are the clean evidence).

  python research/parallel/rounds/parallel-20260906-r2/v323/v323_bot_r2_book_management.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ROWS = {"B0": (False, False), "B1": (True, False), "B2": (False, True), "B3": (True, True)}


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v306 = _load("v306_b", RD / "v306/v306_walkforward_evolution.py")
    v310 = _load("v310_b", RD / "v310/v310_manual_book_robust_evolution.py")  # _policy9 only (no init)
    v306.init_worker()
    grid0, pol0 = v306.W["v216"].GRID, v306._policy
    g = v306.encode(v306.SEEDS["R2"])

    def run(key, full=False):
        tight, pull = ROWS[key]

        def factory(b_abs, b_rel, cool):
            base = v310._policy9(b_abs, b_rel, cool, "tighten" if tight else "close", "close", None)
            if not pull:
                return base

            def pol(i, a, st):
                return {"open": 0.75} if st["pos"] == 0 else base(i, a, st)
            return pol
        v306._policy = factory
        v306.W["v216"] = SimpleNamespace(GRID=dict(grid0, n_valid=3) if pull else grid0)
        try:
            return v306.run_genome(g, full)
        finally:
            v306._policy = pol0
            v306.W["v216"] = SimpleNamespace(GRID=grid0)

    res = {k: run(k) for k in ROWS}
    assert abs(v306.metrics(res["B0"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out = {"version": "v323", "rows": {}, "folds": {}}
    for k, r in res.items():
        out["rows"][k] = dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4), years=[v306.metrics(r, [y]) for y in range(4)])
        log(f"{k} dev4 {out['rows'][k]['dev4']} F {out['rows'][k]['F']}")
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v306.fitness(res[x], ys))
        f_ch, f_ref = v306.fitness(res[ch], [k]), v306.fitness(res["B0"], [k])
        out["folds"][k] = dict(choice=ch, test=v306.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_B0=round(f_ref, 4))
        deltas.append(f_ch - f_ref)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs B0 {f_ref:.4f}")
    out["transfer"] = dict(deltas=[round(x, 4) for x in deltas], holds=bool(all(x > 0 for x in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: v306.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v306.metrics(res[ch], [0, 1, 2, 3]), last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v323_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
