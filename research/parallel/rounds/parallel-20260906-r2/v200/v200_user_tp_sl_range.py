"""v200: book stop-loss / take-profit inside the user's preferred 3-10% range (registry v200).

User (2026-09-27): the v197 book stops/targets (4 / 8 daily sigma, ~8% / ~15% for BTC) are too far - they can take a
month to hit; bring them to roughly 3-10%. Pre-registered variants (the only ones), everything else = v197 (v151 books,
target 0.25, 10 bps book limits resting the whole bar, sleeve x1.5 with stop-risk budget 0.12, rung SL 5 sigma_4h / TP
1 sigma_4h; engine_user after the v188-audit fix):
  A: SL 2 sigma_d, TP 4 sigma_d; B: SL 2.5 sigma_d, TP 2.5 sigma_d; C: SL 3 sigma_d, TP 2 sigma_d.
Reference (not selectable, outside the user's range): v197 SL 4 / TP 8.
Also reported: the median SL/TP distance in % per asset over the live span (sigma_d = 360-bar 4h std * sqrt(6)), the
mean and max gross book exposure (leverage as % of equity).
SELECTION among A/B/C on the first four years (monthly_dev4, gate DD <= 20, no losing year among them); the selected
variant's most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v200/v200_user_tp_sl_range.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("engine_user", HERE.parent / "engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)
VARIANTS = (("A_sl2_tp4", 2.0, 4.0), ("B_sl2.5_tp2.5", 2.5, 2.5), ("C_sl3_tp2", 3.0, 2.0))


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    live = np.asarray((books154.index >= eu.v110.START) & (books154.index < eu.v110.END))
    sd = pd.DataFrame(prep["sig4"] * np.sqrt(6), columns=cols)[live].median()
    out = {"version": "v200", "median_sigma_d_pct": {c: round(100 * float(v), 2) for c, v in sd.items()}, "rows": {}}
    print("median daily sigma %", out["median_sigma_d_pct"], flush=True)
    kw = dict(m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5)
    for key, msl, mtp in VARIANTS + (("ref_v197_sl4_tp8", 4.0, 8.0),):
        r = eu.simulate(v151, opens, prep, m_sl=msl, m_tp=mtp, **kw)
        r["sl_tp_median_pct"] = {c: (round(msl * 100 * float(sd[c]), 1), round(mtp * 100 * float(sd[c]), 1)) for c in cols}
        r["gross_mean_pct"] = round(100 * r["stats"]["gross_sum"] / max(r["stats"]["bars"], 1), 1)
        r["gross_max_pct"] = round(100 * r["stats"]["gross_max"], 1)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "stops/tps", r["stats"]["stops"], r["stats"]["tps"],
              "gross mean/max %", r["gross_mean_pct"], r["gross_max_pct"], "SL/TP % BTC", r["sl_tp_median_pct"]["BTCUSDT"], flush=True)
    cand = {k: v for k, v in out["rows"].items() if not k.startswith("ref")}
    ok = {k: v for k, v in cand.items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or cand
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v200_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
