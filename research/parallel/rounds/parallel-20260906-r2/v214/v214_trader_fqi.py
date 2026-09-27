"""v214: reinforcement-learned trader agent on top of the v205 pipeline - offline fitted Q iteration (registry v214).

Why (user goal 2026-09-28): the pipeline is the foundation; an agent should trade it like a real trader (limit entries,
SL/TP, adds, partial and full limit exits, stop management, few market orders) and learn when to do what, maximising the
monthly return and the win rate while keeping DD low - general and without leakage. Rule versions (v210-v213) trade off
trend capture against chop (S3 dev4 4.83 / DD 20.7; E1 4.22 / DD 19.3).

Environment: engine_user trade mode with trade["policy"] (unit-tested; a rule policy reproduces v212 S3 exactly). Actions
(rl/trader_rl.py): flat with a signal -> wait | open (limit 0.25 sigma_4h) | open_deep (limit 0.75 sigma_4h); in a position
-> hold | tighten (stop to 1.5 sigma_d from the open) | reduce 50% (limit) | close 100% (limit) | add (limit, once, when the
signal is on the position's side and larger than the position). Minute-5 rule, SL market / TP limit, break-even at +2 sigma_d,
v205 books / sizing / governor / aligned dip sleeve / Bybit fees / adverse funding are unchanged.

Data (fixed before running): 20 behaviour runs over the whole walk-forward period; each decision follows the v212 S3 rule
policy, replaced by a uniformly random valid action with probability eps (20 values evenly spaced in 0.10..0.60, seeds 0-19).
Transitions: (state at a decision, action, discounted coin PnL until the coin's next decision, next state), gamma = 0.98.
Walk-forward: the Q model for anchor year Y (2022, 2023, 2024, 2025) is fitted ONLY on transitions whose reward window ends
before Y - 7 days; the first year (anchor 2021) has no earlier data and is traded by the S3 rule policy in every variant.
Q models (rl/trader_rl.QModel): one HistGradientBoostingRegressor per action (depth 5, lr 0.05, 200 iter, min leaf 100,
l2 1.0, at most 250k rows per action), rewards x100 (percent of equity). (A pilot with one shared model on [state, onehot]
could not separate the actions; changed before any registered run.)
  Q1_fqi          fitted Q iteration (10 iterations), act = argmax_a Q over valid actions.
  Q2_mc_margin    Monte Carlo returns of the behaviour policy until the position closes (one-step policy improvement); follow
                  the S3 rule action unless another action's value beats it by > 0.05 (percent of equity).
  Q3_mc_averse    Q2 with losses weighted x1.5 in the returns (a confident wrong trade hurts more).
References: ref_v205, rule_S3 (the policy hook with the S3 rules = v212 S3), v213_E1. SELECTION = robust criterion among
Q1..Q3; the most recent year is scored once for the selected row. Trade statistics as v213 (after fees).

  python research/parallel/rounds/parallel-20260906-r2/v214/v214_trader_fqi.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "rl"))
import trader_rl as rl  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v213 = _load("v213", HERE.parent / "v213/v213_trade_exits.py")
eu, v204 = v213.eu, v213.v204
KW, S3 = v213.KW, v213.S3
E1 = v213.VARIANTS["E1_exit_on_loss"]
GAMMA, EPS, EMBARGO = 0.98, tuple(np.round(np.linspace(0.10, 0.60, 20), 3)), pd.Timedelta(days=7)
MARGIN, LOSS_MULT = 0.05, 1.5
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]


def rule_s3(i, a, st):
    if st["pos"] == 0:
        return "open"
    acts, side = set(), st["pos"]
    if st["sgn"] == -side:
        acts.add("tighten")
    if "add" in st["valid"] and st["upnl"] > 0 and abs(st["tg"]) >= 1.5 * st["w"]:
        acts.add("add")
    elif "reduce" in st["valid"] and st["nred"] < 1 and (st["sgn"] != side or abs(st["tg"]) <= 0.5 * st["w"]):
        acts.add("reduce")
    return acts or "hold"


def year_of(t):
    k = -1
    for j, a0 in enumerate(ANCHORS):
        if t >= a0:
            k = j
    return k


def main():
    t0 = time.time()
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    idx = books.index
    feats, fnames = rl.market_features(opens, idx, cols, dict(mA=A, mB=B, mAq=Aq, mBq=Bq))
    out = {"version": "v214", "gamma": GAMMA, "eps": EPS, "features": fnames, "rows": {}, "trades": {}, "data": {}}

    # ---------------- behaviour data
    sets = []
    for seed, eps in enumerate(EPS):
        rng = np.random.default_rng(seed)

        def behaviour(i, a, st, rng=rng, eps=eps):
            if rng.random() < eps:
                return st["valid"][int(rng.integers(len(st["valid"])))]
            return rule_s3(i, a, st)
        rec, att = rl.Recorder(feats, behaviour), []
        eu.simulate(books, opens, prep, trade=dict(S3, policy=rec), win_start=5, attrib=att, **KW)
        ds = rl.build_dataset(rec.rows, att, idx, GAMMA)
        sets.append(ds)
        print(f"behaviour seed {seed} eps {eps}: {len(ds['A'])} decisions ({time.time() - t0:.0f}s)", flush=True)
    data = {k: (np.concatenate([d[k] for d in sets]) if k not in ("VN", "TEND") else None) for k in sets[0]}
    data["VN"] = [v for d in sets for v in d["VN"]]
    data["TEND"] = pd.DatetimeIndex(np.concatenate([d["TEND"].asi8 for d in sets]), tz="UTC")
    out["data"]["decisions"] = int(len(data["A"]))

    # ---------------- walk-forward Q models (anchor years 2..5)
    def subset(Y):
        keep = np.asarray(data["TEND"] < Y - EMBARGO)
        return {k: (v[keep] if isinstance(v, np.ndarray) else ([v[j] for j in np.flatnonzero(keep)] if k == "VN" else v[keep]))
                for k, v in data.items()}
    models = {"Q1_fqi": {}, "Q2_mc_margin": {}, "Q3_mc_averse": {}}
    for j in range(1, len(ANCHORS)):
        ds = subset(ANCHORS[j])
        out["data"][str(ANCHORS[j].date())] = int(len(ds["A"]))
        models["Q1_fqi"][j] = rl.QModel(mode="fqi", seed=j).fit(ds)
        models["Q2_mc_margin"][j] = rl.QModel(mode="mc", seed=j).fit(ds)
        models["Q3_mc_averse"][j] = rl.QModel(mode="mc", seed=j, loss_mult=LOSS_MULT).fit(ds)
        print(f"Q models for {ANCHORS[j].date()}: {len(ds['A'])} transitions ({time.time() - t0:.0f}s)", flush=True)

    def agent(name):
        def pol(i, a, st):
            y = year_of(idx[i] + pd.Timedelta(hours=4))
            if y <= 0:
                return rule_s3(i, a, st)
            x = rl.state_vector(feats, i, a, st)[None, :]
            q = models[name][y].q_all(x, [st["valid"]])[0]
            if not q:
                return rule_s3(i, a, st)
            best = max(q, key=q.get)
            if name in ("Q2_mc_margin", "Q3_mc_averse"):
                ref = rl.encode(rule_s3(i, a, st))
                ref = ref if ref in q else ("hold" if st["pos"] else "open")
                if q[best] - q.get(ref, -1e9) <= MARGIN:
                    return rule_s3(i, a, st)
            return best
        return pol

    # ---------------- evaluation
    runs = [("ref_v205", {}), ("rule_S3", dict(trade=dict(S3, policy=rule_s3), win_start=5)), ("v213_E1", dict(trade=E1, win_start=5))]
    runs += [(k, dict(trade=dict(S3, policy=agent(k)), win_start=5)) for k in models]
    for key, extra in runs:
        ev = []
        r = eu.simulate(books, opens, prep, events=ev, **KW, **extra)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key] = r
        ts = v213.trade_stats(ev) if "trade" in extra else None
        if ts:
            out["trades"][key] = ts
        st = r["stats"]
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]],
              {k: st[k] for k in ("fills", "stops", "tps", "adds", "reduces", "limit_exits", "tightened") if k in st},
              "dev trades", ts["dev"] if ts else None, f"({time.time() - t0:.0f}s)", flush=True)
        if key == "rule_S3":
            assert abs(r["monthly_dev4"] - 4.826) < 0.002, "the policy hook must reproduce v212 S3"
    sel = v204.robust_select({k: out["rows"][k] for k in models})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v214_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
