"""v355: BOT product - BTC-HEDGED dip rungs (registry v355, registered before running; engine_user sleeve_hedge hook, default-neutral).

Dev-only event study (research/diagnostics/hedged_dip, holding bars 2021-09-24 .. 2025-09-17): 3-sigma dip limits on ETH / SOL / BNB / XRP hedged
with an equal-notional BTC short opened at the fill (taker) and closed at the rung's exit stay positive in every dev year (mean +0.24 / +0.17 /
+0.09 / +0.16 % per fill vs unhedged +0.47 / +0.15 / +0.47 / +0.54) with a thinner left tail (5 % quantile -1.95 / -2.56 / -1.69 / -1.70 vs
-3.02 / -3.90 / -2.50 / -1.88): about half of the dip edge is idiosyncratic. The BOT's drawdowns come from market-wide flushes (many rungs stop
together), so a BTC hedge should cut the DD more than the return. A bot opens the hedge with a market order at the fill (not human-feasible).
Rows (fixed before running; everything else = v306 seed R2; BTC rungs unhedged; the hedge short earns no funding):
  R2     = no hedge (reference; dev4 7.079)
  HD50   = sleeve_hedge (0.5, BTC)
  HD100  = sleeve_hedge (1.0, BTC)
CHOICE: dev folds k = 1, 2, 3 with the v306 BOT fitness (R/8, W/5, 15/DD, all-trade win/0.65) on years [:k]; TRANSFER if HD50 / HD100 is chosen and
beats R2 on the unseen dev year in >= 2 of 3 folds. Final choice on dev4; the most recent year computed once for it. Contaminated by design.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v355/v355_hedged_dip_bot.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
ROWS = dict(R2=None, HD50=0.5, HD100=1.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v306 = _load("v306_hd", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu = v306.W["eu"]
    sim0 = eu.simulate
    g = v306.encode(v306.SEEDS["R2"])

    def run(row, full=False):
        h = ROWS[row]
        b = list(v306.W["cols"]).index("BTCUSDT")

        def sim(*a, **kw):
            if h is not None:
                kw["sleeve_hedge"] = (h, b)
            return sim0(*a, **kw)
        eu.simulate = sim
        try:
            return v306.run_genome(g, full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in ROWS}
    assert abs(v306.metrics(res["R2"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out = {"version": "v355", "rows": {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4),
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
    (HERE / "v355_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
