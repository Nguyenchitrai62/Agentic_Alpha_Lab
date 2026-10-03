"""v363: BOT product - BOOK stop / take-profit multiples of R2 (registry v363, registered before running).

v362: in the MANUAL product M3, a wider book bracket (SL 5 / TP 10 sigma_d instead of 4 / 8) was the dev4 choice and better on every robustness
row (fold transfer not confirmed). The BOT R2 uses the same book bracket 4 / 8 (v306 gene m_sl 4.0, TP = 2 x SL). Rows (fixed before running;
engine m_sl / m_tp on the book only; everything else = v306 seed R2, kpack inputs):
  R2     = SL 4 / TP 8 (reference; dev4 7.079)
  BS5    = SL 5 / TP 10
  BS6    = SL 6 / TP 12
CHOICE: dev folds k = 1, 2, 3 with the v306 BOT fitness (R/8, W/5, 15/DD, all-trade win/0.65) on years [:k]; TRANSFER if BS5 / BS6 is chosen and beats
R2 on the unseen dev year in >= 2 of 3 folds. Final choice on dev4; the most recent year computed once for it. Contaminated by design.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v363/v363_bot_book_sltp.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
ROWS = dict(R2=None, BS5=(5.0, 10.0), BS6=(6.0, 12.0))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v306 = _load("v306_bs", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu = v306.W["eu"]
    sim0 = eu.simulate
    g = v306.encode(v306.SEEDS["R2"])

    def run(row, full=False):
        st = ROWS[row]

        def sim(*a, **kw):
            if st is not None:
                kw["m_sl"], kw["m_tp"] = st
            return sim0(*a, **kw)
        eu.simulate = sim
        try:
            return v306.run_genome(g, full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in ROWS}
    assert abs(v306.metrics(res["R2"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out = {"version": "v363", "rows": {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4),
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
    (HERE / "v363_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
