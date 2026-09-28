"""v232: disciplined RL trader - "cut losers, let winners run" action constraints + trader-indicator state (registry v232).

Why: every learned trade manager so far (v214 fitted Q, v215 one-step improvement, v217 ES) was worse than its rule because mean value
estimates of fat-tailed trend payoffs favour early exits: the agents cut WINNING trends (median hold 11-22h) while improving chop.
A real trader's discipline is asymmetric: losers may be cut early, winners are held (and may be added to). Hypothesis: constraining
the learned deviations to that asymmetry keeps the trend tail and lets the learner help only where it is reliable. The agent also
sees the trader indicators that v231 found informative for the foundation (TradingView set, v231/tv_indicators.py).

Fixed before running.
Foundation = v231 V1 books (member A with the TradingView features; 0.5 (A_tv + B)/2 + 0.5 (Aq + Bq)/2), engine_user trade mode
with the v216 G2 grid rule, v218 D2 settings (sleeve budget 0.15, rung x1.75, minute-5 rule, limit entries, SL market / TP limit,
break-even, governor, aligned sleeve, Bybit fees, adverse funding).
Data: 40 behaviour runs (seeds 100-139) of G2 replacing its action by a uniformly random valid action with probability 0.03.
Value of a decision = Monte Carlo return (coin PnL incl. fees/funding, gamma 0.98) of "take the action, then follow G2" until the
position closes (rl/trader_rl.py mode "mc"); per-action HistGradientBoosting, two models per year fitted on even / odd seeds
(cross-fitting). State = rl.market_features (returns / range / vol regime / BTC / the four members) + the 17 TradingView indicators
of the coin at the decision + position state. Walk-forward: models for year Y use transitions ending before Y - 7 days; 2021 = G2.
A deviation from G2's action r to a* happens only if BOTH models give Q(a*) - Q(r) > margin (percent of equity) AND:
  a* in {close, reduce, tighten} only while the position's unrealised PnL < 0 (cut losers);
  a* = add only while the unrealised PnL > 0 (pyramid winners; R2 / R3 only); flat decisions always follow G2.
  R1_cut            losers only, margin 0.10
  R2_cut_pyramid    losers + winner adds, margin 0.10
  R3_strict         as R2, margin 0.25
References: rule_G2_on_V1 (must reproduce v231 V1 dev4 5.462). SELECTION = robust criterion among R1..R3; the most recent year
is scored once for the selected row. Reported: deviations / decisions, trade statistics (win rate, hold time).

  python research/parallel/rounds/parallel-20260906-r2/v232/v232_disciplined_rl.py
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


v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
v231 = _load("v231", HERE.parent / "v231/v231_quality_features.py")
v214 = _load("v214", HERE.parent / "v214/v214_trader_fqi.py")
eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
year_of, ANCHORS = v214.year_of, v214.ANCHORS
GAMMA, EPS, N_RUNS, SEED0, EMBARGO = 0.98, 0.03, 40, 100, pd.Timedelta(days=7)
VARIANTS = {"R1_cut": (False, 0.10), "R2_cut_pyramid": (True, 0.10), "R3_strict": (True, 0.25)}
CUT = ("close", "reduce", "tighten")


def tv_frames(idx, cols):
    v144 = _load("v144_rl", HERE.parent / "v144/v144_deploy_v3.py")
    ext = v144.v115.v114.v113
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    xf = v231.extra_features(("tv",), ext.v92.load_asset, None)
    return {k: xf.pivot_table(index="t", columns="sym", values=k).reindex(idx)[cols] for k in v231.tvm.TV}


def main():
    t0 = time.time()
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    B = mem.xs("B", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(idx).fillna(0.0)[cols] for k in ("A", "B"))
    Atv = pd.read_parquet(eu.er.CACHE / "member_A_tv_annual.parquet").reindex(idx).fillna(0.0)[cols]
    books = 0.5 * (Atv + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    members = dict(mA=Atv, mB=B, mAq=Aq, mBq=Bq, **tv_frames(idx, cols))
    feats, fnames = rl.market_features(opens, idx, cols, members)
    rl.POS_INDEX = feats.shape[2]  # the position block follows the (longer) market block in the state vector
    rule = v216.grid_policy(v221.B_ABS, v221.B_REL)
    trade = dict(v216.GRID)
    out = {"version": "v232", "eps": EPS, "runs": N_RUNS, "state_features": fnames, "variants": {k: list(v) for k, v in VARIANTS.items()},
           "rows": {}, "trades": {}, "data": {}}
    print("features", len(fnames), f"({time.time() - t0:.0f}s)", flush=True)

    parts = {0: [], 1: []}
    for s in range(SEED0, SEED0 + N_RUNS):
        rng = np.random.default_rng(s)

        def beh(i, a, st, rng=rng):
            if rng.random() < EPS:
                return st["valid"][int(rng.integers(len(st["valid"])))]
            return rule(i, a, st)
        rec, att = rl.Recorder(feats, beh), []
        eu.simulate(books, opens, prep, trade=dict(trade, policy=rec), win_start=5, attrib=att, **v221.KW)
        parts[s % 2].append(rl.build_dataset(rec.rows, att, idx, GAMMA))
    print(f"behaviour: {N_RUNS} runs ({time.time() - t0:.0f}s)", flush=True)
    data = {}
    for h, sets in parts.items():
        d = {k: np.concatenate([x[k] for x in sets]) for k in sets[0] if k not in ("VN", "TEND")}
        d["VN"] = [v for x in sets for v in x["VN"]]
        d["TEND"] = pd.DatetimeIndex(np.concatenate([x["TEND"].asi8 for x in sets]), tz="UTC")
        data[h] = d

    def subset(d, Y):
        keep = np.asarray(d["TEND"] < Y - EMBARGO)
        return {k: (v[keep] if k != "VN" else [v[j] for j in np.flatnonzero(keep)]) for k, v in d.items()}

    models = {}
    for j in range(1, len(ANCHORS)):
        models[j] = [rl.QModel(mode="mc", seed=10 * j + h).fit(subset(data[h], ANCHORS[j])) for h in (0, 1)]
        out["data"][str(ANCHORS[j].date())] = int(sum(len(subset(data[h], ANCHORS[j])["A"]) for h in (0, 1)))
    print(f"models ({time.time() - t0:.0f}s)", out["data"], flush=True)

    def agent(pyramid, margin):
        stats = {"decisions": 0, "deviations": 0, "by_action": {}}

        def pol(i, a, st):
            r_act = rule(i, a, st)
            y = year_of(idx[i] + pd.Timedelta(hours=4))
            if y <= 0 or st["pos"] == 0:
                return r_act
            stats["decisions"] += 1
            allowed = set()
            if st["upnl"] < 0:
                allowed |= set(CUT)
            if pyramid and st["upnl"] > 0:
                allowed.add("add")
            cands = [c for c in st["valid"] if c in allowed]
            ref = rl.encode(r_act)
            if not cands:
                return r_act
            x = rl.state_vector(feats, i, a, st)[None, :]
            qa, qb = (m.q_all(x, [st["valid"]])[0] for m in models[y])
            if ref not in qa or ref not in qb:
                return r_act
            cands = [c for c in cands if c != ref and c in qa and c in qb]
            if not cands:
                return r_act
            best = max(cands, key=lambda c: (qa[c] - qa[ref]) + (qb[c] - qb[ref]))
            if min(qa[best] - qa[ref], qb[best] - qb[ref]) > margin:
                stats["deviations"] += 1
                stats["by_action"][best] = stats["by_action"].get(best, 0) + 1
                return best
            return r_act
        pol.stats = stats
        return pol

    runs = [("rule_G2_on_V1", rule)] + [(k, agent(*v)) for k, v in VARIANTS.items()]
    for key, pol in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=dict(trade, policy=pol), win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if hasattr(pol, "stats"):
            r["agent"] = json.loads(json.dumps(pol.stats))
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              r.get("agent"), "dev trades", out["trades"][key]["dev"], f"({time.time() - t0:.0f}s)", flush=True)
        if key == "rule_G2_on_V1":
            assert abs(r["monthly_dev4"] - 5.462) < 0.002, "the rule on the V1 books must reproduce v231 V1"
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
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v232_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
