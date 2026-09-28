"""v217: reinforcement learning by direct policy search (evolution strategies) for the grid trader, walk-forward (registry v217).

Why: value-based RL (v214, v215) learned biased action values on fat-tailed trend payoffs and under-performed the rules. Direct
policy search optimises the real objective (monthly return and drawdown of the simulated account) over the parameters of a
trader policy, like evolution-strategy RL. The policy is the v216 grid trader (best executable pipeline: dev4 4.84, worst year
1.65%/month, DD 18.0).

Policy parameters theta (bounds; default theta0 = v216 G2):
  theta_open [0.02, 0.12] (0.05)  minimum |target| to open;           k_off [0.05, 1.0] (0.25)  entry/adjust limit offset in sigma_4h;
  b_abs [0.01, 0.08] (0.03)        band floor (equity);                b_rel [0.10, 0.90] (0.40) band relative to |target|;
  cool [2, 18] bars (6)            minimum bars between adjustments;   be_k [1.0, 4.0] (2.0)     break-even trigger in sigma_d;
  book_mult [0.7, 1.4] (1.0)       position size multiplier.
Everything else = v216 (engine_user trade mode, minute-5 rule, limit entries/adjustments/exits, SL 4 sigma_d market, TP 8 sigma_d
limit, v205 books / governor / aligned dip sleeve / Bybit fees / adverse funding).
Walk-forward (fixed before running): for anchor year Y_j (j = 1..4: 2022, 2023, 2024, 2025) theta_j is searched ONLY on the
walk-forward years before Y_j (anchors 0..j-1, full simulated years; nothing of year Y_j or later enters the objective); the first
year (2021) uses theta0. Objective on the training years (monthly returns m_y, 1m drawdowns d_y in %):
  ES1_robust   J = mean(m_y) + min(m_y) - sum_y max(0, d_y - 18)
  ES2_shrunk   theta of ES1 shrunk halfway to theta0 (in normalised parameter space)
  ES3_worst    J = min(m_y) - sum_y max(0, d_y - 18)
Search: diagonal evolution strategy in the normalised box, population 12, 7 generations, step 0.2, weighted recombination of the
best 6, seed 217 + j; the best evaluated theta (theta0 included) is kept. 6 worker processes.
References: ref_v205, grid_G2 (theta0 everywhere = v216 G2). SELECTION = robust criterion among ES1..ES3; the most recent year is
scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v217/v217_policy_search.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
NAMES = ("theta_open", "k_off", "b_abs", "b_rel", "cool", "be_k", "book_mult")
LO = np.array([0.02, 0.05, 0.01, 0.10, 2.0, 1.0, 0.7])
HI = np.array([0.12, 1.00, 0.08, 0.90, 18.0, 4.0, 1.4])
THETA0 = np.array([0.05, 0.25, 0.03, 0.40, 6.0, 2.0, 1.0])
POP, GENS, STEP, MU, WORKERS, DD_CAP = 12, 7, 0.2, 6, 6, 18.0


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def to_theta(x):
    t = LO + np.clip(x, 0, 1) * (HI - LO)
    t[4] = round(t[4])
    return t


def to_x(theta):
    return (theta - LO) / (HI - LO)


_G = {}


def _init():
    v216 = _load("v216", HERE.parent / "v216/v216_trade_grid.py")
    eu = v216.eu
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    _G.update(v216=v216, eu=eu, opens=opens, books=0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2, prep=eu.prepare(books154, opens),
              anchors=[pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS])


def policy_for(schedule):
    """schedule: year index -> theta. Returns (trade dict, policy) for engine_user."""
    anchors, idx = _G["anchors"], _G["books"].index

    def year(i):
        t = idx[i] + pd.Timedelta(hours=4)
        k = 0
        for j, a0 in enumerate(anchors):
            if t >= a0:
                k = j
        return k

    cache = {}

    def th(i):
        y = year(i)
        if y not in cache:
            cache[y] = schedule.get(y, THETA0)
        return cache[y]

    def params_at(i):
        t = th(i)
        return {"theta": t[0], "k_off": t[1], "be_k": t[5], "book_mult": t[6]}

    def pol(i, a, st):
        t = th(i)
        if st["pos"] == 0:
            return "open"
        side, tg, w, valid = st["pos"], st["tg"], st["w"], st["valid"]
        if st["sgn"] == -side:
            return {"tighten": 1, "close": 1} if "close" in valid else "tighten"
        if st["sgn"] == 0:
            return "close" if "close" in valid else "hold"
        if st["since_adj"] < t[4]:
            return "hold"
        band = max(t[2], t[3] * abs(tg))
        diff = abs(tg) - w
        if diff > band and "add" in valid:
            return {"add": diff}
        if -diff > band and "reduce" in valid and w > 0:
            return {"reduce": min(1.0, -diff / w)}
        return "hold"
    trade = dict(_G["v216"].GRID, params_at=params_at, policy=pol)
    return trade


def run_schedule(schedule, events=None):
    if not _G:
        _init()
    trade = policy_for(schedule)
    kw = dict(_G["v216"].KW)
    return _G["eu"].simulate(_G["books"], _G["opens"], _G["prep"], trade=trade, win_start=5, events=events, **kw)


def objective(r, j, kind):
    ys = r["yearly"][:j]
    m = np.array([100 * ((1 + y["net_pct"] / 100) ** (1 / 12) - 1) for y in ys])
    pen = sum(max(0.0, y["dd_1m_pct"] - DD_CAP) for y in ys)
    return float((m.mean() + m.min() if kind == "robust" else m.min()) - pen)


def _eval(args):
    x, j, kind = args
    r = run_schedule({y: to_theta(x) for y in range(5)})  # the objective reads only years < j
    return objective(r, j, kind), [(y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:j]]


def search(pool, j, kind, log):
    rng = np.random.default_rng(217 + j)
    x0 = to_x(THETA0)
    best_x, best_j = x0.copy(), pool.submit(_eval, (x0, j, kind)).result()[0]
    mean, sig = x0.copy(), np.full(len(x0), STEP)
    w = np.log(MU + 0.5) - np.log(np.arange(1, MU + 1))
    w /= w.sum()
    for g in range(GENS):
        X = np.clip(mean + sig * rng.standard_normal((POP, len(x0))), 0, 1)
        res = list(pool.map(_eval, [(x, j, kind) for x in X]))
        J = np.array([r[0] for r in res])
        order = np.argsort(-J)
        if J[order[0]] > best_j:
            best_j, best_x = float(J[order[0]]), X[order[0]].copy()
        sel = X[order[:MU]]
        new_mean = (w[:, None] * sel).sum(axis=0)
        sig = np.clip(0.7 * sig + 0.3 * np.sqrt((w[:, None] * (sel - mean) ** 2).sum(axis=0)), 0.02, 0.3)
        mean = new_mean
        log.append(dict(j=j, kind=kind, gen=g, best=round(best_j, 3), gen_best=round(float(J[order[0]]), 3)))
    return best_x, best_j


def main():
    t0 = time.time()
    _init()
    v204 = _load("v204", HERE.parent / "v204/v204_sleeve_book_alignment.py")
    v213 = _G["v216"].v213
    out = {"version": "v217", "names": NAMES, "theta0": THETA0.tolist(), "lo": LO.tolist(), "hi": HI.tolist(), "log": [], "schedules": {}}
    sched = {"ES1_robust": {0: THETA0}, "ES2_shrunk": {0: THETA0}, "ES3_worst": {0: THETA0}}
    with ProcessPoolExecutor(WORKERS, initializer=_init) as pool:
        for j in range(1, 5):
            for kind, key in (("robust", "ES1_robust"), ("worst", "ES3_worst")):
                bx, bj = search(pool, j, kind, out["log"])
                sched[key][j] = to_theta(bx)
                if key == "ES1_robust":
                    sched["ES2_shrunk"][j] = to_theta(to_x(THETA0) + 0.5 * (bx - to_x(THETA0)))
                print(f"anchor {_G['anchors'][j].date()} {kind}: J {bj:.3f} theta {dict(zip(NAMES, np.round(to_theta(bx), 3)))} "
                      f"({time.time() - t0:.0f}s)", flush=True)
    out["schedules"] = {k: {str(y): dict(zip(NAMES, map(float, t))) for y, t in v.items()} for k, v in sched.items()}
    rows, trades = {}, {}
    ref = _G["eu"].simulate(_G["books"], _G["opens"], _G["prep"], **_G["v216"].KW)
    ref["worst_dev_month_pct"] = round(v204.worst_month(ref), 3)
    rows["ref_v205"] = ref
    for key, s in [("grid_G2", {y: THETA0 for y in range(5)})] + list(sched.items()):
        ev = []
        r = run_schedule(s, events=ev)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        rows[key], trades[key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", trades[key]["dev"], flush=True)
        if key == "grid_G2":
            assert abs(r["monthly_dev4"] - 4.836) < 0.002, "theta0 everywhere must reproduce v216 G2"
    cands = ("ES1_robust", "ES2_shrunk", "ES3_worst")
    sel = v204.robust_select({k: rows[k] for k in cands})
    s = rows[sel]
    out.update(rows=rows, trades=trades, selected=sel)
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": trades[sel]["_hidden"]}
    for k in trades:
        if k != sel:
            trades[k].pop("_hidden", None)
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v217_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
