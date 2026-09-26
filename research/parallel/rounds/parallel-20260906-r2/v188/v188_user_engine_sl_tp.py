"""v188: the current best pipeline re-scored under the user's real trading rules, with SL/TP on every position
(registry v188).

AGENTS.md rules of 2026-09-27: limit entries (unfilled limits expire), a market stop-loss and a limit take-profit on
every position, maker 0.02%, taker 0.055%, adverse funding (longs 0.01%/8h, shorts 0), no carry sleeve, majors only,
gate = 5-year mean >= 5%/month AND most recent year >= 5%/month AND no losing year AND DD <= 20% (max 4h, 1m-marked).
Engine: research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py (unit-tested).
Fixed before running:
- Books v154 (A+B+D)/3, vol target 0.25, cap 2, 20% governor; dip sleeve v183 ladder with TP at L(1+sigma_4h) and a
  market stop at L(1 - 2 sigma_4h), open-notional budget 1/6.
- Three pre-registered variants (the only ones for this direction): book stop m = 2, 3, 4 daily sigma, TP = 2m.
- SELECTION on the first four walk-forward years only (monthly_dev4, subject to DD <= 20% and no losing year in those
  years); the most recent year is reported for the selected variant as the one-time final score (it was already seen
  in earlier versions, so the prospective log remains the clean check).
- Reference rows: the selected variant without the sleeve.

  python research/parallel/rounds/parallel-20260906-r2/v188/v188_user_engine_sl_tp.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("engine_user", HERE.parent / "engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)
VARIANTS = (2.0, 3.0, 4.0)


def main():
    books, opens = eu.er.v154_books()
    prep = eu.prepare(books, opens)
    out = {"version": "v188", "variants": {}}
    for m in VARIANTS:
        r = eu.simulate(books, opens, prep, m_sl=m, m_sleeve_sl=2.0, sleeve=True)
        dev_ok = r["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in r["yearly"][:4])
        out["variants"][str(m)] = r
        print("m_sl", m, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "dev_ok", dev_ok, "stats", r["stats"], flush=True)
    ok = {m: v for m, v in out["variants"].items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or out["variants"]
    sel = max(pool, key=lambda m: pool[m]["monthly_dev4"])
    out["selected_m_sl"] = float(sel)
    s = out["variants"][sel]
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED (by first four years) m_sl", sel, "->", out["final_score_selected"], flush=True)
    nb = eu.simulate(books, opens, prep, m_sl=float(sel), sleeve=False)
    out["reference_no_sleeve"] = nb
    print("no sleeve", nb["monthly_dev4"], nb["monthly_5y"], nb["monthly_last_year"], nb["gate_dd"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v188_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
