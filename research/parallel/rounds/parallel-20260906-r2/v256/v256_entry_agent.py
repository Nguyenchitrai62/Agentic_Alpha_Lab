"""v256: a learned ENTRY-EXECUTION agent - where to rest each opening limit order (contextual bandit RL with exact counterfactuals).

Why (user goal: an RL trader acting like a real trader; win rate and DD matter): a trader decides for every entry whether to chase (limit
near the price, sure fill) or to wait for a better price (deeper limit, better entry, may miss the move). The pipeline always rests the
opening limit 0.25 sigma_4h better than the bar open. The O1 robustness report showed the pipeline is sensitive to this offset, and the
right choice plausibly depends on the state (strong trend / whale flow along the signal -> chase; chop / stretched move -> wait). As in
v248 (the largest dev gain of any learned layer), every alternative has an exact outcome from the engine, so the agent learns from full
information without value bootstrapping; unlike v248 it acts on the book (entries), not on the dip sleeve.
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings: G2 grid trader, rung x1.75, minute-5 rule, limits, SL market /
TP limit, break-even, governor, aligned sleeve, Bybit fees, adverse funding). New engine option: a flat-with-signal policy action
{"open": k} rests the opening limit k sigma_4h better than the bar open (adds / reduces / exits unchanged at 0.25).
Actions k in {0.10, 0.25, 0.50, 0.75}. Counterfactual data: four engine runs with a fixed k; opening orders matched on (issue bar, coin,
side) present in all four runs; outcome = the resulting position's net PnL in units of equity weight (fills, adds, reduces, exits,
maker / taker fees; 0 if the order expired or was cancelled unfilled), clipped to [-0.03, 0.03]; end time = position close (or order
end). State at the issue (decision row, known at the bar close): |book| / its 540-bar rolling median, sigma_4h regime (sigma / 540-bar
median), 6- and 42-bar returns in sigma units along the signal, TradingView SuperTrend direction and market-structure trend along the
signal, Williams VIX Fix z, order-level fl_big_imb6 along the signal, hour. Model: per action a HistGradientBoostingRegressor (depth 3,
lr 0.05, 200 iter, min leaf 50, l2 1.0) on outcome x 100, two models per anchor on even / odd issue bars (cross-fitting), fitted on
orders whose position ended before Y - 7 days; 2021 uses k = 0.25.
Policy: argmax of both halves' predictions; deviate from 0.25 only if both halves prefer the same k by more than the margin.
  E1_agent         margin 0
  E2_agent_strict  margin 0.02 (% of equity)
Reference: {"open": 0.25} through the hook (must reproduce v247 B18, dev4 5.777). SELECTION = robust criterion among E1, E2; the most
recent year is scored once for the selected row. Reported: action counts, trade statistics (win rate after fees).

  python research/parallel/rounds/parallel-20260906-r2/v256/v256_entry_agent.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = HERE.parent
ACTIONS = (0.10, 0.25, 0.50, 0.75)
BASE_K = 0.25
EMBARGO = pd.Timedelta(days=7)
BUDGET = 0.18
MAKER, TAKER = 0.0002, 0.00055


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def outcomes(events, idx):
    """(issue row, symbol, side) -> (net PnL in equity-weight units, end time) of each opening order."""
    pos_i = {t: k for k, t in enumerate(idx)}
    pend, open_, out = {}, {}, {}
    for e in events:
        k, s = e["kind"], e["symbol"]
        if k == "order_issue" and "scale" not in e:  # opening orders only (in-position add / reduce orders carry "scale")
            i = pos_i.get(e["t"].floor("4h") - pd.Timedelta(hours=4))
            pend[s] = (i, s, 1 if e["side"] == "buy" else -1)
        elif k in ("order_expire", "order_cancel") and s in pend and "scale" not in e:
            out[pend.pop(s)] = (0.0, e["t"])
        elif k == "book_fill" and s in pend:
            key = pend.pop(s)
            w = abs(e["weight"])
            open_[s] = dict(key=key, side=key[2], qty=w / e["price"], cost=w, proceeds=0.0, fees=w * MAKER)
        elif s in open_:
            o = open_[s]
            if k == "book_add":
                q = abs(e["weight"]) / e["price"]
                o["qty"] += q
                o["cost"] += q * e["price"]
                o["fees"] += q * e["price"] * MAKER
            elif k in ("book_reduce", "book_partial"):
                q = min(abs(e["weight"]) / e["price"], o["qty"])
                o["qty"] -= q
                o["proceeds"] += q * e["price"]
                o["fees"] += q * e["price"] * MAKER
            elif k in ("book_stop", "book_tp", "book_close"):
                o["proceeds"] += o["qty"] * e["price"]
                o["fees"] += o["qty"] * e["price"] * (TAKER if k == "book_stop" else MAKER)
                out[o["key"]] = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"], e["t"])
                open_.pop(s)
    return out


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v232 = _load("v232_e", RD / "v232/v232_disciplined_rl.py")
    v240 = _load("v240_e", RD / "v240/v240_order_level_flow.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    KW = dict(v221.KW, sleeve_risk_budget=BUDGET)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    base_pol = v216.grid_policy(v221.B_ABS, v221.B_REL)

    # ---- state at the decision row (bar close)
    tv = v232.tv_frames(idx, cols)
    o1 = opens.reindex(idx)[cols].shift(-1)
    lo1 = np.log(o1)
    sig = lo1.diff().rolling(360, min_periods=120).std()
    ab = books.abs()
    F = {"strength": ab / ab.rolling(540, min_periods=180).median().replace(0, np.nan),
         "vol": sig / sig.rolling(540, min_periods=180).median(),
         "r6": lo1.diff(6) / (sig * np.sqrt(6)), "r42": lo1.diff(42) / (sig * np.sqrt(42)),
         "st": tv["tv_st_dir"], "ms": tv["tv_ms_trend"], "wvf": tv["tv_wvf_z"],
         "flow": pd.DataFrame({s: v240.flo.flow_features(s, idx)["fl_big_imb6"].to_numpy() for s in cols}, index=idx)}
    Fa = {k: v.reindex(idx)[cols].to_numpy(float) for k, v in F.items()}
    hours = np.array([(t + pd.Timedelta(hours=4)).hour for t in idx], float)
    SIGNED = ("r6", "r42", "st", "ms", "flow")

    def state(i, a, side):
        return np.nan_to_num(np.array([Fa[k][i, a] * (side if k in SIGNED else 1.0) for k in F] + [hours[i]], float))

    def fixed(k):
        def pol(i, a, st):
            return {"open": k} if st["pos"] == 0 else base_pol(i, a, st)
        return pol

    def run(pol, ev=None):
        return eu.simulate(books, opens, prep, trade=dict(v216.GRID, policy=pol), win_start=5, events=ev, **KW)

    # ---- counterfactual outcomes
    per = {}
    for k in ACTIONS:
        ev = []
        r = run(fixed(k), ev)
        per[k] = outcomes(ev, idx)
        print(f"k={k}: dev4 {r['monthly_dev4']} orders {len(per[k])}", flush=True)
        if k == BASE_K:
            assert abs(r["monthly_dev4"] - 5.777) < 0.002, "k = 0.25 through the hook must reproduce v247 B18"
    keys = [kk for kk in set.intersection(*[set(v) for v in per.values()]) if kk[0] is not None]
    keys.sort(key=lambda x: (x[0], x[1]))
    X = np.array([state(kk[0], cols.index(kk[1]), kk[2]) for kk in keys])
    Y = 100 * np.clip(np.array([[per[k][kk][0] for k in ACTIONS] for kk in keys]), -0.03, 0.03)
    t_end = pd.DatetimeIndex([max(per[k][kk][1] for k in ACTIONS) for kk in keys])
    t_iss = pd.DatetimeIndex([idx[kk[0]] + pd.Timedelta(hours=4) for kk in keys])
    half = np.array([kk[0] % 2 for kk in keys])
    out = {"version": "v256", "actions": ACTIONS, "matched_orders": len(keys), "train": {}, "rows": {}, "trades": {}}
    dev = np.asarray((t_iss >= anchors[0]) & (t_iss < anchors[4]))
    out["dev_mean_outcome_by_action_pct_equity"] = {str(k): round(float(Y[dev, j].mean()), 4) for j, k in enumerate(ACTIONS)}
    print("matched orders", len(keys), "dev mean outcome (% equity) by action", out["dev_mean_outcome_by_action_pct_equity"], flush=True)

    models = {}
    for j in range(1, len(anchors)):
        keep = np.asarray((t_end < anchors[j] - EMBARGO) & (t_iss >= anchors[0]))
        pair = []
        for h in (0, 1):
            sel = keep & (half == h)
            pair.append([HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=50,
                                                       l2_regularization=1.0, random_state=10 * j + h + 3 * c).fit(X[sel], Y[sel, c])
                         for c in range(len(ACTIONS))])
        models[j] = pair
        out["train"][str(anchors[j].date())] = int(keep.sum())

    def year(i):
        t = idx[i] + pd.Timedelta(hours=4)
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    base = ACTIONS.index(BASE_K)

    def agent(margin):
        stats = {str(k): 0 for k in ACTIONS}

        def pol(i, a, st):
            if st["pos"] != 0:
                return base_pol(i, a, st)
            jj = year(i)
            k = BASE_K
            if jj > 0:
                x = state(i, a, st["sgn"])[None, :]
                pa = np.array([mm.predict(x)[0] for mm in models[jj][0]])
                pb = np.array([mm.predict(x)[0] for mm in models[jj][1]])
                ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
                if ba == bb and ba != base and pa[ba] - pa[base] > margin and pb[bb] - pb[base] > margin:
                    k = ACTIONS[ba]
            stats[str(k)] += 1
            return {"open": k}
        pol.stats = stats
        return pol

    for key, pol in (("v247_B18", fixed(BASE_K)), ("E1_agent", agent(0.0)), ("E2_agent_strict", agent(0.02))):
        ev = []
        r = run(pol, ev)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if hasattr(pol, "stats"):
            r["agent"] = dict(pol.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], r.get("agent"), flush=True)
    cands = ("E1_agent", "E2_agent_strict")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
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
    (HERE / "v256_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
