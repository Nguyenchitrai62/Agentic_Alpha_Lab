"""v305: keep the 2.0-sigma dip rung and re-balance risk to the old drawdown - RETURN AT EQUAL DD (registry v305).

Why: v304 R1 (ladder 2.0 / 2.5 / 3.0 / 3.5 / 4.0 with the pooled-experience agents retrained on that rung set) lifted the dev4 from 6.527 to 7.807 %/month
(dip rungs 4073 -> 7022, rung win 70.0% -> 67.5%) but the dev DD from 17.33 to 20.25 - the extra rung adds sleeve risk in the flushes
(research/diagnostics/g2_dd: half of G2's DD is dip flushes). Return bought through the shallow rung cost ~0.44 pp per DD point; the book-risk
frontier measured in v297 costs ~1.5 pp per DD point, so trading book risk against the shallow rung should beat G2 at equal drawdown.
Two risk dials, both mechanical and chosen before running: the dip-sleeve risk budget (G2 0.26) and the book vol target (G2 0.25).
All rows use the v304 R1 ladder and its agents (one fit, 35-coin pooled experience, fits on fills exited before anchor - 7 days, S1 size rule, X4
take-profit rule, C4 rules).
Fixed before running:
  Q1_b22        budget 0.22, target 0.25
  Q2_b18        budget 0.18, target 0.25
  Q3_t22_b26    budget 0.26, target 0.22
  Q4_t22_b22    budget 0.22, target 0.22
Reference: G2_ref (4 rungs, budget 0.26, target 0.25: dev4 6.527, dev DD 17.33) and R1_ref (5 rungs, 0.26 / 0.25: 7.807 / 20.25) - both must reproduce.
SELECTION (return at equal drawdown, dev years only): pool = Q rows with dev DD <= 17.33 + 0.3, worst dev year >= 3.0 and no losing dev year; highest
dev4 (ties -> lower DD). Replaces G2 only if dev4 >= G2_ref + 0.3 (twice the HGB seed spread of ~0.15, v303). The most recent year is scored once
for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v305/v305_shallow_rung_rebalance.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
R1 = (2.0, 2.5, 3.0, 3.5, 4.0)
G2 = (2.5, 3.0, 3.5, 4.0)
ROWS = {"Q1_b22": (0.22, 0.25), "Q2_b18": (0.18, 0.25), "Q3_t22_b26": (0.26, 0.22), "Q4_t22_b22": (0.22, 0.22)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v301 = _load("v301_q", RD / "v301/v301_return_first_budget.py")
v296, v294, v293 = v301.v296, v301.v294, v301.v293


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_q", RD / "v286/v286_coinbase_member_upgrade.py")
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
    out = {"version": "v305", "rows": {}, "trades": {}}

    def run(key, rungs, size, tp, budget, target, expect=None):
        ev = []
        r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, sleeve_fill_size=size, sleeve_tp=tp, rungs=rungs, target=target,
                        **dict(v221.KW, **dict(v293.C4R, sleeve_risk_budget=budget)))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        r["dev_rungs"] = v296.rung_stats([e for e in ev if e["t"] < anchors[4]])
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev trade win", out["trades"][key]["dev"]["win_rate"], "dev rungs", r["dev_rungs"], flush=True)
        if expect is not None:
            assert abs(r["monthly_dev4"] - expect[0]) < 0.002 and abs(r["dev_dd"] - expect[1]) < 0.02, (key, r["monthly_dev4"], r["dev_dd"])

    v293.RUNGS = G2
    s1, _, tp = v301.build_hooks(eu, idx, cols)
    run("G2_ref", G2, s1, tp, 0.26, 0.25, expect=(6.527, 17.33))
    v293.RUNGS = R1
    s1, _, tp = v301.build_hooks(eu, idx, cols)
    run("R1_ref", R1, s1, tp, 0.26, 0.25, expect=(7.807, 20.25))
    for key, (budget, target) in ROWS.items():
        run(key, R1, s1, tp, budget, target)
    ref = out["rows"]["G2_ref"]
    pool = {k: v for k, v in out["rows"].items() if k in ROWS and v["dev_dd"] <= ref["dev_dd"] + 0.3 and v["worst_dev_month_pct"] >= 3.0
            and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    sel = max(pool, key=lambda k: (pool[k]["monthly_dev4"], -pool[k]["dev_dd"])) if pool else None
    if sel and pool[sel]["monthly_dev4"] < ref["monthly_dev4"] + 0.3:
        sel = None
    out["selected"] = sel
    if sel:
        s_ = out["rows"][sel]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"][sel]["_hidden"]}
    else:
        out["final_score_selected"] = "no row meets the equal-DD rule - G2 stays; nothing scored on the most recent year"
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
    (HERE / "v305_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
