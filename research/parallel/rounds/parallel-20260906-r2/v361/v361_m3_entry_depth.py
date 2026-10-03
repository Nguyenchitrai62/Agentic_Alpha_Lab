"""v361: PULLBACK ENTRY DEPTH of the MANUAL book in M3 (registry v361, registered before running).

M3's book enters with a resting limit 0.75 sigma_4h behind the price, valid 3 bars (v315, chosen for the book-only product before the dip limits
existed). With two bracket dip limits per coin in the same account the best book entry depth may differ. Rows (fixed before running; everything
else = M3, kpack inputs):
  M3    = k_entry 0.75 (reference, dev4 6.233)
  KE50  = k_entry 0.50
  KE100 = k_entry 1.00
Fitness / protocol as v347-v360 (MANUAL fitness, all-trade win): dev folds k = 2, 3 on years [:k]; TRANSFER if KE50 / KE100 is chosen and beats M3 on
the unseen dev year in both folds; final on dev4; most recent year once. Contaminated by design; prospective log = clean evidence.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v361/v361_m3_entry_depth.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
KE = {"M3": 0.75, "KE50": 0.50, "KE100": 1.00}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v347 = _load("v347_ke", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu = v347.W["v310"].W["eu"]
    sim0 = eu.simulate

    v315 = v347.W["v315"]
    we0 = v315.with_entry

    def run(row, full=False):
        v315.with_entry = lambda k: we0(KE[row])  # v347.run_genome calls v315.with_entry(0.75)
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            v315.with_entry = we0

    res = {k: run(k) for k in KE}
    assert abs(v347.W_metrics(res["M3"], [0, 1, 2, 3])["R"] - 6.233) < 0.003
    out = {"version": "v361", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v347.W_metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, "dev4", v["dev4"], "F", v["F"], flush=True)
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v347.fitness(res[x], ys))
        f_ch, f0 = v347.f_single(res[ch], [k]), v347.f_single(res["M3"], [k])
        out["folds"][k] = dict(choice=ch, test=dict(v347.W_metrics(res[ch], [k]), F=round(f_ch, 4)), m3_F=round(f0, 4))
        gains.append(ch != "M3" and f_ch > f0)
        print("FOLD", k, ch, out["folds"][k]["test"], "vs M3", round(f0, 4), flush=True)
    out["transfer"] = bool(all(gains))
    print("TRANSFER", out["transfer"], flush=True)
    ch = max(res, key=lambda x: v347.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v361_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
