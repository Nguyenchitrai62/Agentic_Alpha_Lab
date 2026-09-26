"""v201: hourly-anchored dip ladder added to v197 under the stop-risk budget (registry v201).

Why: v196 showed the 4h-anchored sleeve is capacity-limited (at budget 0.16 all 5163 candidate rungs are taken), and
the liquidation-overshoot mechanism (confirmed out-of-universe in v181) works at the minute scale. An hourly-anchored
ladder adds independent, smaller overshoots. v184 failed only because hourly rungs crowded the old NOTIONAL budget;
the stop-risk budget (v193) prices each rung by its stop distance, which is smaller for hourly rungs.
Fixed before running: hourly ladder per hour h of the 4h holding bar: base = 1m open of minute 60h; sigma_1h = std of
1h open-to-open returns over the 1440 hours ending before the bar (min 480); rungs 2.5/3/3.5/4 sigma_1h; bids live
minutes 16..57 (h=0) or 60h+4..60h+57; maker fill on a 1m trade-through; TP L(1 + sigma_1h) (maker), SL L(1 - 5
sigma_1h) (market); else market exit at the next hour's open (h = 3: next 4h open with funding). Same rung notional as
the 4h ladder (x1.5); one shared stop-risk budget (rn * (5 sigma + 2%)).
Pre-registered variants (the only ones): hourly OFF (reference = v197, must reproduce dev4 5.562 / DD 19.72); hourly ON
with the v197 budget 0.12; hourly ON with budget 0.18. Everything else = v197 (engine_user after the v188-audit fix).
SELECTION on the first four years (monthly_dev4, gate DD <= 20, no losing year among them); the selected variant's most
recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v201/v201_hourly_ladder_risk_budget.py
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
VARIANTS = (("ref_hourly_off", False, 0.12), ("hourly_on_b0.12", True, 0.12), ("hourly_on_b0.18", True, 0.18))


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v201", "rows": {}}
    for key, hourly, x in VARIANTS:
        r = eu.simulate(v151, opens, prep, m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239,
                        sleeve_risk_budget=x, size_mult=1.5, hourly=hourly)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "rungs", r["stats"]["rungs"], "stops/tps",
              r["stats"]["rung_stops"], r["stats"]["rung_tps"], "years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
        if key.startswith("ref"):
            assert abs(r["monthly_dev4"] - 5.562) < 0.002 and abs(r["gate_dd"] - 19.72) < 0.02, "reference must reproduce v197"
    ok = {k: v for k, v in out["rows"].items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or out["rows"]
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v201_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
