"""v345: BOT product - move risk from the book to the dip ladder: R2 with a smaller book (registry v345, registered before running).

The BOT R2 (v321: CB books + dip ladder 2.5..5.0 sigma with bot close5 stops, R2 agents, budget 0.26) has dev4 7.079, dev DD 18.39; the G2 DD
anatomy (research/diagnostics/g2_dd) puts about half of the drawdown in the BOOK's one-way concentration. In the MANUAL product moving risk
from the book to the dip limits (engine trade-mode book_mult: position size only, the signal threshold keeps the unscaled target; dip sizes
unchanged) transferred (v340 / v342). Rows (fixed before running; everything else = v306 seed R2):
  R2    = book_mult 1.00 (reference; dev4 7.079)
  RB75  = book_mult 0.75
  RB50  = book_mult 0.50
CHOICE: dev folds k = 1, 2, 3 with the v306 BOT fitness (g = R/8, W/5, 15/DD, all-trade win/0.65) on years [:k]; TRANSFER if RB75 / RB50 is
chosen and beats R2 on the unseen dev year in >= 2 of 3 folds. Final choice on dev4; the most recent year computed once for it.
Contaminated by design (R2 was chosen after earlier looks at the most recent year); prospective paper log = clean evidence.

  python research/parallel/rounds/parallel-20260906-r2/v345/v345_bot_book_share.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
ROWS = dict(R2=1.0, RB75=0.75, RB50=0.5)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v306 = _load("v306_bb", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu = v306.W["eu"]
    sim0 = eu.simulate
    g = v306.encode(v306.SEEDS["R2"])

    def run(row, full=False):
        bm = ROWS[row]

        def sim(*a, **kw):
            if bm != 1.0:
                kw["trade"] = dict(kw["trade"], book_mult=bm)
            return sim0(*a, **kw)
        eu.simulate = sim
        try:
            return v306.run_genome(g, full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in ROWS}
    assert abs(v306.metrics(res["R2"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out = {"version": "v345", "rows": {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v306.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    wins = 0
    for k in (1, 2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v306.fitness(res[x], ys))
        f_ch, f0 = v306.fitness(res[ch], [k]), v306.fitness(res["R2"], [k])
        out["folds"][k] = dict(choice=ch, test=v306.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_R2=round(f0, 4))
        wins += int(ch != "R2" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], round(f_ch, 4), "vs R2", round(f0, 4), flush=True)
    out["transfer"] = dict(gain_folds=wins, holds=bool(wins >= 2))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v306.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v306.metrics(res[ch], [0, 1, 2, 3]), last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v345_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
