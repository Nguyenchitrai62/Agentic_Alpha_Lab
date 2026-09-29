"""v271: an RL OPTIMAL-STOPPING agent for losing dip rungs - at every 5m close, cut now or keep following the rule (on v266 B1).

Why (user goal: an RL trader acting like a real trader): v266 B1 showed that when and how a dip trade is stopped matters most (touch ->
5m-close stops raised every metric). A trader watching a losing dip position decides at every candle close whether the breakdown is
real (cut now) or a flush that will revert (hold). This is an optimal-stopping problem with EXACT returns: cutting at the close of
minute c fills at the next minute's open; holding continues with the B1 rule to its TP / close stop / backstop / bar end - both are known
from the 1m path, the payoffs are bounded inside the bar (TP 1 sigma, backstop 8 sigma), so the value estimate is not dominated by fat
tails (the failure of v214-v258). One-step policy improvement over the rule with cross-fitting, walk-forward.
Fixed before running.
Environment = v266 B1 (O1 books, sleeve budget 0.18, dip stops on 5m closes at 5 sigma + 8-sigma native backstop, v218 D2 settings).
Decision points: every 5m-block close c of an open dip rung before the rule's own exit, while the close is >= 2 sigma below the fill.
Data: one B1 run with a recording agent that always holds (reproduces B1); advantage(c) = [open(c+1) / fill - 1 - maker - taker] - [B1 net
return of that rung], clipped to [-0.05, 0.05].
State at c (1m data up to minute c only): loss in sigma units, minutes since the fill and to the bar end, 5- and 15-minute returns in
sigma units, the lowest low since the fill and the bounce from it (sigma units), BTC's return since the bar open (sigma_4h units), the
number of coins more than 2 sigma below their bar open, hour of day.
Model: HistGradientBoostingRegressor (depth 3, lr 0.05, 200 iter, min leaf 200, l2 1.0) on the advantage, two models per anchor on even /
odd bars (cross-fitting), fitted on checkpoints whose bar ended before Y - 7 days; 2021 follows the rule.
Policy: cut at the first checkpoint where BOTH halves predict an advantage above the margin.
  A1_stop_agent          margin 0
  A2_stop_agent_strict   margin 0.002 (0.2% of the rung notional)
Reference: v266 B1 (must reproduce dev4 6.13). SELECTION = robust criterion among A1, A2; the most recent year is scored once for the
selected row. Reported: checkpoints, dev mean advantage, cut counts, rung stops / TPs, trade win rates.

  python research/parallel/rounds/parallel-20260906-r2/v271/v271_stop_agent.py
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
EMBARGO = pd.Timedelta(days=7)
B1 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    Cc = eu.er.CACHE
    m = {k: pd.read_parquet(Cc / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    KW = dict(v221.KW, **B1)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    C, O, L, sig4, o2 = prep["C"], prep["O"], prep["L"], prep["sig4"], prep["o2"]
    b = cols.index("BTCUSDT")
    t_hold = idx + pd.Timedelta(hours=4)
    hours = np.array([t.hour for t in t_hold], float)

    def state(i, a, f, c, lv, sg):
        cc = float(C[i, c, a])
        lo = float(np.nanmin(L[i, f:c + 1, a]))
        r5 = (cc / float(C[i, c - 5, a]) - 1) / sg if c >= 5 else 0.0
        r15 = (cc / float(C[i, c - 15, a]) - 1) / sg if c >= 15 else 0.0
        btc = (float(C[i, c, b]) / float(O[i, 0, b]) - 1) / sig4[i][b] if np.isfinite(sig4[i][b]) and sig4[i][b] > 0 else 0.0
        nfl = float(np.nansum(C[i, c, :].astype(float) <= O[i, 0, :].astype(float) * (1 - 2 * sig4[i])))
        return np.nan_to_num(np.array([(cc / lv - 1) / sg, (c - f) / 240, (239 - c) / 240, r5, r15, (lo / lv - 1) / sg,
                                       (cc / lo - 1) / sg, btc, nfl, (hours[i] + c / 60) / 24], float))

    def run(agent=None, ev=None):
        return eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_exit_agent=agent, **KW)

    # ---- data: record every checkpoint of a B1 run (the recorder always holds)
    rec = []

    def recorder(i, a, r, f, c, lv, sg):
        rec.append((i, a, r, f, c, lv, sg))
        return False
    ev = []
    r0 = run(recorder, ev)
    assert abs(r0["monthly_dev4"] - 6.13) < 0.002, "the recording run must reproduce v266 B1"
    rung_ret, last = {}, None
    for e in ev:
        if e["kind"] == "rung_fill":
            last = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and last is not None:
            t0 = last["t"].floor("4h")
            i = int(np.searchsorted(t_hold, t0))
            f = int((last["t"] - t0).total_seconds() // 60)
            rung_ret[(i, cols.index(last["symbol"]), float(last["rung"]), f)] = float(e["ret"])
            last = None
    rungs = list(v221.KW.get("rungs", eu.RUNGS))
    X, Y, I, keep = [], [], [], []
    for (i, a, r, f, c, lv, sg) in rec:
        hold = rung_ret.get((i, a, float(rungs[r]), f))
        if hold is None:
            continue
        px = float(O[i, c + 1, a]) if c + 1 < 240 else float(o2[i][a])
        X.append(state(i, a, f, c, lv, sg))
        Y.append(np.clip(px / lv - 1 - eu.MAKER - eu.TAKER - hold, -0.05, 0.05))
        I.append(i)
    X, Y, I = np.array(X), np.array(Y), np.array(I)
    bar_end = t_hold[I] + pd.Timedelta(hours=4)
    dev = np.asarray((t_hold[I] >= anchors[0]) & (t_hold[I] < anchors[4]))
    out = {"version": "v271", "checkpoints": int(len(Y)), "dev_mean_advantage_pct": round(100 * float(Y[dev].mean()), 4),
           "dev_share_positive": round(float((Y[dev] > 0).mean()), 3), "train": {}, "rows": {}, "trades": {}}
    print("checkpoints", len(Y), "dev mean adv %", out["dev_mean_advantage_pct"], "share > 0", out["dev_share_positive"], flush=True)
    models = {}
    for j in range(1, len(anchors)):
        tr = np.asarray((bar_end < anchors[j] - EMBARGO) & (t_hold[I] >= anchors[0]))
        models[j] = [HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                                   random_state=10 * j + h).fit(X[tr & (I % 2 == h)], Y[tr & (I % 2 == h)]) for h in (0, 1)]
        out["train"][str(anchors[j].date())] = int(tr.sum())

    def year(i):
        t = t_hold[i]
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    def agent(margin):
        stats = {"asked": 0, "cut": 0}

        def ag(i, a, r, f, c, lv, sg):
            jj = year(i)
            if jj == 0:
                return False
            x = state(i, a, f, c, lv, sg)[None, :]
            stats["asked"] += 1
            if all(mm.predict(x)[0] > margin for mm in models[jj]):
                stats["cut"] += 1
                return True
            return False
        ag.stats = stats
        return ag

    for key, ag in (("v266_B1", None), ("A1_stop_agent", agent(0.0)), ("A2_stop_agent_strict", agent(0.002))):
        ev = []
        r = run(ag, ev)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if ag is not None:
            r["agent"] = dict(ag.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "rung tp/sl", r["stats"]["rung_tps"], r["stats"]["rung_stops"], r.get("agent"), flush=True)
    cands = ("A1_stop_agent", "A2_stop_agent_strict")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s_ = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
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
    (HERE / "v271_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
