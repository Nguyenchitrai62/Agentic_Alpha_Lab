"""v193: dip-sleeve budget defined by stop risk instead of notional (registry v193).

Why: the notional budget (open sleeve notional <= 1/6 equity) was derived for a -30% crash with NO stop. Every rung now
carries a market stop at L(1 - 5 sigma_4h) (v191), so a rung's loss is bounded by its stop distance plus gap-through
slippage; the notional cap cancels ~60% of the rungs. Rule: take a fill only if the loss when every open rung and the
new one stop out, sum rn * (5 sigma_4h(asset) + 0.02 gap allowance), stays <= the risk budget X of equity.
Pre-registered variants (the only ones): X = 0.03, 0.05, 0.08. Pipeline: v192 selection (v151 books, book limits 10 bps
resting the whole bar, book SL/TP m = 4) + sleeve (rung SL 5 sigma_4h, TP L(1 + sigma_4h)); engine_user; gate DD =
max(4h, 1m-marked) includes stop gaps at 1m resolution. SELECTION on the first four years (monthly_dev4, DD <= 20, no
losing year among them); the selected variant's most recent year is the one-time final score. Reference: v192
selected row (notional budget), dev4 4.069.

  python research/parallel/rounds/parallel-20260906-r2/v193/v193_sleeve_risk_budget.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("engine_user", HERE.parent / "engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)
VARIANTS = (0.03, 0.05, 0.08)


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v193", "rows": {}}
    for x in VARIANTS:
        r = eu.simulate(v151, opens, prep, m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=x)
        out["rows"][str(x)] = r
        print("risk_budget", x, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "dd_1m", r["dd_1m"], "rungs", r["stats"]["rungs"],
              "stops/tps", r["stats"]["rung_stops"], r["stats"]["rung_tps"], "liq", r["stats"]["liq"], flush=True)
    ok = {k: v for k, v in out["rows"].items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or out["rows"]
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    s = out["rows"][sel]
    out["selected"] = float(sel)
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v193_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
