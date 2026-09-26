"""v192: offset and resting window of the book limit orders under the user's no-market-fallback rule (registry v192).

User rule: book entries/rebalances are limit orders and an unfilled limit expires. ~19% of book orders expire at the
current setting (10 bps better than the minute-0 price, resting minutes 2..59), chosen earlier (v135/v170) when a taker
fallback existed. Pre-registered variants (the only ones for this direction), on the v191-selected pipeline (v151 books
+ sleeve with rung stop 5 sigma_4h, book SL/TP m = 4, engine_user):
  (10 bps, minutes 2..59) reference; (10 bps, minutes 2..238); (3 bps, minutes 2..238).
SELECTION on the first four years (monthly_dev4, DD <= 20, no losing year among them); the selected variant's most
recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v192/v192_book_limit_orders.py
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
VARIANTS = (("10bps_60m", 0.001, 60), ("10bps_bar", 0.001, 239), ("3bps_bar", 0.0003, 239))


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    prep = eu.prepare(books154, opens)
    out = {"version": "v192", "rows": {}}
    for key, dl, we in VARIANTS:
        r = eu.simulate(v151, opens, prep, m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=dl, win_end=we)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "fills/unfilled", r["stats"]["fills"], r["stats"]["unfilled"], flush=True)
    ok = {k: v for k, v in out["rows"].items() if v["gate_dd"] <= 20 and all(y["net_pct"] >= 0 for y in v["yearly"][:4])}
    pool = ok or out["rows"]
    sel = max(pool, key=lambda k: pool[k]["monthly_dev4"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v192_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
