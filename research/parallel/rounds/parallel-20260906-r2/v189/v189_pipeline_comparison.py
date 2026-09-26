"""v189: re-evaluate the best existing pipelines under the user's real trading rules (engine_user) (registry v189).

User (2026-09-27): "đánh giá qua lại các pipeline tốt nhất hiện tại". Pre-registered comparison, no new parameters:
P1 = v144 books (member A), P2 = v151 books (A+B)/2, P3 = v154 books (A+B+D)/3 (members cached by v187 in
artifacts/research/engine_real/members_v154.parquet); each without and with the dip sleeve (v183 ladder, TP L(1+sigma),
SL L(1-2 sigma)). Book SL/TP m = 4 daily sigma (selected in v188 on the first four years). Vol target 0.25, cap 2,
governor, maker 0.02%, taker 0.055%, adverse funding, no carry.
SELECTION: highest monthly_dev4 (first four anchors) among rows with DD <= 20% and no losing year in those four years.
The selected row's most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v189/v189_pipeline_comparison.py
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
    m = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B, D = (m.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[list(books154.columns)] for k in ("A", "B", "D"))
    assert ((A + B + D) / 3 - books154).abs().max().max() < 1e-9
    pipes = {"P1_v144": A, "P2_v151": (A + B) / 2, "P3_v154": books154}
    prep = eu.prepare(books154, opens)
    out = {"version": "v189", "rows": {}}
    for name, bk in pipes.items():
        for sl in (False, True):
            key = f"{name}{'+sleeve' if sl else ''}"
            r = eu.simulate(bk, opens, prep, m_sl=4.0, m_sleeve_sl=2.0, sleeve=sl)
            out["rows"][key] = r
            print(key, "dev4", r["monthly_dev4"], "5y", r["monthly_5y"], "gateDD", r["gate_dd"],
                  "years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]], flush=True)
    ok = {k: v for k, v in out["rows"].items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or out["rows"]
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v189_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
