"""v353: BOT product - capital-weighted SUB-ACCOUNT blend of the audited pipelines, weights chosen walk-forward (registry v353).

User suggestion: combine many promising solutions with weights found by search instead of one fixed pipeline. A BOT can run several sub-accounts.
MEMBERS (fixed before running; each simulated alone on engine_user with the kpack inputs, its 4h equity and 1m-marked minimum path captured):
  R2 (v321, v306 seed R2), G2 (v301), Q2 (v306 seed: 2.0 rung, fit R1, budget 0.18), B1 (v306 seed: 5-sigma close stop), T1 (v306 seed: target
  0.28), M3 (the MANUAL pipeline: CB books x0.75 + bracket dip limits 3.0 / 4.0 sigma, native 8-sigma stop).
BLEND: integer weights 0..4 per member (at least one > 0), capital split reset to w / sum(w) at every month start (internal transfers, no cost);
combined 4h equity = sum of the sub-accounts; combined 1m-marked minimum = sum of their minima (conservative). NO leverage (weights sum to 1).
All 5^6 - 1 = 15624 blends are evaluated (no sampling noise).
Per dev year y: monthly = (end / start)^(1/12) - 1 of the combined path, DD = max drawdown of the 1m-marked minimum vs the running 4h peak inside
the year, all-trade win = trade-count-weighted member win rates (weights = capital share x member trades). FITNESS = v306 BOT fitness
(g = R/8, W/5, 15/DD, win/0.65, capped 1.2; 0.5 min + 0.5 mean; losing year -> -1 + R/100) on the years given.
CHOICE = flat optimum: among the 30 best blends on F(years [:k]), the highest mean F over the blend and all its one-step weight neighbours (+-1).
PROTOCOL: folds k = 1, 2, 3: choice on dev years [:k], scored on dev year k against R2 alone; TRANSFER if it beats R2 in >= 2 of 3 folds. Final
choice on dev4; the most recent year computed once for it. Contaminated by design (members chosen after earlier looks at the most recent year).

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v353/v353_bot_subaccount_blend.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
NAMES = ("R2", "G2", "Q2", "B1", "T1", "M3")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def capture(eu, fn):
    po, sim0 = {}, eu.simulate

    def sim(*a, **kw):
        kw["path_out"] = po
        return sim0(*a, **kw)
    eu.simulate = sim
    try:
        res = fn()
    finally:
        eu.simulate = sim0
    return res, po


def combine(month, eqs, mins, w):
    """Month-start rebalanced sub-accounts (units fixed inside a month), computed one month segment at a time."""
    n = len(month)
    eq, emin = np.ones(n), np.ones(n)
    starts = [0] + [i for i in range(1, n) if month[i] != month[i - 1]] + [n]
    V = 1.0
    for s0, s1 in zip(starts[:-1], starts[1:]):
        ref = eqs[:, s0 - 1] if s0 > 0 else eqs[:, 0]
        units = w * V / ref
        eq[s0:s1] = units @ eqs[:, s0:s1]
        emin[s0:s1] = units @ mins[:, s0:s1]
        V = eq[s1 - 1]
    return eq, emin


def yearly(t, eq, emin, anchors, ny):
    out = []
    for y in range(ny):
        a0 = anchors[y]
        m = np.asarray((t >= a0) & (t < a0 + pd.Timedelta(days=365)))
        i0 = int(np.argmax(m))
        base = eq[i0 - 1] if i0 > 0 else 1.0
        e, lo = eq[m] / base, emin[m] / base
        peak = np.maximum.accumulate(np.r_[1.0, e])[:-1]
        dd = float(np.max(1 - np.minimum(lo, e) / np.maximum(peak, e)))
        net = float(e[-1] - 1)
        out.append(dict(net=100 * net, monthly=100 * ((1 + net) ** (1 / 12) - 1), dd=100 * dd))
    return out


def main():
    v306 = _load("v306_bl", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu6 = v306.W["eu"]
    paths, stats = {}, {}
    for nm in ("R2", "G2", "Q2", "B1", "T1"):
        g = v306.encode(v306.SEEDS[nm])
        res, po = capture(eu6, lambda: v306.run_genome(g, True))
        paths[nm], stats[nm] = po, res
        print(nm, v306.metrics(res, [0, 1, 2, 3]), flush=True)
    assert abs(v306.metrics(stats["R2"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    v347 = _load("v347_bl", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    eu7 = v347.W["v310"].W["eu"]
    res, po = capture(eu7, lambda: v347.run_genome(v347.encode(v347.SEEDS["CB"]), True))
    paths["M3"], stats["M3"] = po, res
    assert abs(v347.W_metrics(res, [0, 1, 2, 3])["R"] - 6.233) < 0.003
    t = pd.DatetimeIndex(paths["R2"]["t"]) + pd.Timedelta(hours=4)
    for nm in NAMES:
        assert len(paths[nm]["t"]) == len(t)
    eqs = np.vstack([np.asarray(paths[nm]["eq"], float) for nm in NAMES])
    mins = np.vstack([np.minimum(np.asarray(paths[nm]["eq_min"], float), eqs[q]) for q, nm in enumerate(NAMES)])
    month = np.asarray(t.to_period("M").astype(str))
    anchors = v306.W["anchors"]
    ntr = np.array([[stats[nm]["years"][y]["n_book"] + stats[nm]["years"][y]["n_rung"] for y in range(5)] for nm in NAMES], float)
    nwin = np.array([[stats[nm]["years"][y]["w_book"] + stats[nm]["years"][y]["w_rung"] for y in range(5)] for nm in NAMES], float)

    def evaluate(w, ny=4):
        w = np.asarray(w, float) / sum(w)
        eq, emin = combine(month, eqs, mins, w)
        ys = yearly(t, eq, emin, anchors, ny)
        for y, d in enumerate(ys):
            d["n"] = float(w @ ntr[:, y])
            d["wins"] = float(w @ nwin[:, y])
        return ys

    def metrics(ys_res, ys):
        yy = [ys_res[y] for y in ys]
        R = 100 * (np.prod([1 + d["net"] / 100 for d in yy]) ** (1 / (12 * len(yy))) - 1)
        win = sum(d["wins"] for d in yy) / max(sum(d["n"] for d in yy), 1e-9)
        return dict(R=round(R, 3), W=round(min(d["monthly"] for d in yy), 3), DD=round(max(d["dd"] for d in yy), 2), win=round(win, 4),
                    losing=sum(d["net"] < 0 for d in yy))

    def fitness(ys_res, ys):
        m = metrics(ys_res, ys)
        if m["losing"]:
            return -1 + m["R"] / 100
        g = np.minimum([m["R"] / 8, m["W"] / 5, 15 / max(m["DD"], 1e-6), m["win"] / 0.65], 1.2)
        return float(0.5 * g.min() + 0.5 * g.mean())

    grid = [w for w in itertools.product(range(5), repeat=len(NAMES)) if sum(w) > 0]
    cache = {}
    for n, w in enumerate(grid):
        cache[w] = evaluate(w)
        if n % 2000 == 0:
            print("evaluated", n, "/", len(grid), flush=True)
    r2 = (4, 0, 0, 0, 0, 0)
    out = {"version": "v353", "members": {nm: v306.metrics(stats[nm], [0, 1, 2, 3]) if nm != "M3" else v347.W_metrics(stats[nm], [0, 1, 2, 3])
                                          for nm in NAMES}, "blend_check_R2": metrics(cache[r2], [0, 1, 2, 3]), "folds": {}}
    print("R2 via blend path", out["blend_check_R2"], flush=True)

    def neighbours(w):
        out_ = []
        for q in range(len(w)):
            for d in (-1, 1):
                c = list(w)
                c[q] += d
                if 0 <= c[q] <= 4 and sum(c) > 0:
                    out_.append(tuple(c))
        return out_

    def choose(ys):
        ft = {w: fitness(cache[w], ys) for w in grid}
        top = sorted(grid, key=lambda w: -ft[w])[:30]
        flat = {w: float(np.mean([ft[w]] + [ft[c] for c in neighbours(w)])) for w in top}
        return max(flat, key=lambda w: flat[w]), ft

    wins = 0
    for k in (1, 2, 3):
        ys = list(range(k))
        ch, ft = choose(ys)
        f_ch, f0 = fitness(cache[ch], [k]), fitness(cache[r2], [k])
        out["folds"][k] = dict(choice=dict(zip(NAMES, ch)), train_F=round(ft[ch], 4), test=dict(metrics(cache[ch], [k]), F=round(f_ch, 4)),
                               r2_test=dict(metrics(cache[r2], [k]), F=round(f0, 4)))
        wins += int(f_ch > f0 and ch != r2)
        print("FOLD", k, out["folds"][k], flush=True)
    out["transfer"] = dict(gain_folds=wins, holds=bool(wins >= 2))
    print("TRANSFER", out["transfer"], flush=True)
    ch, ft = choose([0, 1, 2, 3])
    full = evaluate(ch, ny=5)
    out["final"] = dict(choice=dict(zip(NAMES, ch)), dev4=dict(metrics(full, [0, 1, 2, 3]), F=round(ft[ch], 4)), r2_F=round(ft[r2], 4),
                        last_year=metrics(full, [4]), five_years=metrics(full, [0, 1, 2, 3, 4]))
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v353_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
