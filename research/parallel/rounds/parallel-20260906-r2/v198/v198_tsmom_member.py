"""v198: time-series-momentum (trend) book blended with the ML books (registry v198).

Why (first four years only): the v151 books earned +19% in the 2021 anchor year (bear market) vs +74-80% in 2023-24;
the sleeve cannot fill that gap in calm years. Time-series momentum is the classic diversifier in sustained trends and
bears; under the user's funding rule shorts pay no funding. Low-parameter, fixed before running:
- For each major j at decision t (4h opens known at t): signal_j = mean over L in (180, 540, 1080) bars (30/90/180 days)
  of sign(open_t / open_{t-L} - 1); vol_j = std of 4h open-to-open returns over 42 bars * sqrt(2190);
  raw_j = signal_j * 0.20 / vol_j / 5, clipped to [-0.5, 0.5]. T = the resulting weight panel (no tranching).
- Pipelines (the only three): v151 books (reference = v197 selection); 0.75 v151 + 0.25 T; 0.5 v151 + 0.5 T. All with
  the v197 sleeve (rung size x1.5, stop-risk budget 0.12, rung stop 5 sigma_4h, TP 1 sigma_4h), book SL/TP m = 4,
  10 bps book limits resting the whole bar, vol target 0.25 on the blended books, governor; engine_user.
- SELECTION on the first four years (monthly_dev4, gate DD <= 20, no losing year among them); the selected pipeline's
  most recent year is the one-time final score.

  python research/parallel/rounds/parallel-20260906-r2/v198/v198_tsmom_member.py
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


def tsmom(opens, idx, cols):
    o = opens[cols].sort_index()
    sig = sum(np.sign(o / o.shift(L) - 1) for L in (180, 540, 1080)) / 3
    vol = o.pct_change().rolling(42, min_periods=42).std() * np.sqrt(2190)
    raw = (sig * 0.20 / vol / 5).clip(-0.5, 0.5)
    return raw.reindex(idx).fillna(0.0)


def main():
    books154, opens = eu.er.v154_books()
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    cols = list(books154.columns)
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    v151 = (A + B) / 2
    T = tsmom(opens, books154.index, cols)
    prep = eu.prepare(books154, opens)
    out = {"version": "v198", "rows": {}}
    for key, bk in (("ref_v151", v151), ("blend75_25", 0.75 * v151 + 0.25 * T), ("blend50_50", 0.5 * v151 + 0.5 * T)):
        r = eu.simulate(bk, opens, prep, m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239,
                        sleeve_risk_budget=0.12, size_mult=1.5)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "gateDD", r["gate_dd"], "years",
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
    (HERE / "v198_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
