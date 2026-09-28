"""v215: one-step policy improvement over a trade-mode rule with sparse exploration and cross-fitted advantages (registry v215).

Why: v214's offline RL agents improved the chop year (2022) but cut trends: dense exploration (eps up to 0.6) made the
continuation after a decision mostly random, so holding a trend was under-valued, and an argmax over noisy Q values
deviated from the rule too often (median hold 11-22h).

Method (fixed before running): the continuation after every decision must be the RULE. Behaviour runs follow the base rule
and replace it by a uniformly random valid action with probability eps = 0.03 (40 runs per base rule, seeds 100-139). For a
decision the value of each action is the Monte Carlo return (coin PnL, fees and funding included, gamma 0.98) until that
position is closed, i.e. Q_rule(s, a) of "take a, then follow the rule" -> acting greedily on it is a one-step improvement of
the rule. Per-action HistGradientBoostingRegressor (rl/trader_rl.QModel mode "mc"), two models per year fitted on the even /
odd seeds (cross-fitting). At a decision the agent deviates from the rule's action r to a* = argmax_a mean advantage only if
BOTH models give Q(a*) - Q(r) > margin (percent of equity). Walk-forward: models for anchor year Y use transitions ending before
Y - 7 days; the first year (2021) follows the base rule. Environment = engine_user trade mode with trade["policy"] (minute-5 rule,
limits, SL market / TP limit, break-even, v205 books / governor / aligned sleeve / Bybit fees / adverse funding).
  P1_s3        base rule = v212 S3 (hold through signal loss, one add, one 50% reduce, tighten), margin 0.10.
  P2_e1        base rule = v213 E1 (S3 + full limit exit on signal loss), margin 0.10.
  P3_e1_strict base rule = E1, margin 0.25.
References: ref_v205, rule_S3 (= v212 S3, 4.826), rule_E1 (= v213 E1, 4.216). SELECTION = robust criterion among P1..P3;
the most recent year is scored once for the selected row. Per-year DD and trade statistics are reported.

  python research/parallel/rounds/parallel-20260906-r2/v215/v215_policy_improvement.py
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


v214 = _load("v214", HERE.parent / "v214/v214_trader_fqi.py")
v213, eu, v204 = v214.v213, v214.eu, v214.v204
KW, S3 = v214.KW, v214.S3
rule_s3, year_of, ANCHORS = v214.rule_s3, v214.year_of, v214.ANCHORS
GAMMA, EPS, N_RUNS, SEED0, EMBARGO = 0.98, 0.03, 40, 100, pd.Timedelta(days=7)


def rule_e1(i, a, st):
    if st["pos"] == 0:
        return "open"
    acts, side = set(), st["pos"]
    if st["sgn"] == -side:
        acts.add("tighten")
    if "add" in st["valid"] and st["upnl"] > 0 and abs(st["tg"]) >= 1.5 * st["w"]:
        acts.add("add")
    elif "close" in st["valid"] and st["sgn"] != side:
        acts.add("close")
    elif "reduce" in st["valid"] and st["nred"] < 1 and abs(st["tg"]) <= 0.5 * st["w"]:
        acts.add("reduce")
    return acts or "hold"


VARIANTS = {"P1_s3": (rule_s3, 0.10), "P2_e1": (rule_e1, 0.10), "P3_e1_strict": (rule_e1, 0.25)}


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
    out = {"version": "v215", "eps": EPS, "runs": N_RUNS, "variants": {k: v[1] for k, v in VARIANTS.items()}, "rows": {}, "trades": {}, "data": {}}

    def collect(rule, name):
        parts = {0: [], 1: []}
        for s in range(SEED0, SEED0 + N_RUNS):
            rng = np.random.default_rng(s)

            def beh(i, a, st, rng=rng):
                if rng.random() < EPS:
                    return st["valid"][int(rng.integers(len(st["valid"])))]
                return rule(i, a, st)
            rec, att = rl.Recorder(feats, beh), []
            eu.simulate(books, opens, prep, trade=dict(S3, policy=rec), win_start=5, attrib=att, **KW)
            parts[s % 2].append(rl.build_dataset(rec.rows, att, idx, GAMMA))
        print(f"{name}: {N_RUNS} behaviour runs ({time.time() - t0:.0f}s)", flush=True)
        merged = {}
        for h, sets in parts.items():
            d = {k: np.concatenate([x[k] for x in sets]) for k in sets[0] if k not in ("VN", "TEND")}
            d["VN"] = [v for x in sets for v in x["VN"]]
            d["TEND"] = pd.DatetimeIndex(np.concatenate([x["TEND"].asi8 for x in sets]), tz="UTC")
            merged[h] = d
        return merged

    def subset(d, Y):
        keep = np.asarray(d["TEND"] < Y - EMBARGO)
        return {k: (v[keep] if k != "VN" else [v[j] for j in np.flatnonzero(keep)]) for k, v in d.items()}

    data = {"s3": collect(rule_s3, "S3 data"), "e1": collect(rule_e1, "E1 data")}
    models = {}
    for base in ("s3", "e1"):
        models[base] = {}
        for j in range(1, len(ANCHORS)):
            pair = []
            for h in (0, 1):
                ds = subset(data[base][h], ANCHORS[j])
                pair.append(rl.QModel(mode="mc", seed=10 * j + h).fit(ds))
            models[base][j] = pair
            out["data"][f"{base}_{ANCHORS[j].date()}"] = int(sum(len(subset(data[base][h], ANCHORS[j])["A"]) for h in (0, 1)))
        print(f"models {base} ({time.time() - t0:.0f}s)", flush=True)

    def agent(rule, base, margin):
        stats = {"deviations": 0, "decisions": 0}

        def pol(i, a, st):
            y = year_of(idx[i] + pd.Timedelta(hours=4))
            r_act = rule(i, a, st)
            if y <= 0:
                return r_act
            stats["decisions"] += 1
            x = rl.state_vector(feats, i, a, st)[None, :]
            qa, qb = (m.q_all(x, [st["valid"]])[0] for m in models[base][y])
            ref = rl.encode(r_act)
            if ref not in qa or ref not in qb:
                return r_act
            cands = [c for c in st["valid"] if c != ref and c in qa and c in qb]
            if not cands:
                return r_act
            best = max(cands, key=lambda c: (qa[c] - qa[ref]) + (qb[c] - qb[ref]))
            if min(qa[best] - qa[ref], qb[best] - qb[ref]) > margin:
                stats["deviations"] += 1
                return best
            return r_act
        pol.stats = stats
        return pol

    runs = [("ref_v205", {}, None), ("rule_S3", dict(trade=dict(S3, policy=rule_s3), win_start=5), None),
            ("rule_E1", dict(trade=dict(S3, policy=rule_e1), win_start=5), None)]
    for k, (rule, margin) in VARIANTS.items():
        pol = agent(rule, "s3" if rule is rule_s3 else "e1", margin)
        runs.append((k, dict(trade=dict(S3, policy=pol), win_start=5), pol))
    for key, extra, pol in runs:
        ev = []
        r = eu.simulate(books, opens, prep, events=ev, **KW, **extra)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if pol is not None:
            r["agent"] = dict(pol.stats)
        out["rows"][key] = r
        ts = v213.trade_stats(ev) if "trade" in extra else None
        if ts:
            out["trades"][key] = ts
        st = r["stats"]
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              {k: st[k] for k in ("fills", "stops", "tps", "adds", "reduces", "limit_exits", "tightened") if k in st},
              r.get("agent"), "dev trades", ts["dev"] if ts else None, f"({time.time() - t0:.0f}s)", flush=True)
        if key == "rule_S3":
            assert abs(r["monthly_dev4"] - 4.826) < 0.002, "policy hook must reproduce v212 S3"
        if key == "rule_E1":
            assert abs(r["monthly_dev4"] - 4.216) < 0.002, "policy hook must reproduce v213 E1"
    sel = v204.robust_select({k: out["rows"][k] for k in VARIANTS})
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
    (HERE / "v215_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
