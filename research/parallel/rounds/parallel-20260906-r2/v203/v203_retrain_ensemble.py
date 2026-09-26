"""v203: ensemble of annually and quarterly retrained book models (registry v203).

Why: v202 showed quarterly retraining helps the weak dev years (2021 +49.6% vs +40.7%, 2022 +61.6% vs +51.3%) but hurts
2023 and raises DD to 22.5%; the two schedules err in different years. Averaging model sets trained on different
schedules reduces model variance (standard ensembling), without new parameters.
Fixed before running: books = 0.5 * v151(annual) + 0.5 * v151(quarterly) (members cached by v202); v197 sleeve and rules
(engine_user after the v188-audit fix). Pipelines (the only two): reference annual v151 (= v197) and the ensemble.
SELECTION on the first four years (monthly_dev4, gate DD <= 20, no losing year among them); the selected pipeline's
most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v203/v203_retrain_ensemble.py
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


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    annual, quarterly = (A + B) / 2, (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    kw = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5)
    out = {"version": "v203", "rows": {}}
    for key, bk in (("ref_annual_v151", annual), ("ensemble_annual_quarterly", 0.5 * annual + 0.5 * quarterly)):
        r = eu.simulate(bk, opens, prep, **kw)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
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
    (HERE / "v203_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
