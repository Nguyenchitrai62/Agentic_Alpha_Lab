"""v199: depth of the dip-sleeve ladder (registry v199).

The ladder stops at 4 sigma_4h below the 4h open; in the largest liquidation cascades prices overshoot further before
rebounding. Pre-registered variants (the only ones): rungs (2.5, 3, 3.5, 4) reference = v197 selection;
(2.5, 3, 3.5, 4, 5, 6); (3, 4, 5, 6). Per-rung size is unchanged (x1.5 of 0.25/4 before scaling), so deeper rungs add
capital only in deep drops; stop-risk budget 0.12 (v197), rung stop 5 sigma_4h, TP 1 sigma_4h; v151 books, book SL/TP m = 4,
10 bps book limits resting the whole bar; engine_user. SELECTION on the first four years (monthly_dev4, gate DD <= 20,
no losing year among them); the selected variant's most recent year is the one-time final score.

ENGINE NOTE: runs on engine_user after the v188-audit fix (1m-marked DD peaks include intrabar highs; a stop on the
held position wins a same-minute tie with a new fill). The reference row therefore re-scores v197 under the stricter DD.

  python research/parallel/rounds/parallel-20260906-r2/v199/v199_ladder_depth.py
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
VARIANTS = (("ref_2.5-4", (2.5, 3.0, 3.5, 4.0)), ("to6_six", (2.5, 3.0, 3.5, 4.0, 5.0, 6.0)), ("deep_3-6", (3.0, 4.0, 5.0, 6.0)))


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v199", "rows": {}}
    for key, rg in VARIANTS:
        r = eu.simulate(v151, opens, prep, m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239,
                        sleeve_risk_budget=0.12, size_mult=1.5, rungs=rg)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "rungs", r["stats"]["rungs"], "years",
              [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
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
    (HERE / "v199_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
