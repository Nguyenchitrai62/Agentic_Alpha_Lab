"""v263: META-LABELING of the book entries - a classifier of "will this trade win" skips only the least promising signals.

Why (user goal: higher trade win rate without giving up return): v257's PPO skipped 89% of the signals, reached a 56.5% win rate but lost
the trend trades (dev4 3.9). Meta-labeling (Lopez de Prado) keeps the primary model's signals and learns a SECONDARY classifier of the
probability that the resulting trade is profitable after fees; only entries with a clearly low probability are skipped, so most trend
trades stay. The label is the exact realised outcome of each opening order in the reference engine run (O1 B18 rules).
Fixed before running.
Environment = v247 B18 (O1 books, sleeve budget 0.18, v218 D2 settings: G2 grid trader, rung x1.75, minute-5 rule, limits, SL market /
TP limit, break-even, governor, aligned sleeve, Bybit fees, adverse funding).
Data: the reference run's opening orders that FILLED (v256 outcome builder: position net PnL in equity-weight units, fees included, end time
= position close); label = net > 0. State at the issue (decision-bar close) = v256's (strength, sigma regime, r6 / r42 along the signal,
SuperTrend / market structure along the signal, WVF z, order-level flow along the signal, hour).
Model: HistGradientBoostingClassifier (depth 3, lr 0.05, 200 iter, min leaf 50, l2 1.0), two models per anchor on even / odd issue bars
(cross-fitting), fitted on filled orders whose position closed before Y - 7 days; 2021 takes every signal.
Policy: flat with a signal -> wait if the mean predicted win probability of both halves is below the threshold, else open (G2 in a
position unchanged).
  M1_skip_035   threshold 0.35
  M2_skip_040   threshold 0.40
Reference: G2 (must reproduce 5.777). SELECTION = robust criterion among M1, M2; the most recent year is scored once for the selected
row. Reported: skipped share per year, trade win rates.

  python research/parallel/rounds/parallel-20260906-r2/v263/v263_meta_label.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

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

    # ---- labels: realised outcome of every filled opening order in the reference run
    ev = []
    r0 = run(fixed(BASE_K), ev)
    assert abs(r0["monthly_dev4"] - 5.777) < 0.002, "G2 through the hook must reproduce v247 B18"
    oc = outcomes(ev, idx)
    keys = [kk for kk, (pnl, t_end) in oc.items() if kk[0] is not None and pnl != 0.0]
    keys.sort(key=lambda x: (x[0], x[1]))
    X = np.array([state(kk[0], cols.index(kk[1]), kk[2]) for kk in keys])
    Yb = np.array([oc[kk][0] > 0 for kk in keys], int)
    t_end = pd.DatetimeIndex([oc[kk][1] for kk in keys])
    t_iss = pd.DatetimeIndex([idx[kk[0]] + pd.Timedelta(hours=4) for kk in keys])
    half = np.array([kk[0] % 2 for kk in keys])
    out = {"version": "v263", "filled_orders": len(keys), "train": {}, "rows": {}, "trades": {}}
    dev = np.asarray((t_iss >= anchors[0]) & (t_iss < anchors[4]))
    out["dev_base_win_rate"] = round(float(Yb[dev].mean()), 3)
    print("filled orders", len(keys), "dev base win rate", out["dev_base_win_rate"], flush=True)
    models = {}
    for j in range(1, len(anchors)):
        keep = np.asarray((t_end < anchors[j] - EMBARGO) & (t_iss >= anchors[0]))
        models[j] = [HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=50,
                                                    l2_regularization=1.0, random_state=10 * j + h).fit(X[keep & (half == h)], Yb[keep & (half == h)])
                     for h in (0, 1)]
        out["train"][str(anchors[j].date())] = int(keep.sum())

    def year(i):
        t = idx[i] + pd.Timedelta(hours=4)
        return max(jj for jj, a0 in enumerate(anchors) if t >= a0) if t >= anchors[0] else 0

    def agent(thr):
        stats = {"open": 0, "skip": 0}

        def pol(i, a, st):
            if st["pos"] != 0:
                return base_pol(i, a, st)
            jj = year(i)
            if jj > 0:
                x = state(i, a, st["sgn"])[None, :]
                p = np.mean([mm.predict_proba(x)[0, 1] for mm in models[jj]])
                if p < thr:
                    stats["skip"] += 1
                    return "wait"
            stats["open"] += 1
            return "open"
        pol.stats = stats
        return pol

    for key, pol in (("v247_B18", fixed(BASE_K)), ("M1_skip_035", agent(0.35)), ("M2_skip_040", agent(0.40))):
        ev = []
        r = run(pol, ev)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        if hasattr(pol, "stats"):
            r["agent"] = dict(pol.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], r.get("agent"), flush=True)
    cands = ("M1_skip_035", "M2_skip_040")
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
    (HERE / "v263_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
