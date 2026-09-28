"""v243: dip-bid filter with the order-level whale-flow state, on the O1 foundation (registry v243).

Why: v235 (TradingView state) and v220 (basic context) could not predict dip-bid outcomes, but neither saw who was selling. Large-order
flow is the missing piece for a dip buyer: a dip into heavy large-order selling tends to continue, a dip on retail selling while large
orders buy tends to revert. The order-level whale flow (v240) is verified information (audited, exact live feed).
Fixed before running. Environment = v240 O1 books (A: TV + order-level flow; B: options + TV) with the v218 D2 settings. Data / model /
walk-forward exactly as v235 (filled bids of the unfiltered O1 run, HGB on the clipped net bid return, bids exited before Y - 7 days,
2021 places every bid), with the state = v235 state + the coin's six order-level flow features (v236/flow_features.FL on
data/raw/aggflow_20260928_orders) at the decision row.
  S1_skip_negative, S2_skip_bottom25, S3_skip_boost   as v235
Reference: v240_O1 (no filter, must reproduce dev4 5.690). SELECTION = robust criterion among S1..S3; the most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v243/v243_sleeve_flow_bandit.py
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


v220 = _load("v220", HERE.parent / "v220/v220_sleeve_bandit.py")
v221 = _load("v221", HERE.parent / "v221/v221_grid_hysteresis.py")
v232 = _load("v232", HERE.parent / "v232/v232_disciplined_rl.py")
v240 = _load("v240_s", HERE.parent / "v240/v240_order_level_flow.py")
eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
EMBARGO, RUNGS = v220.EMBARGO, v220.RUNGS


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    flow = {f: pd.DataFrame({s: v240.flo.flow_features(s, idx)[f].to_numpy() for s in cols}, index=idx) for f in v240.flo.FL}
    feats, fnames = rl.market_features(opens, idx, cols, dict(mA=m["A"], mB=m["B"], mAq=m["Aq"], mBq=m["Bq"], **v232.tv_frames(idx, cols), **flow))
    bk = books.to_numpy()
    hours = np.array([(t + pd.Timedelta(hours=4)).hour for t in idx])
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))

    def xrow(i, a, r):
        return np.concatenate([np.nan_to_num(feats[i, a], nan=0.0, posinf=0.0, neginf=0.0), [bk[i, a], RUNGS[r], hours[i]]])

    ev0 = []
    base = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev0, **v221.KW)
    assert abs(base["monthly_dev4"] - 5.690) < 0.002, "must reproduce v240 O1"
    obs = v220.sleeve_outcomes(ev0, idx)
    X = np.array([xrow(i, cols.index(s), r) for i, s, r, _, _ in obs])
    y = np.clip(np.array([o[4] for o in obs]), -0.10, 0.05)
    tend = pd.DatetimeIndex([o[3] for o in obs])
    models, q = {}, {}
    out = {"version": "v243", "features": fnames + ["book", "rung", "hour"], "bids_observed": len(obs), "train": {}, "rows": {}, "trades": {}}
    for j in range(1, len(anchors)):
        keep = np.asarray(tend < anchors[j] - EMBARGO)
        mdl = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=200, min_samples_leaf=100, l2_regularization=1.0,
                                            random_state=j).fit(X[keep], y[keep])
        pr = mdl.predict(X[keep])
        models[j], q[j] = mdl, (float(np.percentile(pr, 25)), float(np.percentile(pr, 75)))
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
                if (kind == "S1" and p < 0) or (kind in ("S2", "S3") and p < lo):
                    mult = 0.0
                elif kind == "S3" and p > hi:
                    mult = 1.25
                cache[key] = mult
                stats["asked"] += 1
                stats["skipped"] += mult == 0.0
                stats["boosted"] += mult > 1.0
            return cache[key]
        flt.stats = stats
        return flt

    runs = [("v240_O1", None)] + [(k, make_filter(k[:2])) for k in ("S1_skip_negative", "S2_skip_bottom25", "S3_skip_boost")]
    for key, flt in runs:
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_filter=flt, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        dev = [o for o in v220.sleeve_outcomes(ev, idx) if o[3] < anchors[4]]
        rets = np.array([o[4] for o in dev])
        r["sleeve_dev"] = dict(bids=len(dev), win_rate=round(float((rets > 0).mean()), 3), avg_pct=round(100 * float(rets.mean()), 3))
        if flt is not None:
            r["filter"] = dict(flt.stats)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y_["anchor"][:4], y_["net_pct"], y_["dd_1m_pct"]) for y_ in r["yearly"][:4]],
              "sleeve dev", r["sleeve_dev"], r.get("filter"), flush=True)
    sel = v204.robust_select({k: out["rows"][k] for k in ("S1_skip_negative", "S2_skip_bottom25", "S3_skip_boost")})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y_["anchor"][:4], y_["net_pct"], y_["dd_1m_pct"]) for y_ in s["yearly"]],
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
    (HERE / "v243_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
