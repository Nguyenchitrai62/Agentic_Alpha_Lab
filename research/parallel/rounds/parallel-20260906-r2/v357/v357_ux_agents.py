"""v357: dip agents with a RICHER bar-open state (previous-bar move, BTC previous-bar move, 24h move, previous-bar flush) on M3 (registry v357).

The R2 dip agents (used by M3) see seven state features. Dips cluster (one flush follows another) and market-wide moves matter (v302 breadth at the
fill lowered the BOT DD), so v357 refits the same agents (pooled 35-coin experience, BOT labels, all seven depths, cross-fitted halves, HGB, fills
exited before anchor - 7 days) with four extra features computed from bars closed before the holding bar (v357_ux_tables.py, fit "UX"), and applies
the SAME decision rules as M3. Rows (fixed before running; everything else = M3, kpack inputs):
  M3   = R2 agents (v306 fit "U"; reference, dev4 6.233)
  MX   = UX agents for both size and take-profit
  MXs  = UX size agent, R2 take-profit agent
Fitness / protocol as v347-v356 (MANUAL fitness, all-trade win): dev folds k = 2, 3 on years [:k]; TRANSFER if MX / MXs is chosen and beats M3 on the
unseen dev year in both folds; final on dev4; most recent year once. Contaminated by design; prospective log = clean evidence.

  KPACK=artifacts/kaggle/kpack/pack347 python research/parallel/rounds/parallel-20260906-r2/v357/v357_ux_agents.py
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tables(tab, fit, idx, cols):
    """v306._tables with the M3 rules (up 2.0 x1.5, down 0.0 x0.5, tp_margin 0.001) on one fit of a prediction table."""
    t = tab[tab.fit == fit]
    ii = idx.get_indexer(t["T"] - pd.Timedelta(hours=4))
    aa = np.array([cols.index(s) for s in t["sym"]])
    kk = np.array([U.index(k) for k in t["k"]])
    ok = ii >= 0
    T = {}
    for c in ("pa", "pb", "mu", "qa0", "qa1", "qa2", "qb0", "qb1", "qb2"):
        T[c] = np.full((len(idx), len(cols), len(U)), np.nan)
        T[c][ii[ok], aa[ok], kk[ok]] = t[c].to_numpy(float)[ok]
    pa, pb, mu = T["pa"], T["pb"], T["mu"]
    size = np.ones_like(pa)
    up = (pa > 2.0 * mu) & (pb > 2.0 * mu)
    dn = (pa < 0.0) & (pb < 0.0)
    size[up] = 1.5
    size[dn & ~up] = 0.5
    size[~np.isfinite(pa)] = 1.0
    qa = np.stack([T[f"qa{c}"] for c in range(3)], -1)
    qb = np.stack([T[f"qb{c}"] for c in range(3)], -1)
    ba, bb = np.nanargmax(np.nan_to_num(qa, nan=-9), -1), np.nanargmax(np.nan_to_num(qb, nan=-9), -1)
    ga = np.take_along_axis(qa, ba[..., None], -1)[..., 0] - qa[..., 1]
    gb = np.take_along_axis(qb, bb[..., None], -1)[..., 0] - qb[..., 1]
    okk = (ba == bb) & (ba != 1) & (ga > 0.001) & (gb > 0.001) & np.isfinite(ga) & np.isfinite(gb)
    tp = np.where(okk, np.array((0.5, 1.0, 1.5))[ba], 1.0)
    return size, tp


def main():
    v347 = _load("v347_ux", RD / "v347/v347_member_weight_evolution.py")
    v347.init_worker()
    W0 = v347.W["v310"].W
    idx, cols = W0["idx"], list(W0["cols"])
    tab = pd.read_parquet("artifacts/research/engine_real/v357_ux_tables.parquet")
    tab["T"] = pd.to_datetime(tab["T"], utc=True)
    ux_size, ux_tp = tables(tab, "UX", idx, cols)
    sets = {"M3": (v347.W["size"].copy(), v347.W["tp"].copy()), "MX": (ux_size, ux_tp), "MXs": (ux_size, v347.W["tp"].copy())}
    res = {}
    for k, (sz, tp) in sets.items():
        v347.W["size"], v347.W["tp"] = sz, tp
        res[k] = v347.run_genome(v347.encode(v347.SEEDS["CB"]))
    assert abs(v347.W_metrics(res["M3"], [0, 1, 2, 3])["R"] - 6.233) < 0.003
    out = {"version": "v357", "rows": {k: dict(dev4=v347.W_metrics(r, [0, 1, 2, 3]), F=round(v347.fitness(r, [0, 1, 2, 3]), 4),
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
    v347.W["size"], v347.W["tp"] = sets[ch]
    full = v347.run_genome(v347.encode(v347.SEEDS["CB"]), True)
    out["final"] = dict(choice=ch, dev4=v347.W_metrics(res[ch], [0, 1, 2, 3]), last_year=v347.W_metrics(full, [4]),
                        five_years=v347.W_metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("FINAL", json.dumps(out["final"], default=str), flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v357_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
