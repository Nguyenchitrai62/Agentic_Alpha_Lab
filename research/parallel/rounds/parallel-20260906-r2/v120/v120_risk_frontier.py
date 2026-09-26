"""v120: risk-dial frontier of the v118 band-0.05 portfolio (registry parallel-20260906-r2 / v120, track A).

v115 books + v118 no-trade band 0.05, ungoverned, portfolio vol target in (0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25)
(cap 2x). Reports monthly return, worst-year DD and full-path DD per scenario. This is a reporting frontier: any target
picked from it is an EX-POST risk-budget choice on data already seen and must be labelled as such; the registered
primary row is target 0.18 (fixed before running as the midpoint between the audited 0.15 and the 0.20/0.25 rows).

  python research/parallel/rounds/parallel-20260906-r2/v120/v120_risk_frontier.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v118", HERE.parent / "v118" / "v118_no_trade_band.py")
v118 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v118)
TARGETS = (0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25)


def main():
    panel, books = v118.v115.books_v115()
    out = {"version": "v120", "band": 0.05, "frontier": {}}
    for tgt in TARGETS:
        res = {}
        for sc, (fee, slip) in v118.v115.v104.v92.SCEN.items():
            res[sc] = v118.v110.summarize(*v118.run_band(panel, books, 0.05, fee, slip, target=tgt))
        out["frontier"][f"t{int(round(tgt * 100)):02d}"] = res
        print(f"target {tgt:.2f}", {sc: (res[sc]["monthly_pct"], res[sc]["full_path_dd"]) for sc in res}, flush=True)
    out["primary_t18"] = out["frontier"]["t18"]
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v120_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
