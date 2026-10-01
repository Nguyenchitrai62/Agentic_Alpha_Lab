"""v304: a wider dip ladder now that the learned agents can skip bad rungs - a RETURN-FIRST step (registry v304).

Why (user goal 2026-09-30: 6-7 %/month, DD ~15, win ~60%; stepwise, easiest first): the dip ladder has four rungs (2.5 / 3 / 3.5 / 4 sigma_4h below the
bar open). Shallow rungs fill often but were unprofitable on average (v250-v255 sleeve knobs, 2 sigma worse than 2.5 without a filter) and deep rungs
fill rarely; with the rule sleeve the ladder depth was the budget-limited choice. The pooled-experience agents (v293-v301) now estimate the net return of
EVERY rung before it is filled (size x0.5 / x1 / x1.5, take-profit multiple): a shallow rung the model dislikes is shrunk, a deep one it likes is
enlarged. So extra rungs add trades only where the model sees an edge. The standalone replica and every state feature are defined for any rung depth k.
Rung sets (engine argument `rungs`, replica constant v293.RUNGS; agents retrained on the pooled 35-coin experience of THAT set, fits on fills exited
before anchor - 7 days, S1 size rule, X4 take-profit rule, C4 rules, dip budget 0.26 shared by all rungs):
  R1_shallow   (2.0, 2.5, 3.0, 3.5, 4.0)
  R2_deep      (2.5, 3.0, 3.5, 4.0, 5.0)
  R3_wide      (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)
Reference: G2_ref = (2.5, 3.0, 3.5, 4.0) (must reproduce dev4 6.527, dev DD 17.33).
SELECTION (return-first, dev years only): pool = rows with dev DD <= G2_ref + 0.5, worst dev year >= 3.0 %/month and no losing dev year; highest dev4
(ties -> worst dev year); replaces G2 only if dev4 >= G2_ref + 0.15 (the HGB seed spread of the dev4 is ~0.15, v303). The most recent year is scored
once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v304/v304_ladder_depth.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
BUDGET = 0.26
SETS = {"G2_ref": (2.5, 3.0, 3.5, 4.0), "R1_shallow": (2.0, 2.5, 3.0, 3.5, 4.0), "R2_deep": (2.5, 3.0, 3.5, 4.0, 5.0),
        "R3_wide": (2.0, 2.5, 3.0, 3.5, 4.0, 5.0)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v301 = _load("v301_l", RD / "v301/v301_return_first_budget.py")
v296, v294, v293 = v301.v296, v301.v294, v301.v293


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_l", RD / "v286/v286_coinbase_member_upgrade.py")
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
    out = {"version": "v304", "rows": {}, "trades": {}}
    for key, rungs in SETS.items():
        v293.RUNGS = rungs  # the replica (fills_of) and the state feature "rung depth" read this module constant
        size_s1, size_s5, tp = v301.build_hooks(eu, idx, cols)
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=size_s1, sleeve_tp=tp, rungs=rungs,
                        **dict(v221.KW, **dict(v293.C4R, sleeve_risk_budget=BUDGET)))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["dev_rungs"] = v296.rung_stats([e for e in ev if e["t"] < anchors[4]])
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, rungs, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trade win", out["trades"][key]["dev"]["win_rate"], "dev rungs", r["dev_rungs"], flush=True)
        if key == "G2_ref":
            assert abs(r["monthly_dev4"] - 6.527) < 0.002 and abs(r["dev_dd"] - 17.33) < 0.02
    ref = out["rows"]["G2_ref"]
    pool = {k: v for k, v in out["rows"].items() if k != "G2_ref" and v["dev_dd"] <= ref["dev_dd"] + 0.5 and v["worst_dev_month_pct"] >= 3.0
            and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    sel = max(pool, key=lambda k: (pool[k]["monthly_dev4"], pool[k]["worst_dev_month_pct"])) if pool else None
    if sel and pool[sel]["monthly_dev4"] < ref["monthly_dev4"] + 0.15:
        sel = None
    out["selected"] = sel
    if sel:
        s_ = out["rows"][sel]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"][sel]["_hidden"]}
    else:
        out["final_score_selected"] = "no row meets the return-first rule - G2 stays; nothing scored on the most recent year"
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
    (HERE / "v304_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
