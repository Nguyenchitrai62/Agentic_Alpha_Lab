"""v241: learned position-sizing policy (offline policy optimisation, walk-forward) on the O1 foundation (registry v241).

Why: every learned trade manager (v214 fitted Q, v215 one-step improvement, v217 ES over grid parameters, v232 disciplined RL, v220 /
v235 dip bandits) failed to beat the rules, mostly because action VALUES of fat-tailed trend payoffs are hard to estimate. Sizing is a
different decision: a trader scales a position by how much the evidence agrees, and the new, verified information sources (order-level
whale flow v240, TradingView trend state v231) can tell when a signal is reliable. Here the agent learns a multiplier on the book target
directly by maximising the realised log growth of the training years (policy search, no value function).
Fixed before running.
Environment: v240 O1 books (A: TV + order-level whale flow; B: options + TV), v218 D2 settings (v216 G2 grid trader, sleeve budget 0.15,
rung x1.75, minute-5 rule, limit entries, SL market / TP limit, governor, aligned sleeve, Bybit fees, adverse funding).
State x (per coin a, decision row i, all known at the close of bar i; standardised with training-window statistics only):
  agree   sign(member A) * sign(member B) of the annual members (+1 agree, -1 disagree, 0 if either is 0)
  strength |book| / its 90-day rolling median (rows <= i)
  flow    order-level fl_big_imb6 * sign(book)       (large-order flow along the position direction)
  trend   tv_st_dir * sign(book)                      (4h SuperTrend along the position direction)
  vol     sigma_4h / its 540-bar rolling median
Policy: multiplier m = 1 + w * tanh(theta . x), theta in R^5 (no intercept: m = 1 at neutral evidence); books_adj = books * m.
Training (per anchor Y, rows whose realised bar ends before Y - 7 days; the first year 2021 uses m = 1): fast linear proxy of the
bar return r_i(theta) = sum_a m_ia * bookpnl_ia + sleeve_i, where bookpnl is the per-coin book PnL of the unscaled O1 run (engine
attribution); objective = mean log(1 + r_i) - 1e-3 * (lam * mean(min(r_i, 0)^2) / mean(r_i^2) + mu * |theta|^2) (the 1e-3
puts both terms on the scale of the mean bar log return, ~5e-4), maximised with L-BFGS-B
(theta in [-3, 3]^5, start 0). The final evaluation is the full engine on books_adj (the proxy is only used to fit theta).
  P1_growth       w 0.5, lam 0,   mu 0.01
  P2_downside     w 0.5, lam 0.5, mu 0.01
  P3_narrow       w 0.25, lam 0.5, mu 0.01
Reference: v240_O1 (must reproduce dev4 5.690). SELECTION = robust criterion among P1..P3; the most recent year is scored once for the
selected row. Reported: theta per anchor, mean / p10 / p90 multiplier per year.

  python research/parallel/rounds/parallel-20260906-r2/v241/v241_sizing_policy.py
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
VARIANTS = {"P1_growth": (0.5, 0.0, 0.01), "P2_downside": (0.5, 0.5, 0.01), "P3_narrow": (0.25, 0.5, 0.01)}


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

    out = {"version": "v241", "state": ["agree", "strength", "flow", "trend", "vol"], "variants": {k: list(v) for k, v in VARIANTS.items()},
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
    (HERE / "v241_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
