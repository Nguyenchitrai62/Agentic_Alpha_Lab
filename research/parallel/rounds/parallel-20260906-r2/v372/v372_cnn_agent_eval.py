"""v372: a CNN dip SIZE agent on bar-open 1-minute SEQUENCES (Kaggle GPU) vs the HGB agents (registry v372, registered before running).

The dip size agent decides x1.5 / x1 / x0.5 per rung at the bar open from seven summary state features (HGB, pooled 35-coin experience). v357 added
four hand-made summary features without gain. v372 lets a small 1D-CNN read the previous closed 4h bar's 240 one-minute returns of the coin and of
BTC (plus the seven state features), trained walk-forward on the same pooled fills with the same cross-fitted halves and the same 7-day embargo
(v372_seq_data.py -> v372_cnn_train.py on Kaggle GPU, predictions only). The CNN's pa / pb / mu go through the SAME size rule (x1.5 if both halves >
2 mu, x0.5 if both < 0); take-profit decisions stay with the R2 HGB agent.
ROWS (fixed before running; kpack inputs):
  BOT (primary, goal 2):  R2 (reference, dev4 7.079)  |  R2c = R2 with the CNN size agent
  MANUAL (secondary):     M5 (reference, dev4 6.015)  |  M5c = M5 with the CNN size agent
CHOICE per product: BOT - v306 BOT fitness, folds k = 1, 2, 3, TRANSFER if R2c is chosen and beats R2 on the unseen dev year in >= 2 of 3 folds;
MANUAL - v310 goal-1 fitness (book win), folds k = 2, 3, TRANSFER if M5c is chosen and beats M5 in both folds. Final per product on dev4; the most
recent year computed once for each final. Contaminated by design; prospective log = clean evidence.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v372/v372_cnn_agent_eval.py
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
PRED = Path("artifacts/kaggle/v372/output/v372_cnn_preds.parquet")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cnn_size(idx, cols):
    p = pd.read_parquet(PRED)
    p["T"] = pd.to_datetime(p["T"], utc=True)
    ii = idx.get_indexer(p["T"] - pd.Timedelta(hours=4))
    aa = np.array([list(cols).index(s) for s in p["sym"]])
    kk = np.array([U.index(k) for k in p["k"]])
    ok = ii >= 0
    T = {c: np.full((len(idx), len(cols), len(U)), np.nan) for c in ("pa", "pb", "mu")}
    for c in T:
        T[c][ii[ok], aa[ok], kk[ok]] = p[c].to_numpy(float)[ok]
    size = np.ones_like(T["pa"])
    up = (T["pa"] > 2.0 * T["mu"]) & (T["pb"] > 2.0 * T["mu"])
    dn = (T["pa"] < 0) & (T["pb"] < 0)
    size[up] = 1.5
    size[dn & ~up] = 0.5
    size[~np.isfinite(T["pa"])] = 1.0
    return size


def choose(res, ref, fit, folds, need):
    out, gains = {}, 0
    for k in folds:
        ys = list(range(k))
        ch = max(res, key=lambda x: fit(res[x], ys))
        f_ch, f0 = fit(res[ch], [k]), fit(res[ref], [k])
        out[k] = dict(choice=ch, F_test=round(f_ch, 4), F_ref=round(f0, 4))
        gains += int(ch != ref and f_ch > f0)
    return out, bool(gains >= need)


def main():
    out = {"version": "v372"}
    # ---------------- BOT
    v306 = _load("v306_cn", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    idx, cols = v306.W["idx"], v306.W["cols"]
    sz = cnn_size(idx, cols)
    g = v306.encode(v306.SEEDS["R2"])
    tab0 = v306._tables

    def run_b(cnn, full=False):
        if cnn:
            v306._tables = lambda d: (sz, tab0(d)[1])
        try:
            return v306.run_genome(g, full)
        finally:
            v306._tables = tab0
    rb = {"R2": run_b(False), "R2c": run_b(True)}
    assert abs(v306.metrics(rb["R2"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out["bot_rows"] = {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4)) for k, r in rb.items()}
    out["bot_folds"], out["bot_transfer"] = choose(rb, "R2", v306.fitness, (1, 2, 3), 2)
    ch = max(rb, key=lambda x: v306.fitness(rb[x], [0, 1, 2, 3]))
    full = run_b(ch == "R2c", True)
    out["bot_final"] = dict(choice=ch, last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                            full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("BOT", json.dumps({k: out[k] for k in ("bot_rows", "bot_folds", "bot_transfer", "bot_final")}, default=str), flush=True)
    # ---------------- MANUAL
    v347 = _load("v347_cn", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    v310 = v347.W["v310"]
    eu = v310.W["eu"]
    sim0, enc0 = eu.simulate, v310.encode
    size0 = v347.W["size"].copy()

    def run_m(cnn, full=False):
        def sim(*a, **kw):
            kw["m_sl"], kw["m_tp"] = 5.0, 10.0
            return sim0(*a, **kw)
        eu.simulate = sim
        v310.encode = lambda d: enc0(dict(d, loss_act="tighten"))
        if cnn:
            v347.W["size"] = sz
        try:
            return v347.run_genome(v347.encode(v347.SEEDS["CB"]), full)
        finally:
            eu.simulate, v310.encode = sim0, enc0
            v347.W["size"] = size0
    rm = {"M5": run_m(False), "M5c": run_m(True)}
    assert abs(v347.W_metrics(rm["M5"], [0, 1, 2, 3])["R"] - 6.015) < 0.003
    fit = v310.fitness
    out["manual_rows"] = {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(fit(r, [0, 1, 2, 3]), 4)) for k, r in rm.items()}
    out["manual_folds"], out["manual_transfer"] = choose(rm, "M5", fit, (2, 3), 2)
    ch = max(rm, key=lambda x: fit(rm[x], [0, 1, 2, 3]))
    full = run_m(ch == "M5c", True)
    out["manual_final"] = dict(choice=ch, last_year=v347.W_metrics(full, [4]), five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]),
                               full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("MANUAL", json.dumps({k: out[k] for k in ("manual_rows", "manual_folds", "manual_transfer", "manual_final")}, default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v372_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
