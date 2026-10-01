"""v302: give the learned dip agents the BREADTH of the flush (registry v302) - a drawdown-first step.

Why (user goals 2026-09-30: DD ~15 / 6-7 %/month / win ~60%): the biggest dip-sleeve losses are systemic - several coins' bids are hit and stopped in the
same flush (2024-08-05, 2023-04..06: research/diagnostics/cb_dd, o1_dd_episodes/systemic_fills). The v293-v301 agents see the coin's own price action
and BTC's 30-minute move only, so they cannot tell an idiosyncratic dip (reverts well) from a market-wide liquidation cascade (stops cluster).
Three market-breadth features, all known at minute f-1 of the rung's 4h bar and computed ONLY from the five majors (so they exist live and in the
pooled training rows alike, for alts and majors):
  x7  b_mean   mean over the five majors of sp30 (30-minute log return / (sigma_1m sqrt 30), as the v293 feature)
  x8  b_min    min over the five majors of sp30
  x9  b_flush  number of majors whose 1m low since minute 16 of the bar has already crossed their own 2.5-sigma_4h bid level (0..5); the
               coin's own earlier touch counts only when the coin is a major (alts' rows count the majors only) - same definition in
               training and live
Everything else = v301 G2 (35-coin pooled experience U2020, standalone replica, cross-fitted HGB, fits on fills that exited before anchor - 7 days,
size rule S1, X4 take-profit rule, C4 rules, dip budget 0.26).
Fixed before running:
  H1_breadth_both   size agent and take-profit agent both use x0..x9
  H2_breadth_size   only the size agent uses x0..x9 (take-profit agent unchanged)
Reference: G2_ref (7 features; must reproduce dev4 6.527 and dev DD 17.33).
SELECTION (registered for THIS version, a drawdown-first step; dev years only): pool = rows with dev4 >= G2_ref - 0.15, worst dev year >=
G2_ref's - 0.15 and no losing dev year; within the pool the lowest dev DD (ties -> dev4). The selected row replaces G2 only if its dev DD is
lower than G2_ref's by >= 0.4 points. The most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v302/v302_flush_breadth.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v301 = _load("v301_b", RD / "v301/v301_return_first_budget.py")
v297, v296, v294, v293 = v301.v297, v301.v296, v301.v294, v301.v293
BUDGET = 0.26


def breadth_arrays(assets):
    """b_mean / b_min per minute and b_flush per (bar, minute) from the five majors (all on the common 1m grid)."""
    maj = [assets[s] for s in v293.MAJORS]
    sp = []
    for A in maj:
        c = pd.Series(A.C)
        sp.append((np.log(c / c.shift(30)) / (pd.Series(A.sig1) * np.sqrt(30))).where(pd.Series(A.sig1) > 0).to_numpy())
    sp = np.vstack(sp)
    b_mean, b_min = np.nanmean(sp, axis=0), np.nanmin(sp, axis=0)
    nb = maj[0].nb
    flush = np.zeros((nb, 240), dtype=np.int8)
    for A in maj:
        low = A.L[: nb * 240].reshape(nb, 240).copy()
        low[:, :16] = np.inf
        runmin = np.fmin.accumulate(low, axis=1)
        thr = (A.o[:nb] * (1 - 2.5 * A.sig[:nb]))[:, None]
        flush += (runmin < thr).astype(np.int8)
    return b_mean, b_min, flush


def build_hooks_breadth(eu, idx, cols, size_cols, tp_cols):
    """J1/G2 agents (v301 fits and rules) with the state extended by the breadth features; each model reads its own column subset."""
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    b_mean, b_min, flush = breadth_arrays(assets)
    parts = []
    for s in v293.MAJORS + v294.universe():
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            parts.append(d)
        del A
    allf = pd.concat(parts, ignore_index=True)
    kk = (allf["j"].to_numpy() * 240 + allf["f"].to_numpy() - 1).astype(int)
    allf["x7"], allf["x8"], allf["x9"] = b_mean[kk], b_min[kk], flush[allf["j"].to_numpy(), allf["f"].to_numpy() - 1].astype(float)
    Xall = allf[[f"x{q}" for q in range(10)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    size_m, tp_m, mus = {}, {}, {}
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mus[jj] = float(y1[keep].mean())
        Xs, Xt = Xall[:, size_cols], Xall[:, tp_cols]
        size_m[jj] = [v296.hgb(10 * jj + h).fit(Xs[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tp_m[jj] = [[v296.hgb(10 * jj + h + 3 * c).fit(Xt[keep & (half == h)], Y[keep & (half == h), c]) for c in range(len(v293.ACTIONS))]
                    for h in (0, 1)]
    pos = pd.Series(np.arange(len(btc.t0)), index=btc.t0)
    base = v293.ACTIONS.index(1.0)

    def state(i, a, r, f):
        T = idx[i] + pd.Timedelta(hours=4)
        jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
        if jj is None or T not in pos.index:
            return None, None
        A, j = assets[cols[a]], int(pos[T])
        k = j * 240 + f - 1
        sg = A.sig[j]
        x = np.array([[A.sp30(k), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(k),
                       np.log(A.C[k] / A.hmax24[k]) / sg if A.hmax24[k] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24,
                       b_mean[k], b_min[k], float(flush[j, f - 1])]])
        return jj, x

    def size(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa, pb = (mm.predict(x[:, size_cols])[0] for mm in size_m[jj])
        mu = mus[jj]
        return 1.5 if (pa > 2 * mu and pb > 2 * mu) else (0.5 if (pa < 0 and pb < 0) else 1.0)

    def tp(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa = np.array([mm.predict(x[:, tp_cols])[0] for mm in tp_m[jj][0]])
        pb = np.array([mm.predict(x[:, tp_cols])[0] for mm in tp_m[jj][1]])
        ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
        if ba == bb and ba != base and pa[ba] - pa[base] > 0.0010 and pb[bb] - pb[base] > 0.0010:
            return v293.ACTIONS[ba]
        return 1.0
    return size, tp


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_h", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    seven, ten = list(range(7)), list(range(10))
    variants = {"G2_ref": (seven, seven), "H1_breadth_both": (ten, ten), "H2_breadth_size": (ten, seven)}
    out = {"version": "v302", "rows": {}, "trades": {}}
    for key, (sc, tc) in variants.items():
        size, tp = build_hooks_breadth(eu, idx, cols, sc, tc)
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=size, sleeve_tp=tp,
                        **dict(v221.KW, **dict(v293.C4R, sleeve_risk_budget=BUDGET)))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["dev_rungs"] = v296.rung_stats([e for e in ev if e["t"] < anchors[4]])
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trade win", out["trades"][key]["dev"]["win_rate"], "dev rungs", r["dev_rungs"], flush=True)
        if key == "G2_ref":
            assert abs(r["monthly_dev4"] - 6.527) < 0.002 and abs(r["dev_dd"] - 17.33) < 0.02
    ref = out["rows"]["G2_ref"]
    pool = {k: v for k, v in out["rows"].items() if k != "G2_ref" and v["monthly_dev4"] >= ref["monthly_dev4"] - 0.15
            and v["worst_dev_month_pct"] >= ref["worst_dev_month_pct"] - 0.15 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    sel = min(pool, key=lambda k: (pool[k]["dev_dd"], -pool[k]["monthly_dev4"])) if pool else None
    if sel and pool[sel]["dev_dd"] > ref["dev_dd"] - 0.4:
        sel = None
    out["selected"] = sel
    if sel:
        s_ = out["rows"][sel]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"][sel]["_hidden"]}
    else:
        out["final_score_selected"] = "no row meets the drawdown-first rule - G2 stays; nothing scored on the most recent year"
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v302_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
