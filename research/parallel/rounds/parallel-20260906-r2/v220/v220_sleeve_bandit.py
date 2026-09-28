"""v220: learned dip-sleeve bid filter (contextual bandit, walk-forward) on the best executable pipeline v218 D2 (registry v220).

Why: the dip sleeve is the strongest alpha of the executable pipeline (v218: moving DD budget to it gave dev4 5.26, worst year 2.18),
but its stops are costly (dev: 187 stops at -6.7% vs 2702 take-profits at +1.3%). A trader chooses which dip bids to leave on the
book. At every 4h decision the agent decides, per coin and ladder rung, whether to place the bid (and may enlarge the best ones),
using only information known at the decision; the outcome of a placed bid is observed, a skipped bid earns 0 (full-information
contextual bandit, so no exploration is needed).

Fixed before running. Environment = v218 D2 (v216 G2 grid trader, sleeve stop-risk budget 0.15, rung size x1.75, v205 books /
governor / aligned sleeve / Bybit fees / adverse funding, minute-5 rule, 1m execution). Data: the unfiltered D2 run; every filled
rung gives (decision row i, coin, rung, net return of the bid after fees). Features at the decision of bar i: rl.market_features
(returns 1/6/42/180 bars and 42/180-bar high/low distances in sigma_4h units, vol regime, sigma_4h, BTC 6/42-bar returns, the four
book members), the ensemble book value, the rung depth (2.5..4 sigma_4h) and the hour of day. Model: HistGradientBoostingRegressor
(depth 4, lr 0.05, 200 iter, min leaf 100, l2 1.0) on the net return clipped to [-10%, +5%]. Walk-forward: the model for anchor year
Y uses bids whose exit is before Y - 7 days; the first year (2021) places every bid.
  F1_skip_negative   skip a bid whose predicted net return < 0.
  F2_skip_bottom25   skip a bid whose prediction is below the 25th percentile of the training predictions.
  F3_skip_boost      F2, and x1.25 size for bids above the 75th percentile (the stop-risk budget still applies).
Reference: v218_D2 (no filter). SELECTION = robust criterion among F1..F3; the most recent year is scored once for the selected row.
Reported: bids placed / skipped, filled bids, win rate and average of the sleeve, trade statistics of the book.

  python research/parallel/rounds/parallel-20260906-r2/v220/v220_sleeve_bandit.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "rl"))
import trader_rl as rl  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v216 = _load("v216", HERE.parent / "v216/v216_trade_grid.py")
eu, v204, v213 = v216.eu, v216.v204, v216.v213
KW = dict(v216.KW, sleeve_risk_budget=0.15, size_mult=1.75)
EMBARGO = pd.Timedelta(days=7)
RUNGS = list(eu.RUNGS)


def sleeve_outcomes(events, idx):
    """(decision row i, coin, rung index, exit time, net return) of every filled bid (rung_fill is followed by its exit)."""
    pos = {t: k for k, t in enumerate(idx)}
    out, pending = [], {}
    cols = {}
    for e in events:
        if e["kind"] == "rung_fill":
            pending[e["symbol"]] = e
        elif e["kind"] in ("rung_tp", "rung_sl", "rung_timeout") and e["symbol"] in pending:
            f = pending.pop(e["symbol"])
            bar = f["t"].floor("4h") - pd.Timedelta(hours=4)
            if bar in pos:
                out.append((pos[bar], f["symbol"], RUNGS.index(f["rung"]), e["t"], e["ret"]))
    return out


def main():
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
    bk = books.to_numpy()
    hours = np.array([(t + pd.Timedelta(hours=4)).hour for t in idx])
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    pol = v216.grid_policy(*v216.VARIANTS["G2_medium"])
    trade = dict(v216.GRID, policy=pol)

    def xrow(i, a, r):
        return np.concatenate([np.nan_to_num(feats[i, a], nan=0.0, posinf=0.0, neginf=0.0), [bk[i, a], RUNGS[r], hours[i]]])

    ev0 = []
    base = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev0, **KW)
    assert abs(base["monthly_dev4"] - 5.261) < 0.002, "must reproduce v218 D2"
    obs = sleeve_outcomes(ev0, idx)
    X = np.array([xrow(i, cols.index(s), r) for i, s, r, _, _ in obs])
    y = np.clip(np.array([o[4] for o in obs]), -0.10, 0.05)
    tend = pd.DatetimeIndex([o[3] for o in obs])
    models, q = {}, {}
    out = {"version": "v220", "features": fnames + ["book", "rung", "hour"], "bids_observed": len(obs), "train": {}, "rows": {}, "trades": {}}
    for j in range(1, len(anchors)):
        keep = np.asarray(tend < anchors[j] - EMBARGO)
        m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=200, min_samples_leaf=100, l2_regularization=1.0,
                                          random_state=j).fit(X[keep], y[keep])
        pr = m.predict(X[keep])
        models[j], q[j] = m, (float(np.percentile(pr, 25)), float(np.percentile(pr, 75)))
        out["train"][str(anchors[j].date())] = dict(n=int(keep.sum()), q25=q[j][0], q75=q[j][1], mean_y=float(y[keep].mean()))
        print(f"model {anchors[j].date()}: {int(keep.sum())} bids, q25 {q[j][0]:.4f} q75 {q[j][1]:.4f}", flush=True)

    def year(i):
        t = idx[i] + pd.Timedelta(hours=4)
        k = 0
        for jj, a0 in enumerate(anchors):
            if t >= a0:
                k = jj
        return k

    def make_filter(kind):
        cache, stats = {}, {"asked": 0, "skipped": 0, "boosted": 0}

        def flt(i, a, r):
            jj = year(i)
            if jj == 0:
                return 1.0
            key = (i, a, r)
            if key not in cache:
                p = float(models[jj].predict(xrow(i, a, r)[None, :])[0])
                lo, hi = q[jj]
                mult = 1.0
                if (kind == "F1" and p < 0) or (kind in ("F2", "F3") and p < lo):
                    mult = 0.0
                elif kind == "F3" and p > hi:
                    mult = 1.25
                cache[key] = mult
                stats["asked"] += 1
                stats["skipped"] += mult == 0.0
                stats["boosted"] += mult > 1.0
            return cache[key]
        flt.stats = stats
        return flt

    runs = [("v218_D2", None)] + [(k, make_filter(k[:2])) for k in ("F1_skip_negative", "F2_skip_bottom25", "F3_skip_boost")]
    for key, flt in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_filter=flt, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        dev = [o for o in sleeve_outcomes(ev, idx) if o[3] < anchors[4]]
        rets = np.array([o[4] for o in dev])
        r["sleeve_dev"] = dict(bids=len(dev), win_rate=round(float((rets > 0).mean()), 3), avg_pct=round(100 * float(rets.mean()), 3))
        if flt is not None:
            r["filter"] = dict(flt.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y_["anchor"][:4], y_["net_pct"], y_["dd_1m_pct"]) for y_ in r["yearly"][:4]],
              "sleeve dev", r["sleeve_dev"], r.get("filter"), flush=True)
    cands = ("F1_skip_negative", "F2_skip_bottom25", "F3_skip_boost")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y_["anchor"][:4], y_["net_pct"], y_["dd_1m_pct"]) for y_ in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v220_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
