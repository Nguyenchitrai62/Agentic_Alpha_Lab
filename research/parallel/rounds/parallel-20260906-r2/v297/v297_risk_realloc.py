"""v297: move risk from the book to the (now learned) dip sleeve - towards the new goal DD ~15% (registry v297).

Why (user goal 2026-09-30: DD ~15%, 6-7 %/month, win rate ~60%): the learned dip agents (v295 size, v296 J1 = size + take-profit) raise
the return but the drawdown stays ~17.5-18 because the worst episodes are driven by the BOOK (2022 whipsaws, the 2024-07 short squeeze;
research/diagnostics/cb_dd). The dip sleeve with its agents is now the better risk (dip-rung win rate ~70%, uncorrelated with the book).
Lower the book's vol target and give the sleeve more risk budget. Everything else = v296 J1 (same pooled 35-coin data, fits, hooks).
Fixed before running:
  A1_t20_b18   book target 0.20, sleeve risk budget 0.18
  A2_t20_b24   book target 0.20, sleeve risk budget 0.24
  A3_t15_b24   book target 0.15, sleeve risk budget 0.24
Reference: J1_ref (target 0.25, budget 0.18; must reproduce dev4 6.268).
SELECTION (new-goal rule, dev years only): tier 1 = rows with dev DD (max yearly 1m-marked DD 2021-2024) <= 15.0, no losing dev year and
worst dev year >= 3.0 %/month; if empty, tier 2 = the same with dev DD <= 16.0; within the first non-empty tier the highest worst dev year
(ties -> dev4). If both tiers are empty nothing replaces J1. The most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v297/v297_risk_realloc.py
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
ROWS = {"J1_ref": (0.25, 0.18), "A1_t20_b18": (0.20, 0.18), "A2_t20_b24": (0.20, 0.24), "A3_t15_b24": (0.15, 0.24)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v296 = _load("v296_r", RD / "v296/v296_joint_dip_agent.py")
v294, v293 = v296.v294, v296.v293


def build_j1_hooks(eu, idx, cols):
    """The v296 J1 agents (size S1 rule + X4 take-profit), fitted exactly as v296."""
    U = v294.universe()
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    parts = []
    for s in v293.MAJORS + U:
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

    def size(i, a, r, f):
        jj, x = state(i, a, r, f)
        if jj is None:
            return 1.0
        pa, pb = (mm.predict(x)[0] for mm in size_m[jj])
        mu = mus[jj]
        return 1.5 if (pa > 2 * mu and pb > 2 * mu) else (0.5 if (pa < 0 and pb < 0) else 1.0)

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
    return size, tp


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_r", RD / "v286/v286_coinbase_member_upgrade.py")
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
    size, tp = build_j1_hooks(eu, idx, cols)
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    out = {"version": "v297", "rows": {}, "trades": {}}
    for key, (target, budget) in ROWS.items():
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, target=target, sleeve_fill_size=size, sleeve_tp=tp,
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
    sel = None
    for cap in (15.0, 16.0):
        tier = {k: v for k, v in out["rows"].items() if k != "J1_ref" and v["dev_dd"] <= cap and v["worst_dev_month_pct"] >= 3.0
                and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
        if tier:
            sel = max(tier, key=lambda k: (tier[k]["worst_dev_month_pct"], tier[k]["monthly_dev4"]))
            out["tier"] = cap
            break
    out["selected"] = sel
    if sel:
        s_ = out["rows"][sel]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"][sel]["_hidden"]}
    else:
        out["final_score_selected"] = "no row meets the new-goal rule - J1 stays; nothing scored on the most recent year"
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
    (HERE / "v297_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
