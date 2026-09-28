"""v242: entry-locked sizing - the v241 policy with the multiplier fixed at the start of each signal run (registry v242).

Why: v241's learned sizing (stable theta: size up with signal strength, order-level whale flow and SuperTrend along the position) lost
in the engine because the multiplier changed every bar, so the target crossed the grid trader's thresholds more often (more, smaller
trades, win rate 47%). A trader sizes a position ONCE, at entry, by the conviction at that moment. Diagnostic-motivated by v241's dev
trade statistics (first four years only).
Fixed before running. Everything as v241 (O1 books, state, walk-forward fits of theta on the linear attribution proxy, v218 D2 settings)
except the multiplier path: per coin, a signal run = consecutive decision rows with |book| >= 0.05 (the G2 opening threshold) and the
same sign; the multiplier of the run's FIRST row is kept for the whole run (rows outside runs: 1). The first year (2021) uses m = 1.
  L1_locked_w50   v241 P1 settings (w 0.5, lam 0,   mu 0.01), locked
  L2_locked_w25   v241 P3 settings (w 0.25, lam 0.5, mu 0.01), locked
Reference: v240_O1 (must reproduce dev4 5.690). SELECTION = robust criterion among L1, L2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v242/v242_locked_sizing.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = Path(__file__).parent
RD = HERE.parent
EMBARGO = pd.Timedelta(days=7)
VARIANTS = {"L1_locked_w50": (0.5, 0.0, 0.01), "L2_locked_w25": (0.25, 0.5, 0.01)}
THETA_OPEN = 0.05


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v240 = _load("v240_p", RD / "v240/v240_order_level_flow.py")
v232 = _load("v232_p", RD / "v232/v232_disciplined_rl.py")


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    books = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))

    # ---- state
    sgn = np.sign(books)
    agree = np.sign(m["A"]) * np.sign(m["B"])
    ab = books.abs()
    strength = ab / ab.rolling(540, min_periods=90).median().replace(0, np.nan)
    flow = pd.DataFrame({s: v240.flo.flow_features(s, idx)["fl_big_imb6"].to_numpy() for s in cols}, index=idx) * sgn
    trend = v232.tv_frames(idx, cols)["tv_st_dir"] * sgn
    o1 = opens.reindex(idx)[cols].shift(-1)
    sig = np.log(o1).diff().rolling(360, min_periods=120).std()
    vol = sig / sig.rolling(540, min_periods=180).median()
    X = np.stack([f.reindex(idx)[cols].to_numpy(float) for f in (agree, strength, flow, trend, vol)], axis=2)  # (n, na, 5)

    # ---- unscaled run with per-coin attribution
    att = []
    base = eu.simulate(books, opens, prep, trade=trade, win_start=5, attrib=att, **v221.KW)
    assert abs(base["monthly_dev4"] - 5.690) < 0.002, "must reproduce v240 O1"
    t_of = {t: k for k, t in enumerate(idx + pd.Timedelta(hours=4))}
    P = np.zeros((len(idx), len(cols)))
    S = np.zeros(len(idx))
    live = np.zeros(len(idx), bool)
    for t, bp, sp in att:
        k = t_of.get(t)
        if k is not None:
            P[k], S[k], live[k] = bp, sp, True
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    bar_end = idx + pd.Timedelta(hours=8)  # the decision row i earns over the holding bar ending at idx[i] + 8h

    def fit(Y, w, lam, mu):
        tr = live & np.asarray(bar_end < Y - EMBARGO)
        Xt = X[tr]
        mu_x = np.nanmean(Xt.reshape(-1, 5), axis=0)
        sd_x = np.nanstd(Xt.reshape(-1, 5), axis=0) + 1e-9
        Z = np.nan_to_num((Xt - mu_x) / sd_x)
        Pt, St = P[tr], S[tr]

        def neg(th):
            mult = 1 + w * np.tanh(Z @ th)
            r = (mult * Pt).sum(axis=1) + St
            dn = np.minimum(r, 0.0)
            obj = np.mean(np.log1p(np.clip(r, -0.99, None))) - lam * np.mean(dn ** 2) / (np.mean(r ** 2) + 1e-12) * 1e-3 - mu * th @ th * 1e-3
            return -obj
        res = minimize(neg, np.zeros(5), method="L-BFGS-B", bounds=[(-3, 3)] * 5)
        return res.x, mu_x, sd_x, int(tr.sum())

    out = {"version": "v242", "state": ["agree", "strength", "flow", "trend", "vol"], "variants": {k: list(v) for k, v in VARIANTS.items()},
           "theta": {}, "mult_stats": {}, "rows": {}, "trades": {}}
    runs = {"v240_O1": books}
    for key, (w, lam, mu) in VARIANTS.items():
        M = np.ones((len(idx), len(cols)))
        out["theta"][key] = {}
        for j in range(1, len(anchors)):
            Y = anchors[j]
            end = anchors[j + 1] if j + 1 < len(anchors) else Y + pd.Timedelta(days=365)
            th, mu_x, sd_x, n = fit(Y, w, lam, mu)
            rows = np.asarray((idx + pd.Timedelta(hours=4) >= Y) & (idx + pd.Timedelta(hours=4) < end))
            Z = np.nan_to_num((X[rows] - mu_x) / sd_x)
            M[rows] = 1 + w * np.tanh(Z @ th)
            out["theta"][key][str(Y.date())] = dict(theta=[round(float(v), 4) for v in th], train_rows=n)
        # lock the multiplier at the first row of every signal run (same sign, |book| >= THETA_OPEN)
        bk = books.to_numpy()
        for a in range(len(cols)):
            cur = 1.0
            for i in range(len(idx)):
                if abs(bk[i, a]) < THETA_OPEN:
                    M[i, a] = 1.0
                    cur = None
                    continue
                if cur is None or i == 0 or np.sign(bk[i, a]) != np.sign(bk[i - 1, a]) or abs(bk[i - 1, a]) < THETA_OPEN:
                    cur = M[i, a]
                M[i, a] = cur
        dev = np.asarray(idx + pd.Timedelta(hours=4) < anchors[4])
        out["mult_stats"][key] = dict(mean=round(float(M[dev].mean()), 3), p10=round(float(np.percentile(M[dev], 10)), 3),
                                      p90=round(float(np.percentile(M[dev], 90)), 3))
        runs[key] = books * M
        print(key, "theta", out["theta"][key], "dev multipliers", out["mult_stats"][key], flush=True)
    for key, bk in runs.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **v221.KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trades", out["trades"][key]["dev"], flush=True)
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
    (HERE / "v242_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
