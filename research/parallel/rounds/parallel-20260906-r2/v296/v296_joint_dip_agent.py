"""v296: a smarter dip trader - joint size + take-profit decisions and a wider size action set, pooled 35-coin experience (registry v296).

Why (user goal 2026-09-30: DD ~15%, 6-7 %/month, win rate ~60%): v295 S1 (learned size x0.5 / x1 / x1.5 per dip rung, pooled experience
of the majors + the causal U2020 alts) is the first learned decision that beats the rules (CB -> S1: 5y 5.725 -> 6.084, DD 18.39 -> 17.50).
The take-profit agent (v294 X4) improved with data but alone stayed below CB. Two ways to go further with the same exact counterfactuals:
(a) decide size AND take-profit per rung (the TP agent picks among {0.5, 1.0, 1.5} sigma, the size agent scales the rung);
(b) a wider size action set: SKIP rungs the model clearly expects to lose (fewer bad trades -> lower DD, higher win rate) and DOUBLE the
    ones it clearly likes.
Data, replica, fidelity check, state features, cross-fitting, walk-forward fits (fills exited before anchor - 7 days), models: exactly
v294 (TP agent, margin 0.0010 = X4) and v295 (size model on y1.0, mu = training mean).
Fixed before running (everything else = CB / C4 rules):
  J1_size_tp     size = S1 rule (x1.5 if both halves > 2 mu, x0.5 if both < 0) + TP agent (X4)
  J2_size5       size: x0 if both < -mu; x0.5 if both < 0; x2 if both > 4 mu; x1.5 if both > 2 mu; else x1 (TP 1.0 sigma)
  J3_size5_tp    J2 size + TP agent (X4)
Reference: S1_ref (v295 S1, must reproduce dev4 6.275) and CB_ref (5.864). SELECTION = v286.dev_select among J1..J3; the selected row
replaces S1 only if dev_select prefers it over S1_ref; the most recent year is scored once for the selected row. Dev trade and dip-rung
win rates are reported for every row.

  python research/parallel/rounds/parallel-20260906-r2/v296/v296_joint_dip_agent.py
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v294 = _load("v294_j", RD / "v294/v294_wide_pool_exit_agent.py")
v293 = v294.v293


def hgb(seed):
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                         random_state=seed)


def rung_stats(events):
    rets = [e["ret"] for e in events if e.get("kind") in ("rung_tp", "rung_sl", "rung_timeout") and "ret" in e]
    return {"rungs": len(rets), "rung_win": round(float(np.mean([r > 0 for r in rets])), 3) if rets else None}


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_j", RD / "v286/v286_coinbase_member_upgrade.py")
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
    kw = dict(v221.KW, **v293.C4R)
    U = v294.universe()
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    data = {}
    for s in v293.MAJORS + U:
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            data[s] = d
        del A
    allf = pd.concat(data.values(), ignore_index=True)
    print("fills", len(allf), "assets", len(data), flush=True)
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    size_m, tp_m, mus = {}, {}, {}
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mus[jj] = float(y1[keep].mean())
        size_m[jj] = [hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tp_m[jj] = [[hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(len(v293.ACTIONS))]
                    for h in (0, 1)]
    pos = pd.Series(np.arange(len(btc.t0)), index=btc.t0)
    base = v293.ACTIONS.index(1.0)

    def state(i, a, r, f):
        T = idx[i] + pd.Timedelta(hours=4)
        jj = max([q for q, a0 in enumerate(anchors) if T >= a0], default=None)
        if jj is None or T not in pos.index:
            return None, None
        A, j = assets[cols[a]], int(pos[T])
        kk = j * 240 + f - 1
        sg = A.sig[j]
        return jj, np.array([[A.sp30(kk), v293.RUNGS[r], A.volreg[j], A.trend[j], btc.sp30(kk),
                              np.log(A.C[kk] / A.hmax24[kk]) / sg if A.hmax24[kk] > 0 else np.nan, (A.t0[j].hour + f // 60) % 24]])

    def size_hook(rule):
        stats = {"asked": 0, "x0": 0, "x0.5": 0, "x1.5": 0, "x2": 0}

        def pol(i, a, r, f):
            jj, x = state(i, a, r, f)
            if jj is None:
                return 1.0
            pa, pb = (mm.predict(x)[0] for mm in size_m[jj])
            mu = mus[jj]
            stats["asked"] += 1
            if rule == "s1":
                out = 1.5 if (pa > 2 * mu and pb > 2 * mu) else (0.5 if (pa < 0 and pb < 0) else 1.0)
            else:
                if pa < -mu and pb < -mu:
                    out = 0.0
                elif pa < 0 and pb < 0:
                    out = 0.5
                elif pa > 4 * mu and pb > 4 * mu:
                    out = 2.0
                elif pa > 2 * mu and pb > 2 * mu:
                    out = 1.5
                else:
                    out = 1.0
            if out != 1.0:
                stats[f"x{out:g}"] += 1
            return out
        pol.stats = stats
        return pol

    def tp_hook():
        stats = {"asked": 0, "changed": {str(mu): 0 for mu in v293.ACTIONS}}

        def pol(i, a, r, f):
            jj, x = state(i, a, r, f)
            if jj is None:
                return 1.0
            pa = np.array([mm.predict(x)[0] for mm in tp_m[jj][0]])
            pb = np.array([mm.predict(x)[0] for mm in tp_m[jj][1]])
            ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
            stats["asked"] += 1
            if ba == bb and ba != base and pa[ba] - pa[base] > 0.0010 and pb[bb] - pb[base] > 0.0010:
                stats["changed"][str(v293.ACTIONS[ba])] += 1
                return v293.ACTIONS[ba]
            return 1.0
        pol.stats = stats
        return pol

    out = {"version": "v296", "fills": int(len(allf)), "rows": {}, "trades": {}}
    runs = [("CB_ref", None, None), ("S1_ref", "s1", False), ("J1_size_tp", "s1", True), ("J2_size5", "s5", False), ("J3_size5_tp", "s5", True)]
    for key, rule, use_tp in runs:
        ev, extra = [], {}
        hooks = {}
        if rule:
            hooks["sleeve_fill_size"] = size_hook(rule)
        if use_tp:
            hooks["sleeve_tp"] = tp_hook()
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, **hooks, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["agents"] = {k: dict(h.stats) for k, h in hooks.items()}
        dev_ev = [e for e in ev if e["t"] < anchors[4]]
        r["dev_rungs"] = rung_stats(dev_ev)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trade win", out["trades"][key]["dev"]["win_rate"], "dev rungs", r["dev_rungs"], "agents", r["agents"], flush=True)
        ref = {"CB_ref": 5.864, "S1_ref": 6.275}.get(key)
        if ref is not None:
            assert abs(r["monthly_dev4"] - ref) < 0.002
    cands = ("J1_size_tp", "J2_size5", "J3_size5_tp")
    sel = v286.dev_select({k: out["rows"][k] for k in cands}, v204.worst_month)
    out["selected"] = sel
    out["replaces_s1"] = v286.dev_select({k: out["rows"][k] for k in ("S1_ref", sel)}, v204.worst_month) == sel
    s_ = out["rows"][sel]
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("SELECTED", sel, "replaces S1:", out["replaces_s1"], out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v296_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
