"""v337: bring the OPTIONS-informed member back into both products (registry v337, registered before running).

The Deribit options-flow member (v150 / v151: the v144 book recipe + BTC options trade aggregates per 4h; cached as members_v154 level "B" and
members_quarterly level "B") was 'good alone' in the v154 era and part of v154, but every modern pipeline (CB / G2 / R2 books = 2A + 2B_tv + D;
MANUAL M2 = 2A + 2PT + D) and every v306-v333 gene pool left it out. O = (annual + quarterly)/2 of that member.
ROWS (fixed before running):
  MANUAL (M2 rules: pullback 0.75 sigma_4h / 3 bars, target 0.25, cap 2): M2 = (2A + 2PT + D)/5 | MO1 = (2A + 2PT + D + O)/6 | MO2 = (2A + 2PT + D + 2O)/7
  BOT (R2 machinery: ladder 2.5..5.0, all-depth agents, budget 0.26): R2 = (2A + 2B + D)/5 | BO1 = (2A + 2B + D + O)/6
CHOICE: MANUAL - dev folds k = 2, 3, v310 robust MANUAL fitness; BOT - dev folds k = 1, 2, 3, v306 BOT fitness; TRANSFER (per product) if an options
row is chosen and beats the reference on the unseen year in all its folds (MANUAL) / in >= 2 of 3 folds (BOT). Final per product on dev4; the most
recent year computed once for each final choice.

  python research/parallel/rounds/parallel-20260906-r2/v337/v337_options_member_return.py
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def options_member(idx, cols):
    a = pd.read_parquet(C / "members_v154.parquet").xs("B", axis=1, level=0).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    q = pd.read_parquet(C / "members_quarterly.parquet").xs("B", axis=1, level=0).reindex(idx).fillna(0.0)[cols].to_numpy(float)
    return (a + q) / 2


def main():
    out = {"version": "v337", "manual": {}, "bot": {}}
    # ---------------- MANUAL
    v310 = _load("v310_op", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_op", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    O = options_member(idx, cols)
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    mixes = {"M2": (2 * A + 2 * PT + D) / 5, "MO1": (2 * A + 2 * PT + D + O) / 6, "MO2": (2 * A + 2 * PT + D + 2 * O) / 7}
    base_p9 = v310._policy9

    def run_m(k, full=False):
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mixes[k]
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        try:
            return v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
        finally:
            v310._policy9 = base_p9

    rm = {k: run_m(k) for k in mixes}
    assert abs(v310.metrics(rm["M2"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out["manual"]["rows"] = {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(v310.fitness(r, [0, 1, 2, 3]), 4)) for k, r in rm.items()}
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(rm, key=lambda x: v310.fitness(rm[x], ys))
        f_ch, f0 = v310.fitness(rm[ch], [k]), v310.fitness(rm["M2"], [k])
        out["manual"][f"fold{k}"] = dict(choice=ch, test=v310.metrics(rm[ch], [k]), F_test=round(f_ch, 4), F_M2=round(f0, 4))
        gains.append(ch != "M2" and f_ch > f0)
    out["manual"]["transfer"] = bool(all(gains))
    ch = max(rm, key=lambda x: v310.fitness(rm[x], [0, 1, 2, 3]))
    full = run_m(ch, True)
    out["manual"]["final"] = dict(choice=ch, last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                                  full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("MANUAL", json.dumps(out["manual"], default=str), flush=True)
    # ---------------- BOT
    v306 = _load("v306_op", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    W6 = v306.W
    A6, B6, D6 = W6["grp"]["wA"].copy(), W6["grp"]["wB"].copy(), W6["grp"]["wD"].copy()
    O6 = options_member(W6["idx"], W6["cols"])
    bm = {"R2": (2 * A6 + 2 * B6 + D6) / 5, "BO1": (2 * A6 + 2 * B6 + D6 + O6) / 6}
    g = v306.encode(v306.SEEDS["R2"])

    def run_b(k, full=False):
        W6["grp"]["wA"] = W6["grp"]["wB"] = W6["grp"]["wD"] = bm[k]
        try:
            return v306.run_genome(g, full)
        finally:
            W6["grp"]["wA"], W6["grp"]["wB"], W6["grp"]["wD"] = A6, B6, D6

    rb = {k: run_b(k) for k in bm}
    assert abs(v306.metrics(rb["R2"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out["bot"]["rows"] = {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4)) for k, r in rb.items()}
    wins = 0
    for k in (1, 2, 3):
        ys = list(range(k))
        ch = max(rb, key=lambda x: v306.fitness(rb[x], ys))
        f_ch, f0 = v306.fitness(rb[ch], [k]), v306.fitness(rb["R2"], [k])
        out["bot"][f"fold{k}"] = dict(choice=ch, test=v306.metrics(rb[ch], [k]), F_test=round(f_ch, 4), F_R2=round(f0, 4))
        wins += int(ch != "R2" and f_ch > f0)
    out["bot"]["transfer"] = bool(wins >= 2)
    ch = max(rb, key=lambda x: v306.fitness(rb[x], [0, 1, 2, 3]))
    full = run_b(ch, True)
    out["bot"]["final"] = dict(choice=ch, last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                               full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("BOT", json.dumps(out["bot"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v337_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
