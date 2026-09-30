"""v301: RETURN-FIRST step - give the learned dip sleeve more risk budget (registry v301; first version under the stepwise rule).

User 2026-09-30: three goals (win rate, return / month, DD) - improve step by step, easiest first; a version with DD > 15% is not
rejected for that alone. The return is the easiest lever: the learned dip agents skip / shrink bad rungs (x0.5 or x0) and enlarge good
ones, so the sleeve can carry more risk budget than the rule sleeve did (v219: budget 0.18-0.21 broke DD 20 WITHOUT agents; with agents
v297 A2 budget 0.24 lowered DD at a lower book target). Everything else = v296 J1 (35-coin pooled experience, same fits and hooks).
Fixed before running:
  G1_b22          J1 agents, sleeve risk budget 0.22
  G2_b26          J1 agents, sleeve risk budget 0.26
  G3_size5tp_b22  v296 J3 agents (5-action size: skip / x0.5 / x1 / x1.5 / x2 + X4 take-profit), budget 0.22
Reference: J1_ref (budget 0.18; must reproduce dev4 6.268).
SELECTION = the STEPWISE RETURN-FIRST RULE (registered here, applies from v301 on, never retroactively): pool = rows with dev DD <= the
reference's dev DD + 0.5, worst dev year >= 3.0 %/month and no losing dev year; pick the highest dev4 (ties -> worst dev year). The
selected row replaces J1 only if its dev4 beats J1's by >= 0.05. The most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v301/v301_return_first_budget.py
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


v297 = _load("v297_g", RD / "v297/v297_risk_realloc.py")
v296, v294, v293 = v297.v296, v297.v294, v297.v293


def build_hooks(eu, idx, cols):
    """J1 fits (v296 / v297): size model on y1.0, TP models per action; returns size rules S1 and 5-action plus the X4 TP hook."""
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + v294.universe():
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc).assign(sym=s)
        if len(d):
            parts.append(d)
        del A
    allf = pd.concat(parts, ignore_index=True)
    X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
    Y = np.clip(allf[[f"y{mu}" for mu in v293.ACTIONS]].to_numpy(float), -0.10, 0.08)
    y1 = Y[:, v293.ACTIONS.index(1.0)]
    half = (allf["j"] % 2).to_numpy()
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    size_m, tp_m, mus = {}, {}, {}
    for jj, a0 in enumerate(anchors):
        keep = np.asarray(allf.t_exit < a0 - v293.EMBARGO)
        mus[jj] = float(y1[keep].mean())
        size_m[jj] = [v296.hgb(10 * jj + h).fit(X[keep & (half == h)], y1[keep & (half == h)]) for h in (0, 1)]
        tp_m[jj] = [[v296.hgb(10 * jj + h + 3 * c).fit(X[keep & (half == h)], Y[keep & (half == h), c]) for c in range(len(v293.ACTIONS))]
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

    def size_s1(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa, pb = (mm.predict(x)[0] for mm in size_m[jj])
        mu = mus[jj]
        return 1.5 if (pa > 2 * mu and pb > 2 * mu) else (0.5 if (pa < 0 and pb < 0) else 1.0)

    def size_s5(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa, pb = (mm.predict(x)[0] for mm in size_m[jj])
        mu = mus[jj]
        if pa < -mu and pb < -mu:
            return 0.0
        if pa < 0 and pb < 0:
            return 0.5
        if pa > 4 * mu and pb > 4 * mu:
            return 2.0
        if pa > 2 * mu and pb > 2 * mu:
            return 1.5
        return 1.0

    def tp(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa = np.array([mm.predict(x)[0] for mm in tp_m[jj][0]])
        pb = np.array([mm.predict(x)[0] for mm in tp_m[jj][1]])
        ba, bb = int(np.argmax(pa)), int(np.argmax(pb))
        if ba == bb and ba != base and pa[ba] - pa[base] > 0.0010 and pb[bb] - pb[base] > 0.0010:
            return v293.ACTIONS[ba]
        return 1.0
    return size_s1, size_s5, tp


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_g", RD / "v286/v286_coinbase_member_upgrade.py")
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
    size_s1, size_s5, tp = build_hooks(eu, idx, cols)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    rows = {"J1_ref": (size_s1, 0.18), "G1_b22": (size_s1, 0.22), "G2_b26": (size_s1, 0.26), "G3_size5tp_b22": (size_s5, 0.22)}
    out = {"version": "v301", "rule": "stepwise return-first", "rows": {}, "trades": {}}
    for key, (size, budget) in rows.items():
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=size, sleeve_tp=tp,
                        **dict(v221.KW, **dict(v293.C4R, sleeve_risk_budget=budget)))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["dev_rungs"] = v296.rung_stats([e for e in ev if e["t"] < anchors[4]])
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trade win", out["trades"][key]["dev"]["win_rate"], "dev rungs", r["dev_rungs"], flush=True)
        if key == "J1_ref":
            assert abs(r["monthly_dev4"] - 6.268) < 0.002
    ref = out["rows"]["J1_ref"]
    pool = {k: v for k, v in out["rows"].items() if k != "J1_ref" and v["dev_dd"] <= ref["dev_dd"] + 0.5 and v["worst_dev_month_pct"] >= 3.0
            and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    sel = max(pool, key=lambda k: (pool[k]["monthly_dev4"], pool[k]["worst_dev_month_pct"])) if pool else None
    if sel and pool[sel]["monthly_dev4"] < ref["monthly_dev4"] + 0.05:
        sel = None
    out["selected"] = sel
    if sel:
        s_ = out["rows"][sel]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"][sel]["_hidden"]}
    else:
        out["final_score_selected"] = "no row meets the return-first rule - J1 stays; nothing scored on the most recent year"
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
    (HERE / "v301_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
