"""v366: trader-MANAGEMENT genes on M4's book - the book win rate goal (registry v366, registered before running).

Goal 1 (MANUAL) asks for a book win rate >= 55 %; M4 books win ~0.51 dev. v365: a partial take-profit does not move it (a book trade is scored on its
position net). v309 found the management genes that changed the MANUAL book win rate in the walk-forward GA: loss_act (what to do when the signal goes
flat while the position is under water) and lock (close the position once its unrealised profit reaches `lock` sigma_d). Rows (fixed before
running; v310 _policy9 genes via v310.encode; everything else = M4: book SL 5 / TP 10, CB books x0.75, bracket dip limits 3.0 / 4.0 sigma):
  M4     = loss_act close, lock None (reference, dev4 6.392)
  LT     = loss_act tighten
  LK3    = lock 3.0
Fitness / protocol as v347-v365 (MANUAL fitness, all-trade win; the book win rate is reported per row): dev folds k = 2, 3 on years [:k]; TRANSFER if
LT / LK3 is chosen and beats M4 on the unseen dev year in both folds; final on dev4; most recent year once.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v366/v366_m4_management.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
MG = {"M4": {}, "LT": dict(loss_act="tighten"), "LK3": dict(lock=3.0)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_mg", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    sim0 = eu.simulate

    def run(row, full=False):
        def outer(*a, **kw):
            kw["m_sl"], kw["m_tp"] = 5.0, 10.0
            return sim0(*a, **kw)
        v310 = v347.W["v310"]
        enc0 = v310.encode
        eu.simulate = outer
        v310.encode = lambda d: enc0(dict(d, **MG[row]))  # v347.run_genome encodes (target 0.25, cap 2, n_valid 3)
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate = sim0
            v310.encode = enc0

    res = {k: run(k) for k in MG}
    assert abs(v347.W_metrics(res["M4"], [0, 1, 2, 3])["R"] - 6.392) < 0.003
    out = {"version": "v366", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v347.fitness(res[x], ys))
        f_ch, f0 = v347.f_single(res[ch], [k]), v347.f_single(res["M4"], [k])
        out["folds"][k] = dict(choice=ch, test=dict(v347.W_metrics(res[ch], [k]), F=round(f_ch, 4)), m3_F=round(f0, 4))
        gains.append(ch != "M4" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], "vs M4", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v347.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v366_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
