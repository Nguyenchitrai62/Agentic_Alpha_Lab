"""v285: re-test the Coinbase-premium member D (Coinbase spot exchange data) on the C4 foundation and rules.

Why (user 2026-09-30: use the available exchange data to the maximum): D - the v154 model set on the Coinbase (US spot exchange) premium - is
one of the two members the research map lists as 'good alone'. It was dropped when v206 added it to the touch-stop books (v205) and the
drawdown crossed 20 (the DD margin was ~0.2 pp). The C4 foundation (O1 + TradingView members) with 4-sigma candle-close dip stops has a
1.7 pp margin (DD 18.27). Cached, audited members: D annual (members_v154.parquet 'D'), D quarterly (members_quarterly_D.parquet).
Fixed before running.
Environment = C4 rules (v269 M1: dip stops on 5m closes at 4 sigma + 8-sigma native backstop, budget 0.18, v218 D2 settings).
  D1_six_sets   books = mean over {A, B, D} x {annual, quarterly}                      (v206's form)
  D2_d20        books = 0.8 x C4 books + 0.2 x (D + Dq) / 2
Reference: C4 books (must reproduce dev4 6.026). SELECTION = robust criterion among D1, D2; the most recent year is scored once for the
selected row.

  python research/parallel/rounds/parallel-20260906-r2/v285/v285_coinbase_member_c4.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C4 = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    idx = books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    c4 = 0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2
    mixes = {"C4": c4, "D1_six_sets": (m["A"] + m["B"] + m["D"] + m["Aq"] + m["Bq"] + m["Dq"]) / 6,
             "D2_d20": 0.8 * c4 + 0.2 * (m["D"] + m["Dq"]) / 2}
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {"version": "v285", "rows": {}, "trades": {}}
    for key, bk in mixes.items():
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
        if key == "C4":
            assert abs(r["monthly_dev4"] - 6.026) < 0.002
    cands = ("D1_six_sets", "D2_d20")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s_ = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                   "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
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
    (HERE / "v285_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
